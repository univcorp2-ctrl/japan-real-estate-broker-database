from __future__ import annotations

REQUIRED_COLUMNS = [
    "会社ID",
    "会社名",
    "地域",
    "都道府県",
    "本社所在地",
    "営業エリア",
    "戸建て取扱",
    "収益不動産取扱",
    "その他取扱物件",
    "問い合わせフォーム",
    "公式URL",
    "問い合わせURL",
    "サービスURL",
    "電話番号",
    "特徴・強み",
    "根拠URL",
    "確認日",
    "確認状態",
    "優先度",
    "備考",
]

ENRICHMENT_COLUMNS = [
    "事業者区分",
    "公開メールアドレス",
    "公式サイト確信度",
    "公式サイトスコア",
    "物上げ適性スコア",
    "物上げ適性シグナル",
]

MASTER_COLUMNS = REQUIRED_COLUMNS + ENRICHMENT_COLUMNS

REGION_ORDER = [
    "関東",
    "北海道・東北",
    "中部",
    "近畿",
    "中国・四国",
    "九州・沖縄",
    "全国",
]

URL_COLUMNS = ["公式URL", "問い合わせURL", "サービスURL", "根拠URL"]
SCORE_COLUMNS = ["公式サイトスコア", "物上げ適性スコア"]
