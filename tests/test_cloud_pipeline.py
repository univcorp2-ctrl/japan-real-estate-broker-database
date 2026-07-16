import csv
import json
from datetime import date
from pathlib import Path

from real_estate_db import cloud_pipeline
from real_estate_db.enrichment import EnrichmentResult
from real_estate_db.mlit_source import RegistryCandidate
from real_estate_db.schema import REQUIRED_COLUMNS


def _write_master(path: Path) -> None:
    row = {column: "要確認" for column in REQUIRED_COLUMNS}
    row.update(
        {
            "会社ID": "RE-BASE",
            "会社名": "既存不動産株式会社",
            "地域": "関東",
            "都道府県": "東京都",
            "公式URL": "https://example.com",
            "根拠URL": "https://example.com",
            "確認日": "2026-07-15",
        }
    )
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REQUIRED_COLUMNS)
        writer.writeheader()
        writer.writerow(row)


def test_candidate_to_master_has_public_source_link() -> None:
    candidate = RegistryCandidate(
        13, "東京都", "123", "新規不動産", "東京都", "https://example.test/mlit"
    )
    row = cloud_pipeline.candidate_to_master_row(candidate, "2026-07-16")
    assert row["会社ID"] == "RE-MLIT-13-00000123"
    assert row["根拠URL"] == "https://example.test/mlit"
    assert row["確認状態"] == "公的登録確認・公式サイト要確認"
    assert row["優先度"] == "A"


def test_apply_enrichment_updates_hyperlinks() -> None:
    row = {column: "要確認" for column in REQUIRED_COLUMNS}
    row["根拠URL"] = "https://example.test/mlit"
    result = EnrichmentResult(
        official_url="https://company.example/",
        inquiry_url="https://company.example/contact",
        service_url="https://company.example/house",
        phone="03-1234-5678",
        detached="あり",
        income_property="あり",
        other_types="マンション・土地",
        contact_form="あり",
        summary="公式サイトを自動確認",
        evidence_urls=["https://company.example/", "https://company.example/contact"],
    )
    cloud_pipeline.apply_enrichment(row, result, "2026-07-16")
    assert row["公式URL"] == "https://company.example/"
    assert row["問い合わせフォーム"] == "あり"
    assert "https://example.test/mlit" in row["根拠URL"]
    assert "https://company.example/contact" in row["根拠URL"]


def test_next_target_rotates_weighted_schedule(tmp_path: Path) -> None:
    config = {"registry_schedule": [13, 14, 13], "registry_page_size": 50}
    state = {"schedule_index": 1, "pages": {"14": 3}}
    authority, page, index = cloud_pipeline.next_target(config, state)
    assert (authority, page, index) == (14, 3, 1)
    cloud_pipeline.advance_state(config, state, authority, page, 200, index)
    assert state["schedule_index"] == 2
    assert state["pages"]["14"] == 4


def test_pipeline_adds_and_enriches_with_mocked_network(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path
    (root / "data").mkdir()
    (root / "state").mkdir()
    (root / "database").mkdir()
    (root / "reports").mkdir()
    (root / "config").mkdir()
    master = root / "data" / "real_estate_brokers.csv"
    queue = root / "data" / "research_queue.csv"
    state = root / "state" / "discovery_state.json"
    config = root / "config" / "cloud_pipeline.json"
    _write_master(master)
    queue.write_text(",".join(cloud_pipeline.QUEUE_COLUMNS) + "\n", encoding="utf-8")
    state.write_text(
        json.dumps(
            {"schedule_index": 0, "pages": {}, "total_auto_added": 0, "total_auto_enriched": 0}
        ),
        encoding="utf-8",
    )
    config.write_text(
        json.dumps(
            {
                "daily_new_company_limit": 2,
                "daily_enrichment_limit": 2,
                "registry_page_size": 50,
                "request_timeout_seconds": 1,
                "request_delay_seconds": 0,
                "max_response_bytes": 1000,
                "registry_schedule": [13],
                "official_search_enabled": True,
                "user_agent": "test",
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(cloud_pipeline, "MASTER_PATH", master)
    monkeypatch.setattr(cloud_pipeline, "QUEUE_PATH", queue)
    monkeypatch.setattr(cloud_pipeline, "STATE_PATH", state)
    monkeypatch.setattr(cloud_pipeline, "DATABASE_DIR", root / "database")
    monkeypatch.setattr(cloud_pipeline, "REPORTS_DIR", root / "reports")

    candidate = RegistryCandidate(
        13, "東京都", "123", "新規不動産", "東京都", "https://example.test/mlit"
    )

    def registry_fetcher(*args, **kwargs):
        return [candidate], 1, candidate.source_url

    result = EnrichmentResult(
        official_url="https://new.example/",
        inquiry_url="https://new.example/contact",
        service_url="https://new.example/",
        phone="03-1111-2222",
        detached="あり",
        income_property="あり",
        other_types="土地",
        contact_form="あり",
        summary="公式サイトを自動確認",
        evidence_urls=["https://new.example/"],
    )

    def enricher(*args, **kwargs):
        return result

    report = cloud_pipeline.run_pipeline(config, date(2026, 7, 16), registry_fetcher, enricher)
    assert report.master_added == 1
    assert report.enrichment_succeeded == 1
    assert report.master_total_after == 2
    assert (root / "database" / "real_estate_brokers.xlsx").exists()
    assert (root / "reports" / "2026-07-16.md").exists()
