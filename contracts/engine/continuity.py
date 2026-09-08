"""Does a candidate mapping still recover the records we already trust?

This is Driftlock's proof of correctness, and it is deliberately not a replay
of old payloads. Replay cannot work: the moment a source genuinely changes
shape, a mapping written for the new shape can never reproduce a capture of
the old one. Testing structure against structure asks the wrong question.

The right question is about content. A redesign changes the packaging, not the
facts -- the same products are on the page, at the same names. So a candidate
proves itself by recovering the records we already know are correct.

Two refinements make that workable against live data:

* Records are matched by a declared key, not by position. Ordering changes all
  the time and means nothing.
* Only fields declared `stable` are compared. A price is expected to move
  between runs; a product's name is not. Comparing volatile fields would
  reject honest mappings on ordinary data churn.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ContinuityResult:
    baseline_size: int = 0
    recovered: int = 0          # baseline keys that reappeared at all
    matched: int = 0            # ... and whose stable fields were identical
    threshold: float = 0.0
    key_fields: tuple[str, ...] = ()
    stable_fields: tuple[str, ...] = ()
    mismatches: list[dict] = field(default_factory=list)
    reason: str = ""

    @property
    def rate(self) -> float:
        return self.matched / self.baseline_size if self.baseline_size else 0.0

    @property
    def passed(self) -> bool:
        # Nothing to check against is not a pass. An unproven mapping is
        # refused, exactly like a disproven one.
        if self.baseline_size == 0 or not self.key_fields:
            return False
        return self.rate >= self.threshold

    @property
    def summary(self) -> str:
        if not self.key_fields:
            return "contract declares no record key, so continuity cannot be checked"
        if self.baseline_size == 0:
            return "no trusted records to check against"
        return (
            f"{self.matched}/{self.baseline_size} trusted records recovered "
            f"({self.rate:.0%}, threshold {self.threshold:.0%})"
        )


def _key_of(record: dict[str, Any], key_fields: tuple[str, ...]) -> tuple | None:
    key = tuple(record.get(name) for name in key_fields)
    return None if any(part is None for part in key) else key


def check_continuity(
    baseline: list[dict[str, Any]],
    produced: list[dict[str, Any]],
    key_fields: tuple[str, ...],
    stable_fields: tuple[str, ...],
    threshold: float,
) -> ContinuityResult:
    """Compare a candidate's output against records already known to be right."""
    result = ContinuityResult(
        threshold=threshold, key_fields=key_fields, stable_fields=stable_fields,
    )
    if not key_fields:
        result.reason = "no key fields declared on the contract"
        return result

    trusted = {}
    for record in baseline:
        key = _key_of(record, key_fields)
        if key is not None:
            trusted[key] = record
    result.baseline_size = len(trusted)
    if not trusted:
        result.reason = "baseline holds no records with a complete key"
        return result

    produced_by_key = {}
    for record in produced:
        key = _key_of(record, key_fields)
        if key is not None:
            produced_by_key.setdefault(key, record)

    for key, want in trusted.items():
        got = produced_by_key.get(key)
        if got is None:
            result.mismatches.append({
                "key": list(key), "problem": "record not recovered",
            })
            continue

        result.recovered += 1
        differing = {
            name: {"expected": want.get(name), "produced": got.get(name)}
            for name in stable_fields
            if want.get(name) != got.get(name)
        }
        if differing:
            result.mismatches.append({
                "key": list(key), "problem": "stable field changed", "fields": differing,
            })
        else:
            result.matched += 1

    return result
