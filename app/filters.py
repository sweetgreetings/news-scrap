# Design Ref: PRD.md 기능1 규칙 4·12·16 — 사진기사 제외, 완전 동일 제목 1건만, 언론사 화이트리스트
# [수정: 2026-07-24] 사진기사 제외 힌트 단어 목록 (제목에 하나라도 있으면 제외, 대소문자 무시)
PHOTO_HINT_WORDS = ["포토", "[포토]", "사진", "화보", "포토뉴스", "PHOTO"]
# [추가: 2026-07-24] "[속보]"는 아무리 단신이어도 예외로 항상 남긴다 (규칙12)
BREAKING_NEWS_MARK = "[속보]"


def filter_by_outlet_whitelist(articles: list[dict], whitelist: list[str]) -> list[dict]:
    """설정 화면에서 고른 언론사(whitelist)에 없는 기사는 제외한다 (PRD.md 기능1 규칙 16).

    whitelist가 비어 있으면 아무것도 걸러내지 않는다 — "언론사를 하나도 안 골랐다"는
    PRD상 "화이트리스트 미사용, 기본 우선순위 유지"를 뜻하므로, 호출 여부 자체를
    호출하는 쪽(app.scraper)이 whitelist 존재 여부로 판단한다.
    """
    if not whitelist:
        return articles
    allowed = set(whitelist)
    return [a for a in articles if a["outlet"] in allowed]


def exclude_photo_articles(articles: list[dict]) -> list[dict]:
    """제목에 사진기사 힌트 단어(PHOTO_HINT_WORDS)가 있으면 수집 대상에서 아예 제외한다.

    단, "[속보]"가 붙은 기사는 다른 힌트 단어가 같이 있어도 항상 남긴다 — 아무리
    단신이어도 속보는 놓치면 안 되기 때문이다 (PRD 규칙12 예외).
    """
    result = []
    for article in articles:
        title = article["title"]
        if BREAKING_NEWS_MARK in title:
            result.append(article)
            continue
        title_lower = title.lower()
        if any(word.lower() in title_lower for word in PHOTO_HINT_WORDS):
            continue
        result.append(article)
    return result


def deduplicate_by_title(articles: list[dict]) -> list[dict]:
    """
    제목이 완전히 동일한 기사는 처음 나온 1건만 남긴다.
    (제목이 다르면, 같은 사건을 다룬 기사여도 그대로 모두 남긴다 — PRD.md 기능1 규칙 4)

    주의: "먼저 나온 것"이 남으므로, 언론사 우선순위 정렬(PLAN #5) 이후에
    호출해야 동일 제목 중 우선순위 높은 언론사의 기사가 남는다. DESIGN.md
    데이터 흐름도 참고.
    """
    seen_titles = set()
    unique_articles = []
    for article in articles:
        if article["title"] in seen_titles:
            continue
        seen_titles.add(article["title"])
        unique_articles.append(article)
    return unique_articles


def filter_articles(articles: list[dict]) -> list[dict]:
    """검색 결과에 [포토] 제외 -> 완전 동일 제목 중복 제거 순서로 적용한다."""
    articles = exclude_photo_articles(articles)
    return deduplicate_by_title(articles)
