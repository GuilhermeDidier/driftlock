"""Repair a broken mapping, and prove the repair before trusting it.

The healer is the only component in Driftlock that costs money and the only
one that is non-deterministic. Both facts shape its design:

* It never writes to the active mapping. It produces a CANDIDATE.
* A candidate reaches production only by reproducing every golden fixture.
* Every call is bounded -- attempts per run, dollars per run, and characters
  of payload sent to the model.

The model is the repair mechanism. The fixtures are the authority.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import anthropic
from django.conf import settings
from pydantic import BaseModel, Field

from contracts.engine import ContinuityResult, ContractSpec, check_continuity
from sources.adapters import ROW_RULE, get_adapter
from sources.models import Source

# USD per million tokens, input/output. Used for the per-run budget gate.
PRICING: dict[str, tuple[float, float]] = {
    "claude-opus-5": (5.00, 25.00),
    "claude-sonnet-5": (2.00, 10.00),
    "claude-haiku-4-5": (1.00, 5.00),
}


class HealerUnavailable(RuntimeError):
    """No API key configured, so healing cannot be attempted."""


# --- what we ask the model for ---------------------------------------------

class HtmlFieldRule(BaseModel):
    field: str = Field(description="contract field name this rule fills")
    selector: str = Field(description="CSS selector, relative to one row element")
    attr: str = Field(default="text", description="'text', or an attribute name like 'href'")


class HtmlMappingProposal(BaseModel):
    row_selector: str = Field(description="CSS selector matching one element per record")
    fields: list[HtmlFieldRule]
    notes: str = Field(description="one sentence on what appears to have changed")


class CsvFieldRule(BaseModel):
    field: str
    column: str = Field(description="exact column header to read this field from")


class CsvMappingProposal(BaseModel):
    fields: list[CsvFieldRule]
    notes: str


PROPOSAL_MODELS = {"html": HtmlMappingProposal, "csv": CsvMappingProposal}


# --- results ---------------------------------------------------------------

@dataclass
class Usage:
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0

    @property
    def cost_usd(self) -> Decimal:
        rate_in, rate_out = PRICING.get(self.model, (0.0, 0.0))
        dollars = (self.input_tokens * rate_in + self.output_tokens * rate_out) / 1_000_000
        return Decimal(f"{dollars:.6f}")


@dataclass
class Proposal:
    rules: dict[str, Any]
    notes: str
    usage: Usage


# --- asking the model ------------------------------------------------------

def _client() -> anthropic.Anthropic:
    key = settings.DRIFTLOCK.get("ANTHROPIC_API_KEY")
    if not key:
        raise HealerUnavailable(
            "ANTHROPIC_API_KEY is not set; Driftlock will fail closed instead of healing"
        )
    return anthropic.Anthropic(api_key=key)


SYSTEM = """You repair data-extraction mappings that have stopped working.

A mapping tells a pipeline how to pull each contract field out of a source
payload. The source changed shape, so some rules now match nothing, or match
the wrong element.

Work from what each field MEANS, given in its description, not from what the
old rule looked like. The old rule is evidence about the previous layout, not
a template to mutate.

Rules:
- Every contract field must get exactly one rule.
- Leave a rule alone if it still works. The validator report below tells you
  which fields are healthy; rewriting those adds risk and proves nothing.
- A field selector is matched against the row's descendants and against the row
  element itself, so an attribute carried on the row is reachable directly.
- Prefer selectors anchored on stable, semantic attributes (data-*, id, role,
  itemprop) over presentational class names, which are the thing that just
  changed.
- Field selectors are evaluated relative to a single row element.
- Never invent a field that is not in the contract.
- If a field genuinely is not present in the new payload, still return your
  best candidate rule. A wrong guess is caught by the proof gates; a missing
  rule just wastes the attempt."""


def propose(
    source: Source,
    contract: ContractSpec,
    current_rules: dict[str, Any],
    digest: str,
    failure: str,
) -> Proposal:
    """Ask the model for a replacement mapping. Nothing here trusts the answer."""
    schema = PROPOSAL_MODELS.get(source.kind)
    if schema is None:
        raise HealerUnavailable(f"no heal schema for source kind {source.kind!r}")

    fields_block = "\n".join(
        f"- {f.name} ({f.type.value}{'' if f.required else ', optional'}): {f.description}"
        for f in contract.fields
    )
    prompt = f"""Contract `{contract.key}` -- the fields that must be filled:
{fields_block}

The mapping that used to work:
{current_rules}

What the validator observed on the current payload:
{failure}

The current payload, pruned to its structure:
{digest}

Propose a mapping that reads the fields above out of this payload."""

    model = settings.DRIFTLOCK["HEAL_MODEL"]
    started = time.monotonic()
    response = _client().messages.parse(
        model=model,
        max_tokens=8000,
        system=SYSTEM,
        output_config={"effort": "medium"},
        messages=[{"role": "user", "content": prompt}],
        output_format=schema,
    )
    latency_ms = int((time.monotonic() - started) * 1000)

    parsed = response.parsed_output
    if parsed is None:
        raise HealerUnavailable("model returned no parseable proposal")

    if source.kind == "html":
        rules: dict[str, Any] = {ROW_RULE: {"selector": parsed.row_selector}}
        for rule in parsed.fields:
            rules[rule.field] = {"selector": rule.selector, "attr": rule.attr or "text"}
    else:
        rules = {rule.field: {"column": rule.column} for rule in parsed.fields}

    return Proposal(
        rules=rules,
        notes=parsed.notes,
        usage=Usage(
            model=model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            latency_ms=latency_ms,
        ),
    )


# --- the proof gate --------------------------------------------------------

def normalise(value: Any) -> Any:
    """Make coerced values comparable with values that round-tripped as JSON."""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, float):
        return round(value, 6)
    return value


def trusted_records(source: Source) -> tuple[list[dict], str]:
    """The records a candidate must recover, and where they came from.

    Human-pinned fixtures win outright when they exist -- a person confirmed
    those. Otherwise the most recent clean run stands in, so a source that has
    succeeded even once is never promoted against nothing.
    """
    pinned = list(source.fixtures.filter(enabled=True, pinned=True))
    if pinned:
        records = [r for f in pinned for r in f.records]
        return records, f"{len(pinned)} pinned fixture(s)"

    latest = source.fixtures.filter(enabled=True, pinned=False).first()
    if latest:
        return list(latest.records), f"last clean run ({latest.name})"
    return [], "nothing trusted yet"


def prove(
    source: Source, contract: ContractSpec, produced: list[dict]
) -> tuple[ContinuityResult, str]:
    """Judge a candidate by what it recovered, not by how it is written."""
    baseline, origin = trusted_records(source)
    result = check_continuity(
        baseline=[{k: normalise(v) for k, v in r.items()} for r in baseline],
        produced=[{k: normalise(v) for k, v in r.items()} for r in produced],
        key_fields=contract.unique_by,
        stable_fields=contract.stable_fields,
        threshold=contract.continuity_threshold,
    )
    return result, origin
