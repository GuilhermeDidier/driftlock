from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Verdict(str, Enum):
    PASS = "pass"            # everything clean
    PARTIAL = "partial"      # some rows quarantined, batch still publishable
    DRIFT = "drift"          # batch-level rule broke: publish nothing, heal


@dataclass(frozen=True)
class Violation:
    code: str
    message: str
    field: str | None = None
    observed: Any = None
    expected: Any = None


@dataclass
class RecordResult:
    index: int
    raw: dict[str, Any]
    value: dict[str, Any]
    violations: list[Violation] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.violations


@dataclass
class ValidationReport:
    records: list[RecordResult]
    batch_violations: list[Violation] = field(default_factory=list)
    fill_rates: dict[str, float] = field(default_factory=dict)
    distinct_ratios: dict[str, float] = field(default_factory=dict)

    @property
    def clean(self) -> list[RecordResult]:
        return [r for r in self.records if r.ok]

    @property
    def quarantined(self) -> list[RecordResult]:
        return [r for r in self.records if not r.ok]

    @property
    def verdict(self) -> Verdict:
        if self.batch_violations:
            return Verdict.DRIFT
        if self.quarantined:
            return Verdict.PARTIAL
        return Verdict.PASS

    @property
    def publishable(self) -> list[RecordResult]:
        """Rows allowed downstream. On DRIFT this is empty: fail closed.

        The failure mode this guards against is the expensive one -- a batch
        that looks fine row by row while the source has silently changed
        meaning underneath it.
        """
        if self.verdict is Verdict.DRIFT:
            return []
        return self.clean

    def summary(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict.value,
            "records": len(self.records),
            "clean": len(self.clean),
            "quarantined": len(self.quarantined),
            "batch_violations": [v.code for v in self.batch_violations],
            "fill_rates": self.fill_rates,
            "distinct_ratios": self.distinct_ratios,
        }
