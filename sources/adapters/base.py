from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

# Reserved key in a mapping's rules: how to slice the payload into rows.
ROW_RULE = "__row__"


class ExtractionError(RuntimeError):
    """The payload could not be sliced into rows at all."""


class Adapter(ABC):
    """Reads a raw payload into rows of raw field values.

    Adapters never validate and never coerce. They return whatever the source
    literally said, including None for a rule that matched nothing -- that
    silence is the signal the contract engine is built to catch.
    """

    kind: str

    @abstractmethod
    def fetch(self, config: dict[str, Any]) -> str:
        """Retrieve the raw payload for a source."""

    @abstractmethod
    def extract(self, raw: str, rules: dict[str, Any], config: dict[str, Any]) -> list[dict]:
        """Apply a mapping's rules to a raw payload."""

    @abstractmethod
    def structure_digest(self, raw: str, budget: int) -> str:
        """A pruned view of the payload for the healer to reason over.

        Must fit in `budget` characters. The healer is the only component that
        costs money per call, and payload size is what drives that cost, so
        pruning here is a budget control, not a nicety.
        """
