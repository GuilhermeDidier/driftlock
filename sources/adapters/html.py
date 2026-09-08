from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin

import requests
import soupsieve
from bs4 import BeautifulSoup, Tag

from .base import ROW_RULE, Adapter, ExtractionError

_DROP_TAGS = ("script", "style", "noscript", "svg", "iframe", "template")


class HtmlAdapter(Adapter):
    kind = "html"

    def fetch(self, config: dict[str, Any]) -> str:
        url = config.get("url")
        if not url:
            raise ExtractionError("html source has no 'url' in config")
        response = requests.get(
            url,
            timeout=config.get("timeout", 20),
            headers={"User-Agent": config.get("user_agent", "Driftlock/1.0")},
        )
        response.raise_for_status()
        return response.text

    def extract(self, raw: str, rules: dict[str, Any], config: dict[str, Any]) -> list[dict]:
        soup = BeautifulSoup(raw, "lxml")

        row_rule = rules.get(ROW_RULE) or {}
        row_selector = row_rule.get("selector")
        if not row_selector:
            raise ExtractionError("mapping has no __row__ selector")

        rows = soup.select(row_selector)
        base_url = config.get("url", "")
        field_rules = {k: v for k, v in rules.items() if k != ROW_RULE}

        out: list[dict] = []
        for row in rows:
            record: dict[str, Any] = {}
            for name, rule in field_rules.items():
                record[name] = self._read(row, rule, base_url)
            out.append(record)
        return out

    def _read(self, row: Tag, rule: dict[str, Any], base_url: str) -> Any:
        selector = (rule or {}).get("selector")
        if not selector:
            return None

        # CSS selectors match descendants, but the value is often on the row
        # element itself -- a data-* attribute on the card, say. Falling back to
        # matching the row keeps the obvious selector working instead of
        # silently returning nothing.
        if selector == ".":
            node = row
        else:
            node = row.select_one(selector)
            if node is None and soupsieve.match(selector, row):
                node = row
        if node is None:
            return None  # deliberately silent; the contract engine judges it

        attr = (rule or {}).get("attr", "text")
        if attr == "text":
            return node.get_text(" ", strip=True)

        value = node.get(attr)
        if isinstance(value, list):  # e.g. class="a b"
            value = " ".join(value)
        if value and attr in ("href", "src") and base_url:
            value = urljoin(base_url, value)
        return value

    def structure_digest(self, raw: str, budget: int) -> str:
        """Strip a page down to the skeleton that decides a selector.

        Keeps tag names, id/class/data-* attributes and a short text sample per
        element. Drops scripts, styles, comments and long prose, which is where
        nearly all the bytes live and none of the selector signal does.
        """
        soup = BeautifulSoup(raw, "lxml")
        for tag in soup(list(_DROP_TAGS)):
            tag.decompose()

        lines: list[str] = []

        def walk(node: Tag, depth: int) -> None:
            if len(" ".join(lines)) > budget:
                return
            for child in node.find_all(recursive=False):
                attrs = []
                if child.get("id"):
                    attrs.append(f'id="{child["id"]}"')
                classes = child.get("class")
                if classes:
                    attrs.append(f'class="{" ".join(classes)[:80]}"')
                for key, val in child.attrs.items():
                    if key.startswith("data-") and isinstance(val, str):
                        attrs.append(f'{key}="{val[:40]}"')
                if child.name == "a" and child.get("href"):
                    attrs.append(f'href="{str(child["href"])[:60]}"')

                own_text = child.find(string=True, recursive=False)
                sample = re.sub(r"\s+", " ", str(own_text)).strip()[:60] if own_text else ""

                head = f"{'  ' * depth}<{child.name}{' ' + ' '.join(attrs) if attrs else ''}>"
                lines.append(f"{head} {sample}".rstrip())
                walk(child, depth + 1)

        walk(soup.body or soup, 0)
        digest = "\n".join(lines)
        if len(digest) > budget:
            digest = digest[:budget] + "\n... [truncated]"
        return digest
