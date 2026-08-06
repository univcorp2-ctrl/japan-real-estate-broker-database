from real_estate_db.quality import (
    audit_rows,
    extract_phone_numbers,
    extract_public_emails,
    lead_grade,
    score_lead_signals,
)


def test_phone_extraction_prefers_tel_and_rejects_fax_only() -> None:
    text = "FAX 03-9999-8888 / 代表電話 TEL 03-1234-5678"
    assert extract_phone_numbers(text) == ["03-1234-5678"]


def test_public_email_extraction_keeps_role_accounts_only() -> None:
    text = "お問い合わせ info@example.co.jp 担当 yamada@example.co.jp"
    assert extract_public_emails(text, "https://www.example.co.jp/") == [
        "info@example.co.jp"
    ]


def test_public_email_can_use_published_generic_free_mailbox() -> None:
    text = "ご相談は contact@gmail.com まで"
    assert extract_public_emails(text, "https://small-estate.example/") == [
        "contact@gmail.com"
    ]


def test_lead_scoring_prioritizes_direct_acquisition_signals() -> None:
    text = "不動産買取と買取再販、用地仕入れ、相続不動産と空き家の売却相談"
    score, signals = score_lead_signals(text, has_contact=True)
    assert score >= 75
    assert lead_grade(score) == "A"
    assert "直接買取・買取再販" in signals
    assert "用地仕入れ・開発" in signals


def test_legacy_bad_url_is_warning_but_strict_mode_blocks_it() -> None:
    rows = [
        {
            "会社ID": "RE-1",
            "公式URL": "https://ja.wikipedia.org/wiki/example",
            "電話番号": "要確認",
        }
    ]
    assert audit_rows(rows)[0].severity == "warning"
    assert audit_rows(rows, strict_legacy=True)[0].severity == "error"
