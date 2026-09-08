from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class FieldType(str, Enum):
    STRING = "string"
    INTEGER = "integer"
    NUMBER = "number"
    BOOLEAN = "boolean"
    DATE = "date"
    URL = "url"
    EMAIL = "email"


@dataclass(frozen=True)
class FieldSpec:
    """One field of a record.

    `description` is the semantic anchor: it is what survives when the source
    changes. Selectors are a cache of how to find this field today; the
    description is what the field *is*. The healer re-derives the former from
    the latter.
    """

    name: str
    type: FieldType
    description: str
    required: bool = True

    # Should this value stay the same across runs for the same record? Names
    # and identifiers usually should; prices and counts should not. Only
    # stable fields are compared when proving a healed mapping.
    stable: bool = False

    # Per-value invariants.
    min_value: float | None = None
    max_value: float | None = None
    max_length: int | None = None
    pattern: str | None = None
    choices: tuple[str, ...] | None = None

    # Only consulted for DATE fields; tried in order after ISO-8601.
    date_formats: tuple[str, ...] = ("%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y")


@dataclass(frozen=True)
class ContractSpec:
    """A declared shape for a batch of records.

    Two tiers of rules, and the split is the whole point:

    * Per-record rules catch a dirty row. The row is quarantined, the batch
      still ships.
    * Batch rules catch a source that changed shape. Nothing ships.

    A broken extraction rarely raises. It returns null for every row, or the
    same value for every row (a selector that drifted onto a header). Those are
    the two silent killers, so they each get a batch rule.
    """

    key: str
    fields: tuple[FieldSpec, ...]

    min_records: int = 1

    # field name -> minimum share of records with a non-empty value (0..1)
    min_fill_rate: dict[str, float] = field(default_factory=dict)

    # field name -> minimum distinct values / record count (0..1).
    # Catches a selector collapsing onto one repeated element.
    min_distinct_ratio: dict[str, float] = field(default_factory=dict)

    # Fields whose combined value must be unique across the batch. Doubles as
    # the identity used to match records against a trusted baseline.
    unique_by: tuple[str, ...] = ()

    # Share of trusted records a healed mapping must recover to be promoted.
    continuity_threshold: float = 0.8

    @property
    def stable_fields(self) -> tuple[str, ...]:
        return tuple(f.name for f in self.fields if f.stable)

    def field_by_name(self, name: str) -> FieldSpec | None:
        for f in self.fields:
            if f.name == name:
                return f
        return None

    @property
    def field_names(self) -> tuple[str, ...]:
        return tuple(f.name for f in self.fields)
