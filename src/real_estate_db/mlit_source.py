from __future__ import annotations

import html
import re
from dataclasses import dataclass
from urllib.parse import urlencode

import requests

MLIT_REGISTRY_URL = "https://etsuran2.mlit.go.jp/TAKKEN/takkenKensaku.do"

LICENSE_AUTHORITIES = {
    0: "国土交通大臣",
    1: "北海道",
    2: "青森県",
    3: "岩手県",
    4: "宮城県",
    5: "秋田県",
    6: "山形県",
    7: "福島県",
    8: "茨城県",
    9: "栃木県",
    10: "群馬県",
    11: "埼玉県",
    12: "千葉県",
    13: "東京都",
    14: "神奈川県",
    15: "新潟県",
    16: "富山県",
    17: "石川県",
    18: "福井県",
    19: "山梨県",
    20: "長野県",
    21: "岐阜県",
    22: "静岡県",
    23: "愛知県",
    24: "三重県",
    25: "滋賀県",
    26: "京都府",
    27: "大阪府",
    28: "兵庫県",
    29: "奈良県",
    30: "和歌山県",
    31: "鳥取県",
    32: "島根県",
    33: "岡山県",
    34: "広島県",
    35: "山口県",
    36: "徳島県",
    37: "香川県",
    38: "愛媛県",
    39: "高知県",
    40: "福岡県",
    41: "佐賀県",
    42: "長崎県",
    43: "熊本県",
    44: "大分県",
    45: "宮崎県",
    46: "鹿児島県",
    47: "沖縄県",
}


@dataclass(frozen=True)
class RegistryCandidate:
    authority_code: int
    authority: str
    license_number: str
    company_name: str
    prefecture: str
    source_url: str

    @property
    def candidate_id(self) -> str:
        return f"MLIT-{self.authority_code:02d}-{self.license_number.zfill(8)}"


def build_registry_params(authority_code: int, page: int, page_size: int) -> dict[str, str | int]:
    return {
        "CMD": "selectPage",
        "caller": "TK",
        "choice": "1",
        "rdoSelect": "1",
        "rdoSelectJoken": "1",
        "rdoSelectSort": "1",
        "sortValue": "1",
        "dispCount": page_size,
        "licenseNoKbn": f"{authority_code:02d}",
        "pageCount": page,
        "pageListNo1": page,
        "pageListNo2": page,
    }


def build_registry_url(authority_code: int, page: int, page_size: int) -> str:
    return (
        f"{MLIT_REGISTRY_URL}?{urlencode(build_registry_params(authority_code, page, page_size))}"
    )


def decode_registry_response(response: requests.Response) -> str:
    response.raise_for_status()
    for encoding in (response.encoding, "cp932", "shift_jis", "utf-8"):
        if not encoding:
            continue
        try:
            return response.content.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue
    return response.content.decode("cp932", errors="replace")


def _clean_company_name(value: str) -> str:
    value = re.sub(r"<[^>]+>", "", value)
    value = html.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def parse_registry_html(
    page_html: str,
    authority_code: int,
    source_url: str,
) -> tuple[list[RegistryCandidate], int]:
    authority = LICENSE_AUTHORITIES[authority_code]
    total_match = re.search(r"検索結果[：:]\s*([0-9,]+)件", page_html)
    total = int(total_match.group(1).replace(",", "")) if total_match else 0

    compact = page_html.replace("\r", "").replace("\n", "")
    pattern = re.compile(
        r'<td[^>]*title=["\']licenseNo["\'][^>]*>.*?第\s*([0-9]+)\s*号.*?</td>'
        r'.*?onclick=["\']js_ShowDetail\([^>]+?\)["\'][^>]*>(.*?)</a>',
        re.IGNORECASE,
    )
    candidates: list[RegistryCandidate] = []
    seen: set[tuple[int, str]] = set()
    for license_number, raw_name in pattern.findall(compact):
        key = (authority_code, license_number)
        if key in seen:
            continue
        seen.add(key)
        company_name = _clean_company_name(raw_name)
        if not company_name:
            continue
        prefecture = authority if authority_code != 0 else "全国"
        candidates.append(
            RegistryCandidate(
                authority_code=authority_code,
                authority=authority,
                license_number=license_number,
                company_name=company_name,
                prefecture=prefecture,
                source_url=source_url,
            )
        )
    return candidates, total


def fetch_registry_page(
    authority_code: int,
    page: int,
    page_size: int,
    timeout: int,
    user_agent: str,
    session: requests.Session | None = None,
) -> tuple[list[RegistryCandidate], int, str]:
    session = session or requests.Session()
    params = build_registry_params(authority_code, page, page_size)
    response = session.get(
        MLIT_REGISTRY_URL,
        params=params,
        timeout=timeout,
        headers={"User-Agent": user_agent, "Accept-Language": "ja,en;q=0.8"},
    )
    page_html = decode_registry_response(response)
    candidates, total = parse_registry_html(page_html, authority_code, response.url)
    return candidates, total, response.url
