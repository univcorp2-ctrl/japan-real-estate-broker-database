from __future__ import annotations

import re
from dataclasses import dataclass
from html import unescape
from time import sleep
from urllib.parse import parse_qs, unquote, urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

DENY_DOMAINS = {
    "suumo.jp",
    "homes.co.jp",
    "athome.co.jp",
    "yahoo.co.jp",
    "facebook.com",
    "instagram.com",
    "x.com",
    "twitter.com",
    "youtube.com",
    "mapion.co.jp",
    "itp.ne.jp",
    "townpage.goo.ne.jp",
    "houjin.jp",
    "baseconnect.in",
}

REAL_ESTATE_TERMS = ("不動産", "宅地", "売買", "仲介", "物件", "住宅", "マンション", "土地")
DETACHED_TERMS = ("戸建", "一戸建", "新築住宅", "中古住宅", "建売")
INCOME_TERMS = ("収益不動産", "投資用", "不動産投資", "一棟", "アパート経営", "賃貸経営")
CONTACT_TERMS = ("お問い合わせ", "お問合せ", "問い合わせ", "contact", "inquiry", "資料請求", "相談")
OTHER_TYPES = {
    "マンション": ("マンション",),
    "土地": ("土地", "宅地"),
    "事業用": ("事業用", "店舗", "オフィス", "ビル"),
    "賃貸管理": ("賃貸管理", "管理物件", "プロパティマネジメント"),
    "買取": ("不動産買取", "直接買取", "買取再販"),
}


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


def normalize_company_name(value: str) -> str:
    value = re.sub(r"(株式会社|有限会社|合同会社|合資会社|合名会社|一般社団法人)", "", value)
    return re.sub(r"[\s　・･（）()\-ー_]", "", value).lower()


def _candidate_tokens(company_name: str) -> list[str]:
    normalized = normalize_company_name(company_name)
    tokens = [normalized]
    for suffix in ("不動産", "住宅", "ハウス", "リアルティ", "エステート"):
        shorter = normalized.replace(suffix, "")
        if len(shorter) >= 3:
            tokens.append(shorter)
    return sorted(set(token for token in tokens if len(token) >= 3), key=len, reverse=True)


def _unwrap_search_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.netloc.endswith("duckduckgo.com"):
        target = parse_qs(parsed.query).get("uddg", [""])[0]
        if target:
            return unquote(target)
    return url


def _is_denied(url: str) -> bool:
    host = urlparse(url).netloc.lower().removeprefix("www.")
    return not host or any(host == denied or host.endswith(f".{denied}") for denied in DENY_DOMAINS)


def search_official_candidates(
    company_name: str,
    prefecture: str,
    timeout: int,
    user_agent: str,
    session: requests.Session,
    limit: int = 5,
) -> list[str]:
    query = f'"{company_name}" {prefecture} 不動産 公式'
    response = session.post(
        "https://html.duckduckgo.com/html/",
        data={"q": query},
        timeout=timeout,
        headers={"User-Agent": user_agent, "Accept-Language": "ja,en;q=0.8"},
    )
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    urls: list[str] = []
    for anchor in soup.select("a.result__a, a[href]"):
        href = _unwrap_search_url(anchor.get("href", ""))
        if not href.startswith("https://") or _is_denied(href):
            continue
        normalized = href.split("#", 1)[0]
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
            robots_url, timeout=min(timeout, 10), headers={"User-Agent": user_agent}
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
    return raw.decode(encoding, errors="replace"), response.url


def _page_matches_company(company_name: str, page_text: str) -> bool:
    compact = normalize_company_name(page_text[:250000])
    return any(token in compact for token in _candidate_tokens(company_name)) and any(
        term in page_text for term in REAL_ESTATE_TERMS
    )


def _find_contact_url(soup: BeautifulSoup, base_url: str) -> str:
    for anchor in soup.find_all("a", href=True):
        label = f"{anchor.get_text(' ', strip=True)} {anchor['href']}".lower()
        if any(term.lower() in label for term in CONTACT_TERMS):
            candidate = urljoin(base_url, anchor["href"])
            if candidate.startswith("https://"):
                return candidate
    return ""


def _extract_phone(text: str) -> str:
    match = re.search(r"(?:0\d{1,4}[-‐ー–—−]\d{1,4}[-‐ー–—−]\d{3,4}|0\d{9,10})", text)
    return match.group(0) if match else ""


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
    for candidate_url in candidate_urls:
        try:
            sleep(max(delay_seconds, 0))
            page_html, final_url = _fetch_html(
                candidate_url, timeout, user_agent, max_bytes, session
            )
        except (requests.RequestException, PermissionError, ValueError):
            continue
        soup = BeautifulSoup(page_html, "html.parser")
        text = unescape(soup.get_text(" ", strip=True))
        if not _page_matches_company(company_name, text):
            continue
        inquiry_url = _find_contact_url(soup, final_url)
        form_present = bool(soup.find("form")) or bool(inquiry_url)
        other = [name for name, terms in OTHER_TYPES.items() if any(term in text for term in terms)]
        detached = _yes_no(text, DETACHED_TERMS)
        income = _yes_no(text, INCOME_TERMS)
        summary_parts = ["公式サイトを自動確認"]
        if detached == "あり":
            summary_parts.append("戸建て取扱表記あり")
        if income == "あり":
            summary_parts.append("収益・投資用不動産表記あり")
        if form_present:
            summary_parts.append("問い合わせ導線あり")
        evidence = [final_url]
        if inquiry_url and inquiry_url != final_url:
            evidence.append(inquiry_url)
        return EnrichmentResult(
            official_url=final_url,
            inquiry_url=inquiry_url or "要確認",
            service_url=final_url,
            phone=_extract_phone(text) or "要確認",
            detached=detached,
            income_property=income,
            other_types="・".join(other) if other else "要確認",
            contact_form="あり" if form_present else "要確認",
            summary="。".join(summary_parts),
            evidence_urls=evidence,
        )
    return None
