from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from html import unescape
from time import sleep
from urllib.parse import parse_qs, unquote, urljoin, urlparse, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

from .quality import (
    DENY_DOMAINS,
    extract_phone_numbers,
    extract_public_emails,
    is_denied_url,
    lead_grade,
    same_site,
    score_lead_signals,
)

REAL_ESTATE_TERMS = ("不動産", "宅地", "売買", "仲介", "物件", "住宅", "マンション", "土地")
DETACHED_TERMS = ("戸建", "一戸建", "新築住宅", "中古住宅", "建売")
INCOME_TERMS = ("収益不動産", "投資用", "不動産投資", "一棟", "アパート経営", "賃貸経営")
CONTACT_TERMS = ("お問い合わせ", "お問合せ", "問い合わせ", "contact", "inquiry", "資料請求", "相談")
COMPANY_INFO_TERMS = ("会社概要", "企業情報", "会社案内", "宅地建物取引業", "免許番号")
RECRUITMENT_TERMS = ("採用情報", "求人情報", "募集職種", "エントリー")
DIRECTORY_TERMS = ("企業データベース", "求人検索", "転職", "口コミ", "電話帳", "掲載企業")
RECRUITMENT_PATH_TERMS = ("/recruit", "/career", "/jobs", "/saiyo")
ALLOWED_FORM_DOMAINS = {
    "docs.google.com",
    "forms.gle",
    "form.run",
    "ssl.form-mailer.jp",
    "ws.formzu.net",
}
SERVICE_TERMS = (
    "不動産買取",
    "直接買取",
    "買取再販",
    "用地仕入",
    "土地仕入",
    "売却相談",
    "相続不動産",
    "空き家",
    "任意売却",
)
OTHER_TYPES = {
    "マンション": ("マンション",),
    "土地": ("土地", "宅地"),
    "事業用": ("事業用", "店舗", "オフィス", "ビル"),
    "賃貸管理": ("賃貸管理", "管理物件", "プロパティマネジメント"),
    "買取": ("不動産買取", "直接買取", "買取再販"),
}
MIN_OFFICIAL_SCORE = 70


@dataclass(frozen=True)
class OfficialSiteAssessment:
    score: int
    confidence: str
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class EnrichmentResult:
    official_url: str
    inquiry_url: str
    service_url: str
    phone: str
    detached: str
    income_property: str
    other_types: str
    contact_form: str
    summary: str
    evidence_urls: list[str]
    public_email: str = "要確認"
    official_confidence: str = ""
    official_score: int = 0
    lead_score: int = 0
    lead_grade: str = ""
    lead_signals: str = ""
    diagnostics: list[str] = field(default_factory=list)


def normalize_company_name(value: str) -> str:
    value = re.sub(
        r"(株式会社|有限会社|合同会社|合資会社|合名会社|一般社団法人|司法書士法人)",
        "",
        value,
    )
    return re.sub(r"[\s　・･（）()\-ー_]", "", value).lower()


def _candidate_tokens(company_name: str) -> list[str]:
    normalized = normalize_company_name(company_name)
    tokens = [normalized]
    for suffix in ("不動産", "住宅", "ハウス", "リアルティ", "エステート"):
        shorter = normalized.replace(suffix, "")
        if len(shorter) >= 4:
            tokens.append(shorter)
    return sorted(set(token for token in tokens if len(token) >= 3), key=len, reverse=True)


def _unwrap_search_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.netloc.endswith("duckduckgo.com"):
        target = parse_qs(parsed.query).get("uddg", [""])[0]
        if target:
            return unquote(target)
    return url


def _canonical_candidate(url: str) -> str:
    parsed = urlsplit(url)
    path = parsed.path or "/"
    if any(term in path.lower() for term in RECRUITMENT_PATH_TERMS):
        path = "/"
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def _is_denied(url: str) -> bool:
    return is_denied_url(url)


def search_official_candidates(
    company_name: str,
    prefecture: str,
    timeout: int,
    user_agent: str,
    session: requests.Session,
    limit: int = 5,
) -> list[str]:
    query = f'"{company_name}" {prefecture} 会社概要 不動産'
    response = session.post(
        "https://html.duckduckgo.com/html/",
        data={"q": query},
        timeout=timeout,
        headers={"User-Agent": user_agent, "Accept-Language": "ja,en;q=0.8"},
    )
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    urls: list[str] = []
    for anchor in soup.select("a.result__a"):
        href = _unwrap_search_url(anchor.get("href", ""))
        if not href.startswith("https://") or _is_denied(href):
            continue
        normalized = _canonical_candidate(href)
        if normalized not in urls:
            urls.append(normalized)
        if len(urls) >= limit:
            break
    return urls


def _robots_allowed(url: str, user_agent: str, timeout: int, session: requests.Session) -> bool:
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    try:
        response = session.get(
            robots_url,
            timeout=min(timeout, 10),
            headers={"User-Agent": user_agent},
        )
        if response.status_code >= 400:
            return True
        parser = RobotFileParser()
        parser.set_url(robots_url)
        parser.parse(response.text.splitlines())
        return parser.can_fetch(user_agent, url)
    except requests.RequestException:
        return True


def _fetch_html(
    url: str,
    timeout: int,
    user_agent: str,
    max_bytes: int,
    session: requests.Session,
) -> tuple[str, str]:
    if not _robots_allowed(url, user_agent, timeout, session):
        raise PermissionError(f"robots.txt disallows: {url}")
    response = session.get(
        url,
        timeout=timeout,
        headers={"User-Agent": user_agent, "Accept-Language": "ja,en;q=0.8"},
        allow_redirects=True,
        stream=True,
    )
    response.raise_for_status()
    if not response.url.startswith("https://") or _is_denied(response.url):
        raise ValueError(f"unsafe final URL: {response.url}")
    content_type = response.headers.get("Content-Type", "")
    if "text/html" not in content_type and "application/xhtml" not in content_type:
        raise ValueError(f"not HTML: {content_type}")
    chunks: list[bytes] = []
    size = 0
    for chunk in response.iter_content(65536):
        size += len(chunk)
        if size > max_bytes:
            raise ValueError("response exceeds configured byte limit")
        chunks.append(chunk)
    raw = b"".join(chunks)
    encoding = response.encoding or response.apparent_encoding or "utf-8"
    return raw.decode(encoding, errors="replace"), _canonical_candidate(response.url)


def _json_ld_names(soup: BeautifulSoup) -> list[str]:
    names: list[str] = []

    def visit(value: object) -> None:
        if isinstance(value, dict):
            name = value.get("name")
            if isinstance(name, str):
                names.append(name)
            for nested in value.values():
                visit(nested)
        elif isinstance(value, list):
            for nested in value:
                visit(nested)

    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            visit(json.loads(script.get_text(strip=True)))
        except (json.JSONDecodeError, TypeError):
            continue
    return names


def _has_contact_form(soup: BeautifulSoup) -> bool:
    for form in soup.find_all("form"):
        label = " ".join(
            [
                form.get_text(" ", strip=True),
                str(form.get("action", "")),
                str(form.get("id", "")),
                " ".join(form.get("class", [])),
            ]
        ).lower()
        if any(term.lower() in label for term in CONTACT_TERMS):
            return True
    return False


def assess_official_site(
    company_name: str,
    prefecture: str,
    page_text: str,
    url: str,
    soup: BeautifulSoup,
) -> OfficialSiteAssessment:
    if _is_denied(url):
        return OfficialSiteAssessment(0, "低", ("拒否ドメイン",))

    normalized_name = normalize_company_name(company_name)
    compact_text = normalize_company_name(page_text[:250000])
    if not normalized_name or normalized_name not in compact_text:
        return OfficialSiteAssessment(0, "低", ("会社名完全一致なし",))

    score = 35
    reasons = ["本文会社名一致"]
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    if normalized_name in normalize_company_name(title):
        score += 20
        reasons.append("タイトル会社名一致")
    if any(normalized_name in normalize_company_name(name) for name in _json_ld_names(soup)):
        score += 20
        reasons.append("構造化データ会社名一致")
    if any(term in page_text for term in REAL_ESTATE_TERMS):
        score += 10
        reasons.append("不動産事業表記")
    if prefecture and prefecture in page_text:
        score += 5
        reasons.append("都道府県一致")
    if any(term in page_text for term in COMPANY_INFO_TERMS):
        score += 5
        reasons.append("会社概要表記")
    if _find_contact_url(soup, url) or _has_contact_form(soup):
        score += 10
        reasons.append("問い合わせ導線")
    if urlparse(url).path in {"", "/"}:
        score += 5
        reasons.append("ルートページ")
    if any(term in page_text for term in DIRECTORY_TERMS):
        score -= 35
        reasons.append("第三者ディレクトリ表記")
    if any(term in page_text for term in RECRUITMENT_TERMS) and not any(
        term in page_text for term in COMPANY_INFO_TERMS
    ):
        score -= 25
        reasons.append("採用ページ偏重")

    score = max(0, min(score, 100))
    confidence = "高" if score >= 85 else "中" if score >= MIN_OFFICIAL_SCORE else "低"
    return OfficialSiteAssessment(score, confidence, tuple(reasons))


def _page_matches_company(company_name: str, page_text: str) -> bool:
    compact = normalize_company_name(page_text[:250000])
    return any(token in compact for token in _candidate_tokens(company_name)) and any(
        term in page_text for term in REAL_ESTATE_TERMS
    )


def _allowed_contact_target(candidate: str, base_url: str) -> bool:
    host = (urlparse(candidate).hostname or "").lower().removeprefix("www.")
    return same_site(candidate, base_url) or host in ALLOWED_FORM_DOMAINS


def _find_contact_url(soup: BeautifulSoup, base_url: str) -> str:
    ranked: list[tuple[int, str]] = []
    for anchor in soup.find_all("a", href=True):
        label = f"{anchor.get_text(' ', strip=True)} {anchor['href']}".lower()
        matches = [term for term in CONTACT_TERMS if term.lower() in label]
        if not matches:
            continue
        candidate = _canonical_candidate(urljoin(base_url, anchor["href"]))
        if not candidate.startswith("https://") or not _allowed_contact_target(candidate, base_url):
            continue
        score = max(len(term) for term in matches)
        ranked.append((score, candidate))
    return max(ranked, default=(0, ""), key=lambda item: item[0])[1]


def _find_service_url(soup: BeautifulSoup, base_url: str) -> str:
    ranked: list[tuple[int, str]] = []
    for anchor in soup.find_all("a", href=True):
        label = f"{anchor.get_text(' ', strip=True)} {anchor['href']}"
        matches = [term for term in SERVICE_TERMS if term in label]
        if not matches:
            continue
        candidate = _canonical_candidate(urljoin(base_url, anchor["href"]))
        if candidate.startswith("https://") and same_site(candidate, base_url):
            ranked.append((max(len(term) for term in matches), candidate))
    return max(ranked, default=(0, ""), key=lambda item: item[0])[1]


def _extract_phone(text: str) -> str:
    values = extract_phone_numbers(text)
    return values[0] if values else ""


def _yes_no(text: str, terms: tuple[str, ...]) -> str:
    return "あり" if any(term in text for term in terms) else "要確認"


def enrich_company(
    company_name: str,
    prefecture: str,
    timeout: int,
    user_agent: str,
    max_bytes: int,
    delay_seconds: float,
    session: requests.Session | None = None,
) -> EnrichmentResult | None:
    session = session or requests.Session()
    candidate_urls = search_official_candidates(
        company_name,
        prefecture,
        timeout,
        user_agent,
        session,
    )
    diagnostics: list[str] = []
    for candidate_url in candidate_urls:
        try:
            sleep(max(delay_seconds, 0))
            page_html, final_url = _fetch_html(
                candidate_url,
                timeout,
                user_agent,
                max_bytes,
                session,
            )
        except (requests.RequestException, PermissionError, ValueError) as exc:
            diagnostics.append(f"{candidate_url}: {type(exc).__name__}")
            continue

        soup = BeautifulSoup(page_html, "html.parser")
        text = unescape(soup.get_text(" ", strip=True))
        assessment = assess_official_site(company_name, prefecture, text, final_url, soup)
        if assessment.score < MIN_OFFICIAL_SCORE:
            diagnostics.append(f"{final_url}: official score {assessment.score}")
            continue

        inquiry_url = _find_contact_url(soup, final_url)
        service_url = _find_service_url(soup, final_url) or final_url
        evidence = [final_url]
        combined_text = text
        contact_soup: BeautifulSoup | None = None

        if inquiry_url and same_site(inquiry_url, final_url) and inquiry_url != final_url:
            try:
                sleep(max(delay_seconds, 0))
                contact_html, contact_final_url = _fetch_html(
                    inquiry_url,
                    timeout,
                    user_agent,
                    max_bytes,
                    session,
                )
                contact_soup = BeautifulSoup(contact_html, "html.parser")
                combined_text = f"{combined_text} {unescape(contact_soup.get_text(' ', strip=True))}"
                inquiry_url = contact_final_url
                evidence.append(contact_final_url)
            except (requests.RequestException, PermissionError, ValueError):
                pass
        elif inquiry_url:
            evidence.append(inquiry_url)

        if service_url not in evidence:
            evidence.append(service_url)
        form_present = bool(inquiry_url) or _has_contact_form(soup)
        if contact_soup is not None:
            form_present = form_present or bool(contact_soup.find("form"))

        public_emails = extract_public_emails(combined_text, final_url)
        public_email = public_emails[0] if public_emails else "要確認"
        lead_score_value, lead_signals = score_lead_signals(combined_text, form_present)
        grade = lead_grade(lead_score_value)
        other = [name for name, terms in OTHER_TYPES.items() if any(term in combined_text for term in terms)]
        detached = _yes_no(combined_text, DETACHED_TERMS)
        income = _yes_no(combined_text, INCOME_TERMS)

        summary_parts = [
            f"公式サイト自動確認（確信度{assessment.confidence}・{assessment.score}点）"
        ]
        if detached == "あり":
            summary_parts.append("戸建て取扱表記あり")
        if income == "あり":
            summary_parts.append("収益・投資用不動産表記あり")
        if form_present:
            summary_parts.append("問い合わせ導線あり")
        if public_email != "要確認":
            summary_parts.append(f"公開法人メール: {public_email}")
        if lead_signals:
            summary_parts.append(
                f"物上げ適性{grade}（{lead_score_value}点: {'・'.join(lead_signals)}）"
            )

        return EnrichmentResult(
            official_url=final_url,
            inquiry_url=inquiry_url or "要確認",
            service_url=service_url,
            phone=_extract_phone(combined_text) or "要確認",
            detached=detached,
            income_property=income,
            other_types="・".join(other) if other else "要確認",
            contact_form="あり" if form_present else "要確認",
            summary="。".join(summary_parts),
            evidence_urls=evidence,
            public_email=public_email,
            official_confidence=assessment.confidence,
            official_score=assessment.score,
            lead_score=lead_score_value,
            lead_grade=grade,
            lead_signals="・".join(lead_signals),
            diagnostics=diagnostics,
        )
    return None
