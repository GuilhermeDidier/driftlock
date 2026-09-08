from __future__ import annotations

import re
from typing import Any, Iterable

from .coerce import CoercionError, coerce, is_empty
from .report import RecordResult, ValidationReport, Violation
from .spec import ContractSpec, FieldSpec


def _check_value(value: Any, spec: FieldSpec) -> list[Violation]:
    """Per-value invariants, run after successful coercion."""
    out: list[Violation] = []

    if spec.min_value is not None and isinstance(value, (int, float)):
        if value < spec.min_value:
            out.append(Violation(
                code="below_min", field=spec.name,
                message=f"{spec.name}={value} is below the declared minimum",
                observed=value, expected=spec.min_value,
            ))

    if spec.max_value is not None and isinstance(value, (int, float)):
        if value > spec.max_value:
            out.append(Violation(
                code="above_max", field=spec.name,
                message=f"{spec.name}={value} is above the declared maximum",
                observed=value, expected=spec.max_value,
            ))

    if spec.max_length is not None and isinstance(value, str):
        if len(value) > spec.max_length:
            out.append(Violation(
                code="too_long", field=spec.name,
                message=f"{spec.name} is {len(value)} chars, limit is {spec.max_length}",
                observed=len(value), expected=spec.max_length,
            ))

    if spec.pattern and isinstance(value, str):
        if not re.search(spec.pattern, value):
            out.append(Violation(
                code="pattern_mismatch", field=spec.name,
                message=f"{spec.name} does not match the declared pattern",
                observed=value, expected=spec.pattern,
            ))

    if spec.choices and value not in spec.choices:
        out.append(Violation(
            code="not_in_choices", field=spec.name,
            message=f"{spec.name}={value!r} is not one of the declared choices",
            observed=value, expected=list(spec.choices),
        ))

    return out


def _validate_record(index: int, raw: dict[str, Any], contract: ContractSpec) -> RecordResult:
    result = RecordResult(index=index, raw=raw, value={})

    for spec in contract.fields:
        present = raw.get(spec.name)

        if is_empty(present):
            result.value[spec.name] = None
            if spec.required:
                result.violations.append(Violation(
                    code="required_missing", field=spec.name,
                    message=f"{spec.name} is required but came back empty",
                    observed=present,
                ))
            continue

        try:
            value = coerce(present, spec)
        except CoercionError as exc:
            result.value[spec.name] = None
            result.violations.append(Violation(
                code="type_invalid", field=spec.name, message=str(exc),
                observed=present, expected=spec.type.value,
            ))
            continue

        result.value[spec.name] = value
        result.violations.extend(_check_value(value, spec))

    return result


def _flag_duplicates(records: list[RecordResult], contract: ContractSpec) -> None:
    """Quarantine repeat occurrences of a key, keeping the first.

    Record-level on purpose. A source that collapses onto a single repeated
    value is caught by the distinct-ratio rule as batch-level drift; this rule
    is for the ordinary case of a genuinely duplicated row.
    """
    if not contract.unique_by:
        return

    seen: dict[tuple, int] = {}
    for record in records:
        key = tuple(record.value.get(name) for name in contract.unique_by)
        if any(part is None for part in key):
            continue
        if key in seen:
            record.violations.append(Violation(
                code="duplicate_key",
                field=",".join(contract.unique_by),
                message=f"duplicate of record #{seen[key]} on {contract.unique_by}",
                observed=list(key),
            ))
        else:
            seen[key] = record.index


def _batch_rules(
    records: list[RecordResult], contract: ContractSpec
) -> tuple[list[Violation], dict[str, float], dict[str, float]]:
    """Rules that only exist across a whole batch -- the drift detectors."""
    violations: list[Violation] = []
    total = len(records)

    if total < contract.min_records:
        violations.append(Violation(
            code="too_few_records",
            message=f"batch has {total} records, contract requires at least {contract.min_records}",
            observed=total, expected=contract.min_records,
        ))

    fill_rates: dict[str, float] = {}
    distinct_ratios: dict[str, float] = {}

    for spec in contract.fields:
        filled = [r.value.get(spec.name) for r in records]
        non_empty = [v for v in filled if v is not None]
        fill_rates[spec.name] = (len(non_empty) / total) if total else 0.0
        distinct_ratios[spec.name] = (
            len({str(v) for v in non_empty}) / len(non_empty) if non_empty else 0.0
        )

    for name, threshold in contract.min_fill_rate.items():
        observed = fill_rates.get(name, 0.0)
        if observed < threshold:
            violations.append(Violation(
                code="fill_rate_below_threshold", field=name,
                message=(
                    f"{name} is present in {observed:.0%} of records, "
                    f"contract requires {threshold:.0%}"
                ),
                observed=round(observed, 4), expected=threshold,
            ))

    for name, threshold in contract.min_distinct_ratio.items():
        # If the field is empty everywhere, the fill-rate rule already reports
        # it. Skip here so one break does not surface as two findings.
        if fill_rates.get(name, 0.0) == 0.0:
            continue
        observed = distinct_ratios.get(name, 0.0)
        if observed < threshold:
            violations.append(Violation(
                code="distinct_ratio_below_threshold", field=name,
                message=(
                    f"{name} collapsed to {observed:.0%} distinct values, "
                    f"contract requires {threshold:.0%}"
                ),
                observed=round(observed, 4), expected=threshold,
            ))

    return violations, fill_rates, distinct_ratios


def validate(contract: ContractSpec, rows: Iterable[dict[str, Any]]) -> ValidationReport:
    """Check a batch of raw extracted rows against a contract."""
    records = [_validate_record(i, row, contract) for i, row in enumerate(rows)]
    _flag_duplicates(records, contract)
    batch_violations, fill_rates, distinct_ratios = _batch_rules(records, contract)
    return ValidationReport(
        records=records,
        batch_violations=batch_violations,
        fill_rates=fill_rates,
        distinct_ratios=distinct_ratios,
    )
