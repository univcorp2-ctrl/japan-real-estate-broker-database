from __future__ import annotations

import argparse
import csv
import json
import logging
import math
import os
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import requests

from .build_excel import build
from .enrichment import EnrichmentResult, enrich_company, normalize_company_name
from .mlit_source import LICENSE_AUTHORITIES, RegistryCandidate, fetch_registry_page
from .schema import REQUIRED_COLUMNS
from .validate import validate_file

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "config" / "cloud_pipeline.json"
STATE_PATH = ROOT / "state" / "discovery_state.json"
MASTER_PATH = ROOT / "data" / "real_estate_brokers.csv"
QUEUE_PATH = ROOT / "data" / "research_queue.csv"
DATABASE_DIR = ROOT / "database"
REPORTS_DIR = ROOT / "reports"

QUEUE_COLUMNS = [
    "候補ID",
    "免許行政庁",
    "免許番号",
    "会社名",
    "都道府県",
    "発見日",
    "発見元URL",
    "状態",
    "試行回数",
    "最終試行日",
    "公式URL候補",
    "メモ",
]

PREFECTURE_REGION = {
    "北海道": "北海道・東北",
    "青森県": "北海道・東北",
    "岩手県": "北海道・東北",
    "宮城県": "北海道・東北",
    "秋田県": "北海道・東北",
    "山形県": "北海道・東北",
    "福島県": "北海道・東北",
    "茨城県": "関東",
    "栃木県": "関東",
    "群馬県": "関東",
    "埼玉県": "関東",
    "千葉県": "関東",
    "東京都": "関東",
    "神奈川県": "関東",
    "新潟県": "中部",
    "富山県": "中部",
    "石川県": "中部",
    "福井県": "中部",
    "山梨県": "中部",
    "長野県": "中部",
    "岐阜県": "中部",
    "静岡県": "中部",
    "愛知県": "中部",
    "三重県": "中部",
    "滋賀県": "近畿",
    "京都府": "近畿",
    "大阪府": "近畿",
    "兵庫県": "近畿",
    "奈良県": "近畿",
    "和歌山県": "近畿",
    "鳥取県": "中国・四国",
    "島根県": "中国・四国",
    "岡山県": "中国・四国",
    "広島県": "中国・四国",
    "山口県": "中国・四国",
    "徳島県": "中国・四国",
    "香川県": "中国・四国",
    "愛媛県": "中国・四国",
    "高知県": "中国・四国",
    "福岡県": "九州・沖縄",
    "佐賀県": "九州・沖縄",
    "長崎県": "九州・沖縄",
    "熊本県": "九州・沖縄",
    "大分県": "九州・沖縄",
    "宮崎県": "九州・沖縄",
    "鹿児島県": "九州・沖縄",
    "沖縄県": "九州・沖縄",
    "全国": "全国",
}


@dataclass
class RunReport:
    run_started_at: str
    run_finished_at: str = ""
    target_authority_code: int = 0
    target_authority: str = ""
    target_page: int = 1
    registry_total: int = 0
    registry_candidates_found: int = 0
    queue_added: int = 0
    master_added: int = 0
    enrichment_attempted: int = 0
    enrichment_succeeded: int = 0
    master_total_before: int = 0
    master_total_after: int = 0
    registry_error: str = ""
    warnings: list[str] | None = None


class PipelineError(RuntimeError):
    pass


def load_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return default.copy()
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_csv(path: Path, fieldnames: list[str] | None = None) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, fieldnames=fieldnames)
        return [{key: (value or "").strip() for key, value in row.items()} for row in reader]


def write_csv(path: Path, rows: list[dict[str, str]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def normalized_master_key(row: dict[str, str]) -> tuple[str, str]:
    return normalize_company_name(row.get("会社名", "")), row.get("都道府県", "")


def candidate_to_master_row(candidate: RegistryCandidate, today: str) -> dict[str, str]:
    prefecture = candidate.prefecture
    region = PREFECTURE_REGION.get(prefecture, "全国")
    priority = "A" if region == "関東" else "B"
    return {
        "会社ID": f"RE-{candidate.candidate_id}",
        "会社名": candidate.company_name,
        "地域": region,
        "都道府県": prefecture,
        "本社所在地": "要確認",
        "営業エリア": prefecture,
        "戸建て取扱": "要確認",
        "収益不動産取扱": "要確認",
        "その他取扱物件": "要確認",
        "問い合わせフォーム": "要確認",
        "公式URL": "要確認",
        "問い合わせURL": "要確認",
        "サービスURL": "要確認",
        "電話番号": "要確認",
        "特徴・強み": "国土交通省の企業情報検索システムで宅地建物取引業者登録を確認",
        "根拠URL": candidate.source_url,
        "確認日": today,
        "確認状態": "公的登録確認・公式サイト要確認",
        "優先度": priority,
        "備考": (
            f"免許行政庁: {candidate.authority}; 免許番号: 第{candidate.license_number}号; "
            f"自動追加日: {today}"
        ),
    }


def candidate_to_queue_row(candidate: RegistryCandidate, today: str) -> dict[str, str]:
    return {
        "候補ID": candidate.candidate_id,
        "免許行政庁": candidate.authority,
        "免許番号": candidate.license_number,
        "会社名": candidate.company_name,
        "都道府県": candidate.prefecture,
        "発見日": today,
        "発見元URL": candidate.source_url,
        "状態": "未調査",
        "試行回数": "0",
        "最終試行日": "",
        "公式URL候補": "",
        "メモ": "国土交通省公開検索から自動発見",
    }


def append_evidence(current: str, new_urls: list[str]) -> str:
    values = [part.strip() for part in current.split("|") if part.strip()]
    for url in new_urls:
        if url and url not in values:
            values.append(url)
    return " | ".join(values)


def apply_enrichment(row: dict[str, str], result: EnrichmentResult, today: str) -> None:
    row["公式URL"] = result.official_url
    row["問い合わせURL"] = result.inquiry_url
    row["サービスURL"] = result.service_url
    row["電話番号"] = result.phone
    row["戸建て取扱"] = result.detached
    row["収益不動産取扱"] = result.income_property
    row["その他取扱物件"] = result.other_types
    row["問い合わせフォーム"] = result.contact_form
    row["特徴・強み"] = result.summary
    row["根拠URL"] = append_evidence(row.get("根拠URL", ""), result.evidence_urls)
    row["確認日"] = today
    row["確認状態"] = "自動確認済み" if result.contact_form == "あり" else "一部自動確認"
    row["備考"] = f"{row.get('備考', '')}; 公式サイト自動確認日: {today}".strip("; ")


def next_target(config: dict[str, Any], state: dict[str, Any]) -> tuple[int, int, int]:
    schedule = [int(value) for value in config["registry_schedule"]]
    if not schedule:
        raise PipelineError("registry_schedule is empty")
    schedule_index = int(state.get("schedule_index", 0)) % len(schedule)
    authority_code = schedule[schedule_index]
    pages = state.setdefault("pages", {})
    page = max(int(pages.get(str(authority_code), 1)), 1)
    return authority_code, page, schedule_index


def advance_state(
    config: dict[str, Any],
    state: dict[str, Any],
    authority_code: int,
    page: int,
    total: int,
    schedule_index: int,
) -> None:
    page_size = int(config["registry_page_size"])
    max_page = max(math.ceil(total / page_size), 1)
    state.setdefault("pages", {})[str(authority_code)] = 1 if page >= max_page else page + 1
    state["schedule_index"] = (schedule_index + 1) % len(config["registry_schedule"])


def select_enrichment_queue(queue_rows: list[dict[str, str]], limit: int) -> list[dict[str, str]]:
    eligible = [row for row in queue_rows if row.get("状態") not in {"公式確認済み", "対象外"}]
    return sorted(
        eligible,
        key=lambda row: (
            int(row.get("試行回数") or 0),
            row.get("発見日", ""),
            row.get("候補ID", ""),
        ),
    )[:limit]


def write_report(report: RunReport) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    run_day = report.run_started_at[:10]
    report_path = REPORTS_DIR / f"{run_day}.md"
    warnings = report.warnings or []
    lines = [
        f"# クラウド日次実行レポート {run_day}",
        "",
        f"- 開始: {report.run_started_at}",
        f"- 終了: {report.run_finished_at}",
        f"- 調査対象: {report.target_authority} / ページ {report.target_page}",
        f"- 公的登録候補取得数: {report.registry_candidates_found}",
        f"- 候補キュー追加数: {report.queue_added}",
        f"- マスターDB追加数: {report.master_added}",
        f"- 公式サイト調査数: {report.enrichment_attempted}",
        f"- 公式サイト確認成功数: {report.enrichment_succeeded}",
        f"- マスターDB件数: {report.master_total_before} → {report.master_total_after}",
        f"- 公的登録検索エラー: {report.registry_error or 'なし'}",
        "",
        "## 警告",
        "",
    ]
    lines.extend(f"- {warning}" for warning in warnings)
    if not warnings:
        lines.append("- なし")
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    write_json(REPORTS_DIR / "latest.json", asdict(report))
    return report_path


def run_pipeline(
    config_path: Path = CONFIG_PATH,
    today: date | None = None,
    registry_fetcher=fetch_registry_page,
    enricher=enrich_company,
) -> RunReport:
    today = today or date.today()
    today_text = today.isoformat()
    started = datetime.now(timezone.utc).isoformat()
    config = load_json(config_path, {})
    state = load_json(
        STATE_PATH,
        {
            "schedule_index": 0,
            "pages": {},
            "last_run": None,
            "consecutive_registry_failures": 0,
            "total_auto_added": 0,
            "total_auto_enriched": 0,
        },
    )
    report = RunReport(run_started_at=started, warnings=[])
    master_rows = validate_file(MASTER_PATH)
    queue_rows = load_csv(QUEUE_PATH)
    report.master_total_before = len(master_rows)

    authority_code, page, schedule_index = next_target(config, state)
    report.target_authority_code = authority_code
    report.target_authority = LICENSE_AUTHORITIES[authority_code]
    report.target_page = page

    session = requests.Session()
    registry_candidates: list[RegistryCandidate] = []
    try:
        registry_candidates, total, _ = registry_fetcher(
            authority_code,
            page,
            int(config["registry_page_size"]),
            int(config["request_timeout_seconds"]),
            str(config["user_agent"]),
            session,
        )
        report.registry_total = total
        report.registry_candidates_found = len(registry_candidates)
        state["consecutive_registry_failures"] = 0
        advance_state(config, state, authority_code, page, total, schedule_index)
    except (requests.RequestException, ValueError, KeyError, TimeoutError) as exc:
        report.registry_error = f"{type(exc).__name__}: {exc}"
        state["consecutive_registry_failures"] = int(state.get("consecutive_registry_failures", 0)) + 1
        report.warnings.append("公的登録検索に失敗したため、既存キューの公式サイト調査とExcel生成を継続しました。")

    master_ids = {row["会社ID"] for row in master_rows}
    master_keys = {normalized_master_key(row) for row in master_rows}
    queue_ids = {row.get("候補ID", "") for row in queue_rows}
    new_limit = int(os.environ.get("DAILY_NEW_COMPANY_LIMIT", config["daily_new_company_limit"]))

    for candidate in registry_candidates:
        if report.master_added >= new_limit:
            break
        master_id = f"RE-{candidate.candidate_id}"
        master_key = (normalize_company_name(candidate.company_name), candidate.prefecture)
        if candidate.candidate_id not in queue_ids:
            queue_rows.append(candidate_to_queue_row(candidate, today_text))
            queue_ids.add(candidate.candidate_id)
            report.queue_added += 1
        if master_id in master_ids or master_key in master_keys:
            continue
        master_rows.append(candidate_to_master_row(candidate, today_text))
        master_ids.add(master_id)
        master_keys.add(master_key)
        report.master_added += 1

    enrichment_limit = int(os.environ.get("DAILY_ENRICHMENT_LIMIT", config["daily_enrichment_limit"]))
    if config.get("official_search_enabled", True):
        master_by_id = {row["会社ID"]: row for row in master_rows}
        for queue_row in select_enrichment_queue(queue_rows, enrichment_limit):
            report.enrichment_attempted += 1
            queue_row["試行回数"] = str(int(queue_row.get("試行回数") or 0) + 1)
            queue_row["最終試行日"] = today_text
            master_row = master_by_id.get(f"RE-{queue_row['候補ID']}")
            if not master_row:
                queue_row["状態"] = "マスター未登録"
                continue
            try:
                result = enricher(
                    queue_row["会社名"],
                    queue_row["都道府県"],
                    int(config["request_timeout_seconds"]),
                    str(config["user_agent"]),
                    int(config["max_response_bytes"]),
                    float(config["request_delay_seconds"]),
                    session,
                )
            except requests.RequestException as exc:
                queue_row["状態"] = "通信エラー・再試行"
                queue_row["メモ"] = f"{type(exc).__name__}: {exc}"[:500]
                continue
            if result is None:
                queue_row["状態"] = "公式サイト未特定・再試行"
                continue
            apply_enrichment(master_row, result, today_text)
            queue_row["状態"] = "公式確認済み"
            queue_row["公式URL候補"] = result.official_url
            queue_row["メモ"] = result.summary
            report.enrichment_succeeded += 1

    master_rows.sort(key=lambda row: (row.get("地域", ""), row.get("都道府県", ""), row.get("会社名", "")))
    queue_rows.sort(key=lambda row: (row.get("状態", ""), row.get("発見日", ""), row.get("候補ID", "")))
    write_csv(MASTER_PATH, master_rows, REQUIRED_COLUMNS)
    write_csv(QUEUE_PATH, queue_rows, QUEUE_COLUMNS)
    validate_file(MASTER_PATH)
    build(MASTER_PATH, DATABASE_DIR)

    state["last_run"] = started
    state["total_auto_added"] = int(state.get("total_auto_added", 0)) + report.master_added
    state["total_auto_enriched"] = int(state.get("total_auto_enriched", 0)) + report.enrichment_succeeded
    write_json(STATE_PATH, state)

    report.master_total_after = len(master_rows)
    report.run_finished_at = datetime.now(timezone.utc).isoformat()
    write_report(report)
    logging.info("cloud pipeline report: %s", json.dumps(asdict(report), ensure_ascii=False))
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Daily cloud discovery and database growth pipeline")
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        report = run_pipeline(args.config)
    except (PipelineError, ValueError, OSError, json.JSONDecodeError) as exc:
        logging.exception("pipeline failed")
        print(f"::error::{type(exc).__name__}: {exc}")
        return 1
    print(
        f"added={report.master_added} enriched={report.enrichment_succeeded} "
        f"total={report.master_total_after} registry_error={bool(report.registry_error)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
