from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Any

import requests

from .base import Adapter, ExtractionError


class CsvAdapter(Adapter):
    kind = "csv"

    def fetch(self, config: dict[str, Any]) -> str:
        if config.get("inline"):
            return config["inline"]
        if config.get("path"):
            return Path(config["path"]).read_text(encoding=config.get("encoding", "utf-8"))
        if config.get("url"):
            response = requests.get(config["url"], timeout=config.get("timeout", 20))
            response.raise_for_status()
            return response.text
        raise ExtractionError("csv source needs one of 'inline', 'path' or 'url' in config")

    def _reader(self, raw: str, config: dict[str, Any]) -> csv.DictReader:
        delimiter = config.get("delimiter")
        if not delimiter:
            sample = raw[:4096]
            try:
                delimiter = csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
            except csv.Error:
                delimiter = ","
        return csv.DictReader(io.StringIO(raw), delimiter=delimiter)

    def extract(self, raw: str, rules: dict[str, Any], config: dict[str, Any]) -> list[dict]:
        reader = self._reader(raw, config)
        out: list[dict] = []
        for row in reader:
            record: dict[str, Any] = {}
            for name, rule in rules.items():
                column = (rule or {}).get("column")
                # A renamed column yields None for every row -- the CSV version
                # of a dead selector, and caught by the same fill-rate rule.
                record[name] = row.get(column) if column else None
            out.append(record)
        return out

    def structure_digest(self, raw: str, budget: int) -> str:
        reader = self._reader(raw, {})
        headers = reader.fieldnames or []
        sample_rows = []
        for i, row in enumerate(reader):
            if i >= 3:
                break
            sample_rows.append(row)

        lines = ["columns:"]
        for header in headers:
            values = [str(r.get(header, ""))[:40] for r in sample_rows]
            lines.append(f'  - "{header}"  e.g. {values}')
        digest = "\n".join(lines)
        return digest[:budget]
