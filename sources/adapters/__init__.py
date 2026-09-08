from __future__ import annotations

from .base import ROW_RULE, Adapter, ExtractionError
from .csv_adapter import CsvAdapter
from .html import HtmlAdapter

_ADAPTERS: dict[str, Adapter] = {
    HtmlAdapter.kind: HtmlAdapter(),
    CsvAdapter.kind: CsvAdapter(),
}


def get_adapter(kind: str) -> Adapter:
    try:
        return _ADAPTERS[kind]
    except KeyError:
        raise ExtractionError(f"no adapter for source kind {kind!r}") from None


__all__ = ["Adapter", "ExtractionError", "ROW_RULE", "get_adapter"]
