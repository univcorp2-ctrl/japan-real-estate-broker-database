from pathlib import Path

from real_estate_db.validate import validate_file, validate_rows


def test_master_data_is_valid() -> None:
    rows = validate_file(Path("data/real_estate_brokers.csv"))
    assert len(rows) >= 20
    assert any(row["地域"] == "関東" for row in rows)
    assert any(row["地域"] == "北海道・東北" for row in rows)
    assert any(row["地域"] == "九州・沖縄" for row in rows)


def test_duplicate_id_is_rejected() -> None:
    row = {
        "会社ID": "X",
        "会社名": "test",
        "公式URL": "https://example.com",
        "問い合わせURL": "https://example.com/contact",
        "サービスURL": "https://example.com/service",
        "根拠URL": "https://example.com",
    }
    errors = validate_rows([row, row])
    assert any("duplicate" in error for error in errors)
