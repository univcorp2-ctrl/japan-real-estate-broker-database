from __future__ import annotations

import csv
from pathlib import Path
from urllib.parse import urlparse

from .schema import REQUIRED_COLUMNS, URL_COLUMNS


def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = [column for column in REQUIRED_COLUMNS if column not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"Missing columns: {', '.join(missing)}")
        return [{key: (value or "").strip() for key, value in row.items()} for row in reader]


def _valid_https_urls(value: str) -> bool:
    if not value or value == "要確認":
        return True
    for candidate in [part.strip() for part in value.split("|") if part.strip()]:
        parsed = urlparse(candidate)
        if parsed.scheme != "https" or not parsed.netloc:
            return False
    return True


def validate_rows(rows: list[dict[str, str]]) -> list[str]:
    errors: list[str] = []
    seen_ids: set[str] = set()
    for index, row in enumerate(rows, start=2):
        company_id = row.get("会社ID", "")
        if not company_id:
            errors.append(f"row {index}: 会社ID is required")
        elif company_id in seen_ids:
            errors.append(f"row {index}: duplicate 会社ID {company_id}")
        seen_ids.add(company_id)

        if not row.get("会社名"):
            errors.append(f"row {index}: 会社名 is required")
        for column in URL_COLUMNS:
            if not _valid_https_urls(row.get(column, "")):
                errors.append(f"row {index}: {column} must contain https URLs separated by |")
    return errors


def validate_file(path: Path) -> list[dict[str, str]]:
    rows = load_rows(path)
    errors = validate_rows(rows)
    if errors:
        raise ValueError("\n".join(errors))
    return rows
