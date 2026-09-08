from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

from .spec import FieldSpec, FieldType

# Values a scraper or a spreadsheet emits when it means "nothing".
EMPTY_TOKENS = {"", "-", "--", "—", "n/a", "na", "null", "none", "nil"}

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s.]+\.[^@\s]+$")
_URL_RE = re.compile(r"^https?://[^\s/$.?#].[^\s]*$", re.IGNORECASE)
_TRUE = {"true", "1", "yes", "y", "sim", "s"}
_FALSE = {"false", "0", "no", "n", "nao", "não"}


class CoercionError(ValueError):
    """Raised when a raw value cannot be read as the declared type."""


def is_empty(raw: Any) -> bool:
    if raw is None:
        return True
    if isinstance(raw, str):
        return raw.strip().lower() in EMPTY_TOKENS
    return False


def parse_number(raw: Any) -> float:
    """Read a number written for humans in either pt-BR or en-US convention.

    Separator handling, in order:
      * both '.' and ',' present -> the rightmost one is the decimal separator
      * one separator, appearing more than once -> thousands ("1.234.567")
      * one separator, appearing once with exactly 3 digits after it ->
        read as thousands

    That last rule is a genuine ambiguity: "1.500" is 1500 in pt-BR and 1.5 in
    en-US. We resolve it as thousands because grouped thousands are far more
    common in scraped listings than a 3-decimal price. A source that needs the
    other reading should declare min_value/max_value so the wrong reading trips
    a per-value invariant instead of passing silently.
    """
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return float(raw)
    if not isinstance(raw, str):
        raise CoercionError(f"not a number: {raw!r}")

    text = raw.strip()
    negative = text.startswith("(") and text.endswith(")")  # accounting style
    cleaned = re.sub(r"[^\d,.\-]", "", text)
    if cleaned.count("-") > 1 or ("-" in cleaned and not cleaned.startswith("-")):
        cleaned = cleaned.replace("-", "")
    if not re.search(r"\d", cleaned):
        raise CoercionError(f"no digits in {raw!r}")

    has_dot, has_comma = "." in cleaned, "," in cleaned
    if has_dot and has_comma:
        decimal_sep = "." if cleaned.rfind(".") > cleaned.rfind(",") else ","
        thousands_sep = "," if decimal_sep == "." else "."
        cleaned = cleaned.replace(thousands_sep, "").replace(decimal_sep, ".")
    elif has_dot or has_comma:
        sep = "." if has_dot else ","
        head, _, tail = cleaned.rpartition(sep)
        if cleaned.count(sep) > 1 or (len(tail) == 3 and head.strip("-").isdigit()):
            cleaned = cleaned.replace(sep, "")
        else:
            cleaned = cleaned.replace(sep, ".")

    try:
        value = float(cleaned)
    except ValueError as exc:
        raise CoercionError(f"cannot read {raw!r} as a number") from exc
    return -value if negative and value > 0 else value


def parse_date(raw: Any, formats: tuple[str, ...]) -> date:
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    if not isinstance(raw, str):
        raise CoercionError(f"not a date: {raw!r}")

    text = raw.strip()
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        pass
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise CoercionError(f"cannot read {raw!r} as a date")


def coerce(raw: Any, spec: FieldSpec) -> Any:
    """Turn one raw extracted value into its declared type.

    Returns None for empty input; the caller decides whether that is allowed.
    """
    if is_empty(raw):
        return None

    if spec.type is FieldType.STRING:
        return str(raw).strip()

    if spec.type is FieldType.INTEGER:
        value = parse_number(raw)
        if value != int(value):
            raise CoercionError(f"{raw!r} is not a whole number")
        return int(value)

    if spec.type is FieldType.NUMBER:
        return parse_number(raw)

    if spec.type is FieldType.BOOLEAN:
        if isinstance(raw, bool):
            return raw
        token = str(raw).strip().lower()
        if token in _TRUE:
            return True
        if token in _FALSE:
            return False
        raise CoercionError(f"cannot read {raw!r} as a boolean")

    if spec.type is FieldType.DATE:
        return parse_date(raw, spec.date_formats)

    if spec.type is FieldType.EMAIL:
        token = str(raw).strip()
        if not _EMAIL_RE.match(token):
            raise CoercionError(f"{raw!r} is not an email address")
        return token

    if spec.type is FieldType.URL:
        token = str(raw).strip()
        if not _URL_RE.match(token):
            raise CoercionError(f"{raw!r} is not an http(s) URL")
        return token

    raise CoercionError(f"unsupported field type: {spec.type}")
