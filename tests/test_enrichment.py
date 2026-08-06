from bs4 import BeautifulSoup

from real_estate_db.enrichment import (
    MIN_OFFICIAL_SCORE,
    _is_denied,
    assess_official_site,
    normalize_company_name,
)


def test_normalize_company_name_removes_legal_suffixes() -> None:
    assert normalize_company_name("株式会社 テスト不動産") == "テスト不動産"
    assert normalize_company_name("有限会社テスト・ハウス") == "テストハウス"
    assert normalize_company_name("司法書士法人 テスト法務") == "テスト法務"


def test_directory_and_recruiting_domains_are_denied() -> None:
    assert _is_denied("https://ja.wikipedia.org/wiki/example")
    assert _is_denied("https://wantedly.com/companies/example")
    assert _is_denied("https://recruit.example.co.jp/")
    assert not _is_denied("https://example-estate.co.jp/")


def test_official_site_requires_multiple_company_signals() -> None:
    html = """
    <html><head><title>テスト不動産株式会社｜東京都の不動産買取</title></head>
    <body>
      <h1>テスト不動産株式会社</h1>
      <p>東京都で不動産買取、土地売買を行う宅地建物取引業者です。</p>
      <a href="/company">会社概要</a>
      <a href="/contact">お問い合わせ</a>
    </body></html>
    """
    soup = BeautifulSoup(html, "html.parser")
    assessment = assess_official_site(
        "テスト不動産株式会社",
        "東京都",
        soup.get_text(" ", strip=True),
        "https://example-estate.co.jp/",
        soup,
    )
    assert assessment.score >= MIN_OFFICIAL_SCORE
    assert assessment.confidence in {"中", "高"}


def test_third_party_directory_is_rejected_even_with_company_name() -> None:
    html = """
    <html><head><title>テスト不動産株式会社の求人・口コミ</title></head>
    <body>テスト不動産株式会社 東京都 不動産 求人検索 転職 口コミ 掲載企業</body></html>
    """
    soup = BeautifulSoup(html, "html.parser")
    assessment = assess_official_site(
        "テスト不動産株式会社",
        "東京都",
        soup.get_text(" ", strip=True),
        "https://unknown-directory.example/company/1",
        soup,
    )
    assert assessment.score < MIN_OFFICIAL_SCORE
