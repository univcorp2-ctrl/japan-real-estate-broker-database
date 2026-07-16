from __future__ import annotations

import argparse
import os
from pathlib import Path

import requests

from .validate import validate_file

NOTION_VERSION = "2026-03-11"


def _title(value: str) -> dict:
    return {"title": [{"text": {"content": value[:2000]}}]}


def _rich_text(value: str) -> dict:
    return {"rich_text": [{"text": {"content": value[:2000]}}]} if value else {"rich_text": []}


def _url(value: str) -> dict:
    first = next(
        (part.strip() for part in value.split("|") if part.strip().startswith("https://")), None
    )
    return {"url": first}


def row_properties(row: dict[str, str]) -> dict:
    return {
        "会社名": _title(row["会社名"]),
        "会社ID": _rich_text(row["会社ID"]),
        "地域": {"select": {"name": row["地域"]}},
        "都道府県": {"select": {"name": row["都道府県"]}},
        "営業エリア": _rich_text(row["営業エリア"]),
        "戸建て取扱": {"select": {"name": row["戸建て取扱"]}},
        "収益不動産取扱": {"select": {"name": row["収益不動産取扱"]}},
        "問い合わせフォーム": {"select": {"name": row["問い合わせフォーム"]}},
        "公式URL": _url(row["公式URL"]),
        "問い合わせURL": _url(row["問い合わせURL"]),
        "確認日": {"date": {"start": row["確認日"]}},
        "確認状態": {"select": {"name": row["確認状態"]}},
        "優先度": {"select": {"name": row["優先度"]}},
        "特徴・強み": _rich_text(row["特徴・強み"]),
        "備考": _rich_text(row["備考"]),
    }


def sync(input_path: Path, dry_run: bool = False) -> int:
    rows = validate_file(input_path)
    if dry_run:
        print(f"dry-run: {len(rows)} rows are valid")
        return len(rows)

    token = os.environ.get("NOTION_TOKEN")
    data_source_id = os.environ.get("NOTION_DATA_SOURCE_ID")
    if not token or not data_source_id:
        raise RuntimeError("NOTION_TOKEN and NOTION_DATA_SOURCE_ID are required")

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Notion-Version": NOTION_VERSION,
    }
    session = requests.Session()
    session.headers.update(headers)

    created = 0
    for row in rows:
        response = session.post(
            "https://api.notion.com/v1/pages",
            json={
                "parent": {"type": "data_source_id", "data_source_id": data_source_id},
                "properties": row_properties(row),
            },
            timeout=30,
        )
        response.raise_for_status()
        created += 1
    return created


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path("data/real_estate_brokers.csv"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(f"synced: {sync(args.input, args.dry_run)}")


if __name__ == "__main__":
    main()
