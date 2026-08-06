from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from urllib.parse import urlparse

DENY_DOMAINS = frozenset(
    {
        "wikipedia.org",
        "wikidata.org",
        "suumo.jp",
        "homes.co.jp",
        "athome.co.jp",
        "yahoo.co.jp",
        "facebook.com",
        "instagram.com",
        "linkedin.com",
        "tiktok.com",
        "x.com",
        "twitter.com",
        "youtube.com",
        "mapion.co.jp",
        "mapfan.com",
        "navitime.co.jp",
        "ekiten.jp",
        "itp.ne.jp",
        "townpage.goo.ne.jp",
        "jpnumber.com",
        "telnavi.jp",
        "houjin.jp",
        "baseconnect.in",
        "salesnow.jp",
        "alarmbox.jp",
        "buffett-code.com",
        "b-mall.ne.jp",
        "prtimes.jp",
        "wantedly.com",
        "en-gage.net",
        "indeed.com",
        "doda.jp",
        "rikunabi.com",
        "mynavi.jp",
        "townwork.net",
        "baitoru.com",
        "green-japan.com",
        "openwork.jp",
        "jobtalk.jp",
        "duckduckgo.com",
        "gbiz.go.jp",
        "nta.go.jp",
        "mlit.go.jp",
    }
)
DENY_HOST_LABELS = frozenset({"recruit", "saiyo", "career", "jobs"})
FREE_EMAIL_DOMAINS = frozenset(
    {
        "gmail.com",
        "yahoo.co.jp",
        "outlook.com",
        "hotmail.com",
        "icloud.com",
    }
)
PUBLIC_EMAIL_PREFIXES = (
    "info",
    "contact",
    "inquiry",
    "support",
    "office",
    "sales",
    "eigyo",
    "soudan",
    "customer",
    "reception",
    "webmaster",
    "mail",
    "soumu",
    "general",
)
SENTINEL_VALUES = frozenset({"", "要確認", "なし", "不明"})
EMAIL_RE = re.compile(
    r"(?<![\w.+-])([A-Z0-9._%+-]{1,64})@([A-Z0-9.-]+\.[A-Z]{2,24})(?![\w.-])",
    re.IGNORECASE,
)
PHONE_CANDIDATE_RE = re.compile(r"(?<!\d)(0\d{1,4}(?:[\s\-‐‑‒–—―ー−]*\d{1,4}){1,2})(?!\d)")

LEAD_SIGNAL_GROUPS: tuple[tuple[str, int, tuple[str, ...]], ...] = (
    (
        "直接買取・買取再販",
        35,
        ("不動産買取", "直接買取", "即時買取", "買取再販", "当社買取", "自社買取"),
    ),
    (
        "用地仕入れ・開発",
        25,
        ("用地仕入", "土地仕入", "物件仕入", "仕入物件", "開発用地", "事業用地", "用地募集"),
    ),
    (
        "売主・オーナー直結",
        15,
        ("売主様", "売却物件募集", "売却相談", "オーナー様向け", "所有者様", "無料査定"),
    ),
    (
        "相続・空き家",
        15,
        ("相続不動産", "相続登記", "空き家", "遺産整理", "任意売却", "成年後見"),
    ),
    (
        "難あり・権利調整",
        10,
        ("底地", "借地", "共有持分", "再建築不可", "事故物件", "訳あり物件", "競売"),
    ),
    (
        "士業・業者連携",
        10,
        (
            "司法書士",
            "土地家屋調査士",
            "税理士",
            "弁護士",
            "不動産会社様向け",
            "業者様向け",
        ),
    ),
)


@dataclass(frozen=True)
class DataQualityIssue:
    row_number: int
    company_id: str
    field: str
    severity: str
    message: str


def normalize_host(value: str) -> str:
    host = urlparse(value).hostname or ""
    return host.lower().removeprefix("www.").rstrip(".")


def _registrable_hint(host: str) -> str:
    labels = [label for label in host.split(".") if label]
    if len(labels) <= 2:
        return ".".join(labels)
    if ".".join(labels[-2:]) in {"co.jp", "ne.jp", "or.jp", "go.jp", "ac.jp"}:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def same_site(first_url: str, second_url: str) -> bool:
    first = normalize_host(first_url)
    second = normalize_host(second_url)
    return bool(first and second and _registrable_hint(first) == _registrable_hint(second))


def is_denied_url(url: str) -> bool:
    host = normalize_host(url)
    if not host:
        return True
    if any(host == denied or host.endswith(f".{denied}") for denied in DENY_DOMAINS):
        return True
    first_label = host.split(".", 1)[0]
    return first_label in DENY_HOST_LABELS


def normalize_phone(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).strip()
    normalized = re.sub(r"[‐‑‒–—―ー−]", "-", normalized)
    digits = re.sub(r"\D", "", normalized)
    if digits.startswith("81") and len(digits) in {11, 12}:
        digits = f"0{digits[2:]}"
    if len(digits) not in {10, 11} or not digits.startswith("0"):
        return ""
    if len(set(digits)) <= 2:
        return ""
    if "-" in normalized:
        cleaned = re.sub(r"[^0-9-]", "", normalized)
        cleaned = re.sub(r"-+", "-", cleaned).strip("-")
        if re.sub(r"\D", "", cleaned).endswith(digits):
            return cleaned
    return digits


def is_valid_japanese_phone(value: str) -> bool:
    return bool(normalize_phone(value))


def extract_phone_numbers(text: str) -> list[str]:
    normalized_text = unicodedata.normalize("NFKC", text)
    found: list[tuple[int, str]] = []
    seen: set[str] = set()
    for match in PHONE_CANDIDATE_RE.finditer(normalized_text):
        phone = normalize_phone(match.group(1))
        if not phone or phone in seen:
            continue
        context = normalized_text[max(0, match.start() - 20) : match.start()].lower()
        if "fax" in context and not any(term in context for term in ("tel", "電話")):
            continue
        priority = 0 if any(term in context for term in ("tel", "電話", "代表")) else 1
        found.append((priority, phone))
        seen.add(phone)
    return [phone for _, phone in sorted(found, key=lambda item: item[0])]


def _is_public_local_part(local_part: str) -> bool:
    local = local_part.lower()
    return any(
        local == prefix or local.startswith(f"{prefix}.") or local.startswith(f"{prefix}-")
        for prefix in PUBLIC_EMAIL_PREFIXES
    )


def is_public_business_email(email: str, site_url: str = "") -> bool:
    match = EMAIL_RE.fullmatch(email.strip())
    if not match:
        return False
    local, domain = match.group(1).lower(), match.group(2).lower()
    if not _is_public_local_part(local):
        return False
    if any(token in local for token in ("noreply", "no-reply", "privacy")):
        return False
    if not site_url or domain in FREE_EMAIL_DOMAINS:
        return True
    site_host = normalize_host(site_url)
    return bool(site_host and _registrable_hint(domain) == _registrable_hint(site_host))


def extract_public_emails(text: str, site_url: str) -> list[str]:
    normalized = unicodedata.normalize("NFKC", text)
    normalized = re.sub(r"\s*(?:\[at\]|\(at\)|＠)\s*", "@", normalized, flags=re.IGNORECASE)
    emails: list[str] = []
    for match in EMAIL_RE.finditer(normalized):
        email = f"{match.group(1)}@{match.group(2)}".lower()
        if email not in emails and is_public_business_email(email, site_url):
            emails.append(email)
    return emails


def score_lead_signals(text: str, has_contact: bool) -> tuple[int, list[str]]:
    normalized = unicodedata.normalize("NFKC", text).lower()
    score = 0
    signals: list[str] = []
    for label, weight, terms in LEAD_SIGNAL_GROUPS:
        if any(term.lower() in normalized for term in terms):
            score += weight
            signals.append(label)
    if has_contact:
        score += 5
        signals.append("問い合わせ導線")
    return min(score, 100), signals


def lead_grade(score: int) -> str:
    if score >= 60:
        return "A"
    if score >= 35:
        return "B"
    return "C"


def audit_rows(
    rows: list[dict[str, str]],
    *,
    strict_legacy: bool = False,
) -> list[DataQualityIssue]:
    issues: list[DataQualityIssue] = []
    for row_number, row in enumerate(rows, start=2):
        company_id = row.get("会社ID", "")
        confidence = row.get("公式サイト確信度", "")
        severity = "error" if confidence or strict_legacy else "warning"

        official_url = row.get("公式URL", "")
        if official_url not in SENTINEL_VALUES:
            for candidate in [part.strip() for part in official_url.split("|") if part.strip()]:
                if is_denied_url(candidate):
                    issues.append(
                        DataQualityIssue(
                            row_number,
                            company_id,
                            "公式URL",
                            severity,
                            f"第三者・求人・公的ディレクトリの可能性: {candidate}",
                        )
                    )

        phone = row.get("電話番号", "")
        if phone not in SENTINEL_VALUES and not is_valid_japanese_phone(phone):
            issues.append(
                DataQualityIssue(
                    row_number,
                    company_id,
                    "電話番号",
                    severity,
                    f"日本の電話番号として不正: {phone}",
                )
            )

        email = row.get("公開メールアドレス", "")
        if email not in SENTINEL_VALUES and not is_public_business_email(email, official_url):
            issues.append(
                DataQualityIssue(
                    row_number,
                    company_id,
                    "公開メールアドレス",
                    "error",
                    f"法人窓口メールとして検証できない: {email}",
                )
            )

        for field in ("公式サイトスコア", "物上げ適性スコア"):
            value = row.get(field, "")
            if value in SENTINEL_VALUES:
                continue
            try:
                numeric = int(value)
            except ValueError:
                numeric = -1
            if not 0 <= numeric <= 100:
                issues.append(
                    DataQualityIssue(
                        row_number,
                        company_id,
                        field,
                        "error",
                        f"0から100の整数ではない: {value}",
                    )
                )
    return issues
