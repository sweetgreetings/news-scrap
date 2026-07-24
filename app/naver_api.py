# Design Ref: PRD.md 기능1 규칙 2 — 등록된 키워드 중 하나라도 포함되면 수집(OR 조건), 건수 제한 없음, 당일 기사만
import html
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Optional
from urllib.parse import urlparse

import requests

from app.config import NAVER_CLIENT_ID, NAVER_CLIENT_SECRET

NAVER_NEWS_API_URL = "https://openapi.naver.com/v1/search/news.json"
_MAX_DISPLAY = 100  # 네이버 API가 허용하는 1회 요청 최대 건수
_MAX_START = 1000  # 네이버 API가 허용하는 최대 조회 시작 위치 (이 이상은 API 자체가 지원 안 함)

_TAG_PATTERN = re.compile(r"</?b>")

# PRD.md 기능1 규칙 2 — "당일"은 한국 시간(KST) 기준. 네이버 API의 pubDate도 항상 KST(+0900)로
# 내려오므로, 실행 서버의 시스템 시간대와 무관하게 KST로 고정해 비교한다.
_KST = timezone(timedelta(hours=9))

# PRD.md 기능1 규칙 3의 언론사 우선순위 (방송사 -> 주요 언론사 순). 이 순서 자체가
# app.sorter.sort_by_outlet_priority의 우선순위로도 재사용되므로 순서를 바꾸지 말 것 —
# 새 언론사를 추가할 땐 우선순위상 맞는 위치에 끼워 넣는다.
PRIORITY_OUTLETS = (
    "KBS",
    "MBC",
    "조선일보",
    "중앙일보",
    "동아일보",
    "한국경제",
    "매일경제",
    "서울경제",
    "한국일보",
    "머니투데이",
    "이데일리",
    "연합뉴스",
    "뉴시스",
)

# 위 우선순위 언론사를 URL 도메인으로 식별하기 위한 매핑 (한 언론사가 도메인을 여러
# 개 쓸 수 있어 값에 중복이 있을 수 있다). 네이버 뉴스 검색 API는 언론사명을 직접
# 내려주지 않아 도메인으로 추정한다.
OUTLET_DOMAINS = {
    "kbs.co.kr": "KBS",
    "imnews.imbc.com": "MBC",
    "mbc.co.kr": "MBC",
    "mbn.co.kr": "MBN",
    "news.sbs.co.kr": "SBS",
    "ytn.co.kr": "YTN",
    "khan.co.kr": "경향신문",
    "kmib.co.kr": "국민일보",
    "naeil.com": "내일신문",
    "donga.com": "동아일보",
    "munhwa.com": "문화일보",
    "seoul.co.kr": "서울신문",
    "segye.com": "세계일보",
    "asiatoday.co.kr": "아시아투데이",
    "chosun.com": "조선일보",
    "joongang.co.kr": "중앙일보",
    "joins.com": "중앙일보",
    "hani.co.kr": "한겨레",
    "hankookilbo.com": "한국일보",
    "mk.co.kr": "매일경제",
    "mt.co.kr": "머니투데이",
    "sedaily.com": "서울경제",
    "asiae.co.kr": "아시아경제",
    "edaily.co.kr": "이데일리",
    "fnnews.com": "파이낸셜뉴스",
    "hankyung.com": "한국경제",
    "heraldcorp.com": "헤럴드경제",
    "koreajoongangdaily.joins.com": "코리아중앙데일리",
    "koreatimes.co.kr": "코리아타임스",
    "koreaherald.com": "코리아헤럴드",
    "etnews.com": "전자신문",
    "dt.co.kr": "디지털타임스",
    "yna.co.kr": "연합뉴스",
    "newsis.com": "뉴시스",
    "news1.kr": "뉴스1",
    "pressian.com": "프레시안",
    "dailian.co.kr": "데일리안",
    "imaeil.com": "매일신문",
}

# 설정 화면의 "언론사 선택" 카테고리별 목록 (PRD.md 기능1 규칙 16). 사용자가 준 순서를 그대로 따른다.
# OBS·이투데이·내일신문은 사용자 요청으로 목록에서 제외됨. [수정: 2026-07-23] 순서 갱신.
OUTLET_CATEGORIES = {
    "방송사": ("KBS", "MBC", "SBS", "YTN", "MBN"),
    "전국종합일간": (
        "조선일보", "동아일보", "중앙일보", "문화일보", "한국일보", "서울신문",
        "세계일보", "경향신문", "한겨레", "국민일보", "아시아투데이",
    ),
    "경제일간": (
        "매일경제", "한국경제", "머니투데이", "이데일리",
        "서울경제", "파이낸셜뉴스", "헤럴드경제", "아시아경제",
    ),
    "영자일간": ("코리아중앙데일리", "코리아타임스", "코리아헤럴드"),
    "통신사": ("연합뉴스", "뉴시스", "뉴스1"),
    "전문일간": ("전자신문", "디지털타임스"),
    "기타 언론사": ("프레시안", "데일리안", "매일신문"),
}

ALL_OUTLET_NAMES = frozenset(name for names in OUTLET_CATEGORIES.values() for name in names)


def _clean_text(raw: str) -> str:
    """네이버 API가 검색어 강조용으로 넣는 <b> 태그와 HTML 엔티티(&quot; 등)를 제거한다."""
    return html.unescape(_TAG_PATTERN.sub("", raw))


def _parse_pub_date(pub_date_str: str) -> Optional[datetime]:
    """네이버 API의 pubDate(RFC 822 형식)를 파싱한다. 형식이 이상하면 None."""
    try:
        parsed = parsedate_to_datetime(pub_date_str)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_KST)
    return parsed


def _is_today_kst(pub_date: datetime) -> bool:
    return pub_date.astimezone(_KST).date() == datetime.now(_KST).date()


# 도메인 문자열이 긴(구체적인) 것부터 검사해야 한다 — 예: "koreajoongangdaily.joins.com"
# (코리아중앙데일리)이 그 자신의 상위 도메인 "joins.com"(중앙일보)으로 먼저 매칭되는
# 오판정을 막는다. 모듈 로드 시 한 번만 정렬해 매 호출마다 다시 정렬하지 않는다.
_SORTED_OUTLET_DOMAINS = sorted(OUTLET_DOMAINS.items(), key=lambda kv: len(kv[0]), reverse=True)


def _extract_outlet(url: str) -> str:
    """URL 도메인으로 언론사명을 추정한다. 목록에 없으면 도메인 자체를 그대로 쓴다."""
    domain = urlparse(url).netloc.removeprefix("www.")
    for known_domain, outlet_name in _SORTED_OUTLET_DOMAINS:
        # 서브도메인(biz.chosun.com)은 매칭하되, "notchosun.com"처럼 접미사만
        # 우연히 같은 무관한 도메인은 잘못 매칭되지 않도록 경계를 확인한다.
        if domain == known_domain or domain.endswith("." + known_domain):
            return outlet_name
    return domain


def _search_one_keyword(keyword: str) -> list[dict]:
    """
    한 키워드로 검색해 당일(KST) 게시된 기사만 모은다 (PRD.md 기능1 규칙 2).

    sort="date"로 최신순 정렬해서 받으므로, 오늘보다 오래된 기사가 한 건이라도 나오면
    그 뒤로는 전부 더 오래된 기사다 — 그 지점에서 이 키워드의 페이지네이션을 그만둔다
    (불필요한 API 호출을 줄인다). pubDate를 못 읽는 낱개 기사는 그 기사만 건너뛴다
    (페이지네이션 중단 신호로 쓰지 않는다).
    """
    headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
    }
    results = []
    start = 1
    while start <= _MAX_START:
        response = requests.get(
            NAVER_NEWS_API_URL,
            headers=headers,
            params={"query": keyword, "display": _MAX_DISPLAY, "start": start, "sort": "date"},
            timeout=10,
        )
        response.raise_for_status()
        items = response.json().get("items", [])
        if not items:
            break

        reached_older_article = False
        for item in items:
            pub_date = _parse_pub_date(item.get("pubDate", ""))
            if pub_date is None:
                continue  # 날짜를 못 읽으면 이 기사만 건너뛴다
            if not _is_today_kst(pub_date):
                reached_older_article = True
                break  # 최신순 정렬이므로 여기서부터는 전부 더 오래된 기사
            results.append(
                {
                    # 네이버가 기사를 자체 미러링하면 link가 n.news.naver.com이 되어
                    # 도메인만으로는 언론사를 알 수 없다. 언론사 판별은 원본 링크로 한다.
                    "outlet": _extract_outlet(item["originallink"]),
                    "title": _clean_text(item["title"]),
                    "url": item["link"],
                    "summary": _clean_text(item["description"]),
                }
            )

        if reached_older_article or len(items) < _MAX_DISPLAY:
            break
        start += _MAX_DISPLAY
    return results


def search_articles(keywords: list[str], mode: str = "OR") -> list[dict]:
    """
    등록된 키워드로 기사를 검색해 모아 반환한다 (건수 제한 없음).

    mode="OR" (기본값): 키워드 중 하나라도 포함된 기사를 모두 모은다 (합집합).
    mode="AND": 키워드를 모두 포함한 기사만 남긴다 (URL 기준 교집합).
    키워드가 1개뿐이면 OR/AND 결과는 같다 (PRD.md 기능1 규칙 2).

    주의: 각 키워드는 최신 1000건까지만 조회하므로(_MAX_START), 어느 한 키워드의
    당일 기사량이 1000건을 넘으면 두 키워드 모두에 실린 기사라도 교집합에서
    누락될 수 있다. "재정경제부"/"재경부" 수준의 키워드에서는 발생 가능성이 낮다.

    같은 기사가 여러 키워드에 걸려 중복 수집돼도 이 단계에서는 그대로 둔다.
    완전 동일 제목 중복 제거·[포토] 제외·언론사 우선순위 정렬은 다음 작업(PLAN #4·#5)에서 처리한다.
    """
    if mode not in ("OR", "AND"):
        raise ValueError(f"알 수 없는 검색 방식입니다: {mode!r} (OR 또는 AND만 가능)")

    per_keyword_results = [_search_one_keyword(keyword) for keyword in keywords]

    if mode == "OR" or len(per_keyword_results) <= 1:
        articles = []
        for results in per_keyword_results:
            articles.extend(results)
        return articles

    # AND: 모든 키워드의 검색 결과에 공통으로 등장한 기사만 남긴다.
    url_sets = [{a["url"] for a in results} for results in per_keyword_results]
    common_urls = set.intersection(*url_sets)

    seen_urls = set()
    articles = []
    for results in per_keyword_results:
        for article in results:
            if article["url"] in common_urls and article["url"] not in seen_urls:
                seen_urls.add(article["url"])
                articles.append(article)
    return articles
