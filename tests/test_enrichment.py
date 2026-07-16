from real_estate_db.enrichment import normalize_company_name


def test_normalize_company_name_removes_legal_suffixes() -> None:
    assert normalize_company_name("株式会社 テスト不動産") == "テスト不動産"
    assert normalize_company_name("有限会社テスト・ハウス") == "テストハウス"
