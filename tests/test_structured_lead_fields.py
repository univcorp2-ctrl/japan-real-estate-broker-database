from real_estate_db import cloud_pipeline
from real_estate_db.enrichment import EnrichmentResult
from real_estate_db.schema import MASTER_COLUMNS


def test_master_columns_include_contact_and_lead_intelligence() -> None:
    assert "公開メールアドレス" in MASTER_COLUMNS
    assert "公式サイト確信度" in MASTER_COLUMNS
    assert "物上げ適性スコア" in MASTER_COLUMNS
    assert "物上げ適性シグナル" in MASTER_COLUMNS


def test_apply_enrichment_persists_structured_lead_fields() -> None:
    row = {column: "" for column in MASTER_COLUMNS}
    result = EnrichmentResult(
        official_url="https://company.example/",
        inquiry_url="https://company.example/contact",
        service_url="https://company.example/buy",
        phone="03-1234-5678",
        detached="あり",
        income_property="あり",
        other_types="買取・土地",
        contact_form="あり",
        summary="公式サイト自動確認",
        evidence_urls=["https://company.example/"],
        public_email="info@company.example",
        official_confidence="高",
        official_score=95,
        lead_score=80,
        lead_grade="A",
        lead_signals="直接買取・買取再販・用地仕入れ・開発",
    )
    cloud_pipeline.apply_enrichment(row, result, "2026-08-06")
    assert row["公開メールアドレス"] == "info@company.example"
    assert row["公式サイトスコア"] == "95"
    assert row["物上げ適性スコア"] == "80"
    assert row["優先度"] == "A"


def test_quarantine_resets_legacy_directory_url_and_requeues() -> None:
    row = {column: "" for column in MASTER_COLUMNS}
    row.update(
        {
            "会社ID": "RE-MLIT-13-00000001",
            "会社名": "テスト不動産",
            "公式URL": "https://ja.wikipedia.org/wiki/example",
            "問い合わせURL": "https://ja.wikipedia.org/wiki/example#contact",
            "サービスURL": "https://ja.wikipedia.org/wiki/example",
            "電話番号": "要確認",
            "確認状態": "自動確認済み",
        }
    )
    queue = [{"候補ID": "MLIT-13-00000001", "状態": "公式確認済み", "メモ": ""}]
    count = cloud_pipeline.quarantine_legacy_rows([row], queue)
    assert count == 1
    assert row["公式URL"] == "要確認"
    assert row["確認状態"] == "品質再確認待ち"
    assert queue[0]["状態"] == "品質再確認待ち"
