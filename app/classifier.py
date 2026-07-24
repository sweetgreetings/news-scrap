# Design Ref: PRD.md 기능2 규칙 1·2·3·7 — 제목 분석으로 소제목(최대 5개) 자동 생성·배정 (규칙 기반, LLM 없음)
from collections import Counter, OrderedDict
from typing import Optional

from app.config import DEFAULT_KEYWORDS, MAX_SUBHEADINGS
from app.tokenizer import STOPWORDS, tokenize


def _assign(articles: list, token_sets: list, topic_words: list) -> tuple:
    """기사를 topic_words 중 (빈도순으로) 처음 걸리는 소제목에 배정한다.

    반환: (OrderedDict[소제목 -> 기사 리스트], 어디에도 안 걸린 기사 리스트).
    입력 순서(언론사 우선순위)를 유지하며 배정한다 (PRD 규칙 7).
    """
    groups = OrderedDict((w, []) for w in topic_words)
    leftover = []
    for article, tokens in zip(articles, token_sets):
        chosen = next((w for w in topic_words if w in tokens), None)
        if chosen is not None:
            groups[chosen].append(article)
        else:
            leftover.append(article)
    # 아무 기사도 못 담은 소제목은 버린다.
    used = OrderedDict((w, arts) for w, arts in groups.items() if arts)
    return used, leftover


def _apply_forced_groups(groups: list, forced_groups: dict) -> list:
    """사용자가 소제목 경계를 넘어 수동으로 옮긴 기사를 지정된 소제목으로 강제 이동한다
    (PRD.md 기능1 규칙 21 — ↑/↓로 소제목 자체를 바꾸는 경우).

    지정된 소제목이 이번 회차 자동 분류 결과에 없으면(예: 그 사이 관련 기사가 다
    숨겨지거나 삭제돼 그 소제목 자체가 사라짐) 조용히 무시하고 자동 분류를 그대로
    둔다 — 사라진 소제목을 억지로 되살리지 않는다(자기 치유적 동작).
    """
    group_by_name = {g["name"]: g for g in groups}
    for url, target_name in forced_groups.items():
        target = group_by_name.get(target_name)
        if target is None:
            continue
        moved = None
        for g in groups:
            for a in g["articles"]:
                if a["url"] == url:
                    moved = a
                    break
            if moved is not None:
                g["articles"] = [a for a in g["articles"] if a["url"] != url]
                break
        if moved is not None and moved not in target["articles"]:
            target["articles"].append(moved)
    return [g for g in groups if g["articles"]]


def classify_articles(
    articles: list,
    keywords: Optional[list] = None,
    max_subheadings: int = MAX_SUBHEADINGS,
    forced_groups: Optional[dict] = None,
) -> list:
    """기사 목록을 소제목별로 분류한다.

    반환: [{"name": 소제목, "articles": [기사, ...]}, ...] (최대 max_subheadings개).
    각 기사는 정확히 하나의 소제목에만 담기며, 어디에도 안 걸리는 기사는 "기타"로 모은다.
    소제목 순서는 빈도 높은 순, "기타"는 항상 맨 뒤. 그룹 내 기사 순서는 입력 순서를 유지한다.

    [수정: 2026-07-24] 분류 기준을 기사 제목이 아니라 네이버 요약(description)으로 바꿨다.
    제목은 언론사마다 표현이 제각각이라 같은 사건을 다뤄도 겹치는 단어가 잘 안 잡히는데,
    요약문은 보도자료 내용을 비슷한 문장으로 옮기는 경우가 많아 "○○회의" 같은 공통
    단어가 더 잘 드러난다. 요약이 비어 있으면 제목으로 대신한다.

    forced_groups: {기사 url: 소제목 이름} — 자동 분류 결과와 무관하게 이 소제목으로
    강제 이동한다(규칙21). 자동 분류를 모두 마친 뒤 마지막에 적용한다.
    """
    if not articles:
        return []

    keywords = keywords if keywords is not None else DEFAULT_KEYWORDS
    # 검색 키워드는 거의 모든 제목/요약에 있어 소제목으로 쓸모없으므로 불용어에 포함한다.
    stopwords = STOPWORDS | {k.lower() for k in keywords}

    token_sets = [tokenize(a.get("summary") or a["title"], stopwords) for a in articles]

    # 문서 빈도(몇 개 제목에 등장했는가) 2 이상인 단어만 소제목 후보로 삼는다.
    doc_freq = Counter(word for tokens in token_sets for word in tokens)
    first_seen = {}
    for i, tokens in enumerate(token_sets):
        for word in tokens:
            first_seen.setdefault(word, i)
    # 빈도·최초등장이 같을 때 단어 자체를 마지막 tie-break로 두어, set 순회 순서
    # (PYTHONHASHSEED)에 상관없이 항상 같은 결과가 나오도록 한다.
    candidates = sorted(
        (w for w, c in doc_freq.items() if c >= 2 and w != "기타"),
        key=lambda w: (-doc_freq[w], first_seen[w], w),
    )

    # 소제목 후보 개수를 줄여가며, 총 그룹 수(소제목 + 기타)가 최대치 이하가 되는 최대 구성을 찾는다.
    for num_topics in range(min(len(candidates), max_subheadings), -1, -1):
        used, leftover = _assign(articles, token_sets, candidates[:num_topics])
        total_groups = len(used) + (1 if leftover else 0)
        if total_groups <= max_subheadings:
            break

    result = [{"name": w, "articles": arts} for w, arts in used.items()]
    if leftover:
        result.append({"name": "기타", "articles": leftover})
    if forced_groups:
        result = _apply_forced_groups(result, forced_groups)
    return result
