# Design Ref: PRD.md 기능1 규칙 19·21, 기능2 규칙 8 — 기사 숨김/되돌리기, 소제목 순서·경계 넘나들기, 소제목 이름 바꾸기
import json
from typing import Optional, Tuple

from app.atomic_write import atomic_write_text
from app.classifier import classify_articles
from app.config import GROUP_LABELS_FILE, GROUP_OVERRIDES_FILE, HIDDEN_ARTICLES_FILE


def load_hidden_urls() -> set:
    """숨긴 기사의 URL 집합을 읽어온다. 파일이 없거나 손상됐으면 빈 집합으로 취급한다."""
    if not HIDDEN_ARTICLES_FILE.exists():
        return set()
    try:
        return set(json.loads(HIDDEN_ARTICLES_FILE.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, TypeError):
        return set()


def _write(urls: set) -> None:
    atomic_write_text(HIDDEN_ARTICLES_FILE, json.dumps(sorted(urls), ensure_ascii=False, indent=2))


def hide_article(url: str) -> None:
    """기사 하나를 숨김 처리한다. 원본 회차 JSON은 그대로 두고, 화면에 그릴 때만 제외한다."""
    urls = load_hidden_urls()
    urls.add(url)
    _write(urls)


def unhide_article(url: str) -> None:
    """숨김을 해제해 다시 화면에 보이게 한다."""
    urls = load_hidden_urls()
    urls.discard(url)
    _write(urls)


def load_group_overrides() -> dict:
    """소제목 경계를 넘어 수동으로 옮긴 기사의 강제 소제목 기록을 읽어온다.

    {기사 url: 소제목 이름} 형태. 파일이 없거나 손상됐으면 빈 dict로 취급한다.
    """
    if not GROUP_OVERRIDES_FILE.exists():
        return {}
    try:
        return json.loads(GROUP_OVERRIDES_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, TypeError):
        return {}


def _write_overrides(overrides: dict) -> None:
    atomic_write_text(GROUP_OVERRIDES_FILE, json.dumps(overrides, ensure_ascii=False, indent=2))


def set_group_override(url: str, group_name: str) -> None:
    """기사 하나를 특정 소제목에 강제로 배정한다 (PRD.md 기능1 규칙 21)."""
    overrides = load_group_overrides()
    overrides[url] = group_name
    _write_overrides(overrides)


def move_article(
    articles: list, keywords: Optional[list], url: str, direction: str, overrides: Optional[dict] = None
) -> Tuple[list, Optional[tuple]]:
    """기사 하나를 위/아래로 옮긴다 (PRD.md 기능1 규칙 21).

    같은 소제목 안이면 그 기사와 이웃의 위치를 원본 리스트에서 맞바꿔 순서만 바꾼다
    (다른 소제목은 전혀 건드리지 않는다). 소제목의 맨 위/아래에 닿으면, 한 번 더
    누를 때 바로 앞/뒤 소제목으로 기사를 통째로 옮긴다 — 이건 순서가 아니라 분류
    자체를 바꾸는 것이라 즉시 리스트를 바꿀 수 없고, "이 기사는 이제 이 소제목"이라는
    강제 배정을 새로 만들어야 다음 렌더링에도 유지된다.

    overrides: 지금까지 쌓인 강제 배정 기록. classify_articles에 그대로 반영해 "현재
    화면에 실제로 보이는 소제목 구성" 기준으로 위/아래를 판단한다.

    반환: (new_articles, new_override).
      - new_override가 None이면 new_articles만 반영하면 된다 (같은 소제목 내 순서 변경).
      - new_override가 (url, 소제목이름) 튜플이면, 호출하는 쪽이 set_group_override로
        저장해야 한다 (소제목 경계를 넘은 경우). 이때 new_articles는 원본과 동일하다.
      - 더 옮길 곳이 없거나 url을 못 찾으면 (articles, None)을 그대로 돌려준다.
    """
    groups = classify_articles(articles, keywords, forced_groups=overrides)
    group_index = next(
        (i for i, g in enumerate(groups) if any(a["url"] == url for a in g["articles"])), None
    )
    if group_index is None:
        return articles, None

    group_urls = [a["url"] for a in groups[group_index]["articles"]]
    pos = group_urls.index(url)
    swap_with = pos - 1 if direction == "up" else pos + 1

    if 0 <= swap_with < len(group_urls):
        other_url = group_urls[swap_with]
        index_by_url = {a["url"]: i for i, a in enumerate(articles)}
        i, j = index_by_url[url], index_by_url[other_url]
        new_articles = list(articles)
        new_articles[i], new_articles[j] = new_articles[j], new_articles[i]
        return new_articles, None

    target_index = group_index - 1 if direction == "up" else group_index + 1
    if not (0 <= target_index < len(groups)):
        return articles, None  # 맨 처음/맨 마지막 소제목이라 더 옮길 곳이 없음

    return articles, (url, groups[target_index]["name"])


def load_group_labels() -> dict:
    """자동 생성된 소제목 단어(topic word)에 사용자가 붙인 표시용 이름을 읽어온다.

    {소제목 단어: 표시할 이름} 형태. 분류 로직 자체(어떤 기사가 어느 그룹인지)는 항상
    원래 소제목 단어로만 판단하고, 이 이름표는 화면에 보여줄 때만 마지막에 적용한다 —
    그래야 소제목 경계 넘나들기(move_article)의 대상 지정도 계속 원래 단어 기준으로
    안정적으로 동작한다.
    """
    if not GROUP_LABELS_FILE.exists():
        return {}
    try:
        return json.loads(GROUP_LABELS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, TypeError):
        return {}


def _write_labels(labels: dict) -> None:
    atomic_write_text(GROUP_LABELS_FILE, json.dumps(labels, ensure_ascii=False, indent=2))


def set_group_label(topic_word: str, label: str) -> None:
    """소제목 단어의 표시 이름을 정한다 (PRD.md 기능2 규칙 8).

    이 단어가 나중에 다른 회차에서도 소제목으로 다시 잡히면 같은 이름표가 계속
    적용된다. 원래 단어와 똑같은 이름으로 "바꾸면" 이름표를 지운 것으로 본다
    (되돌리기를 별도 버튼 없이 자연스럽게 처리).
    """
    labels = load_group_labels()
    if label == topic_word:
        labels.pop(topic_word, None)
    else:
        labels[topic_word] = label
    _write_labels(labels)


def display_group_name(name: str, labels: dict) -> str:
    """소제목 단어를 화면에 보여줄 이름으로 바꾼다 (이름표가 없으면 원래 단어 그대로)."""
    return labels.get(name, name)


def filter_hidden(articles: list) -> list:
    """숨긴 기사를 제외한 목록을 돌려준다.

    화면 렌더링·복사용 텍스트·키워드 추출·워드클라우드 등 기사 목록을 쓰는 모든 곳이
    이 함수를 거친 뒤의 목록만 사용해야, 숨긴 기사가 어디에도 다시 새어나가지 않는다.
    """
    hidden = load_hidden_urls()
    return [a for a in articles if a["url"] not in hidden]
