"""Pure-Python contract engine: no Django imports, no I/O.

Kept dependency-free so the validation rules can be unit-tested on their own
and reused outside the web layer.
"""
from .spec import ContractSpec, FieldSpec, FieldType
from .report import ValidationReport, RecordResult, Violation, Verdict
from .continuity import ContinuityResult, check_continuity
from .validator import validate

__all__ = [
    "ContractSpec", "FieldSpec", "FieldType",
    "ValidationReport", "RecordResult", "Violation", "Verdict",
    "validate", "check_continuity", "ContinuityResult",
]
