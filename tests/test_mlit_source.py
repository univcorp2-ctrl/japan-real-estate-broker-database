from pathlib import Path

from real_estate_db.mlit_source import build_registry_params, parse_registry_html


def test_build_registry_params() -> None:
    params = build_registry_params(13, 2, 50)
    assert params["licenseNoKbn"] == "13"
    assert params["pageCount"] == 2
    assert params["dispCount"] == 50


def test_parse_registry_html() -> None:
    page_html = Path("tests/fixtures/mlit_registry_sample.html").read_text(encoding="utf-8")
    candidates, total = parse_registry_html(page_html, 13, "https://example.test/source")
    assert total == 2
    assert [candidate.license_number for candidate in candidates] == ["12345", "67890"]
    assert candidates[0].company_name == "株式会社テスト不動産"
    assert candidates[0].prefecture == "東京都"
    assert candidates[0].candidate_id == "MLIT-13-00012345"
