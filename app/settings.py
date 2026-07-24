# Design Ref: PRD.md 기능1 규칙 6·15·16·20 — 검색 키워드/언론사 선택/형광펜 단어/수집 시각, 코드 수정 없이 화면에서 변경
import json
import re
from typing import Optional

from app.atomic_write import atomic_write_text
from app.config import (
    DEFAULT_ARTICLE_LINE_TEMPLATE,
    DEFAULT_HIGHLIGHT_KEYWORDS,
    DEFAULT_KEYWORDS,
    MAX_HIGHLIGHT_KEYWORDS,
    MAX_KEYWORDS,
    MAX_SCHEDULE_TIMES,
    MIN_KEYWORDS,
    MIN_SCHEDULE_TIMES,
    SCHEDULE_TIMES,
    SETTINGS_FILE,
)
from app.naver_api import ALL_OUTLET_NAMES

VALID_MODES = ("OR", "AND")
VALID_DIRECTIONS = ("up", "down")
_TIME_PATTERN = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


class SettingsError(ValueError):
    """설정값이 PRD 규칙을 어겼을 때 (예: 키워드 0개, 8개 이상, 모르는 언론사)."""


def _default_settings() -> dict:
    return {
        "keywords": list(DEFAULT_KEYWORDS),
        "mode": "OR",
        "outlet_order": [],
        "highlight_keywords": list(DEFAULT_HIGHLIGHT_KEYWORDS),
        "article_line_template": DEFAULT_ARTICLE_LINE_TEMPLATE,
        "schedule_times": list(SCHEDULE_TIMES),
    }


def _write(settings: dict) -> None:
    atomic_write_text(SETTINGS_FILE, json.dumps(settings, ensure_ascii=False, indent=2))


def load_settings() -> dict:
    """저장된 설정을 읽어온다. 파일이 없으면 기본값으로 만들어두고 반환한다.

    옛 버전(언론사 선택·형광펜 단어·수집 시각 설정 기능 이전)에 저장된 파일에는 그
    필드가 없을 수 있어, 없으면 기본값으로 채워 반환한다 (하위 호환).
    """
    if not SETTINGS_FILE.exists():
        settings = _default_settings()
        _write(settings)
        return settings
    settings = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    settings.setdefault("outlet_order", [])
    settings.setdefault("highlight_keywords", list(DEFAULT_HIGHLIGHT_KEYWORDS))
    settings.setdefault("article_line_template", DEFAULT_ARTICLE_LINE_TEMPLATE)
    settings.setdefault("schedule_times", list(SCHEDULE_TIMES))
    return settings


def validate_article_line_template(template: str) -> str:
    """출력 줄 템플릿이 PRD 규칙을 어겼는지 검사한다 (PRD.md 기능1 규칙 5).

    {outlet}·{title} 자리표시자를 각각 정확히 1번씩 포함해야 한다 — 하나라도 없으면
    화면에서 언론사명이나 제목이 통째로 사라지고, 여러 번 있으면 같은 내용이 중복
    표시되므로 둘 다 막는다.
    """
    template = template.strip()
    if not template:
        raise SettingsError("출력 형식은 비워둘 수 없습니다.")
    for token in ("{outlet}", "{title}"):
        count = template.count(token)
        if count != 1:
            raise SettingsError(f'"{token}"를 정확히 1번 포함해야 합니다 (현재 {count}번).')
    return template


def validate_settings(keywords: list, mode: str) -> list:
    """키워드/검색방식이 PRD 규칙에 맞는지 검사해, 정리된 키워드 목록을 돌려준다.

    - 키워드는 앞뒤 공백을 지우고 빈 문자열은 버린다.
    - 개수는 MIN_KEYWORDS~MAX_KEYWORDS개여야 한다 (규칙15).
    - mode는 "OR" 또는 "AND"만 허용한다.
    - 키워드가 1개뿐이면 OR/AND 구분이 의미 없으므로 mode를 강제로 "OR"로 맞춘다.
    """
    cleaned = [k.strip() for k in keywords if k.strip()]
    if not (MIN_KEYWORDS <= len(cleaned) <= MAX_KEYWORDS):
        raise SettingsError(f"키워드는 {MIN_KEYWORDS}~{MAX_KEYWORDS}개여야 합니다 (현재 {len(cleaned)}개).")
    if mode not in VALID_MODES:
        raise SettingsError(f"검색 방식은 OR 또는 AND만 가능합니다: {mode!r}")
    return cleaned


def save_settings(keywords: list, mode: str) -> dict:
    """검증 후 키워드/검색방식을 저장한다. 기존에 저장돼 있던 outlet_order 등 다른
    설정은 그대로 보존한다 (통째로 덮어써서 지워버리지 않도록)."""
    cleaned = validate_settings(keywords, mode)
    settings = load_settings()
    settings["keywords"] = cleaned
    settings["mode"] = mode if len(cleaned) >= 2 else "OR"
    _write(settings)
    return settings


def save_outlet_selection(selected: list) -> dict:
    """설정 화면 체크박스에서 고른 언론사 집합을 저장한다 (PRD.md 기능1 규칙 16).

    이미 순서가 잡혀 있던 언론사는 그 순서를 그대로 유지하고, 새로 체크된 언론사만
    맨 뒤에 이어 붙인다. 체크 해제된 언론사는 순서 목록에서 빠진다. 알 수 없는
    언론사명이 섞여 있으면 에러를 낸다 (화면 체크박스 값은 항상 알려진 이름이어야 정상).
    """
    unknown = [name for name in selected if name not in ALL_OUTLET_NAMES]
    if unknown:
        raise SettingsError(f"알 수 없는 언론사입니다: {', '.join(unknown)}")

    settings = load_settings()
    current_order = settings.get("outlet_order", [])
    selected_set = set(selected)

    kept = [name for name in current_order if name in selected_set]
    newly_added = [name for name in selected if name not in current_order]
    settings["outlet_order"] = kept + newly_added
    _write(settings)
    return settings


def save_highlight_keywords(keywords: list) -> dict:
    """형광펜 단어를 저장한다 (PRD.md 기능1 규칙 6).

    검색 키워드(save_settings)와는 완전히 별개 필드다. 0~3개까지 허용하며(최소 개수
    제한 없음 — 하나도 안 넣으면 하이라이트를 아예 안 하는 것도 유효한 선택), 빈
    문자열은 버리고 앞뒤 공백은 지운다.
    """
    cleaned = [k.strip() for k in keywords if k.strip()]
    if len(cleaned) > MAX_HIGHLIGHT_KEYWORDS:
        raise SettingsError(f"형광펜 단어는 최대 {MAX_HIGHLIGHT_KEYWORDS}개까지 가능합니다 (현재 {len(cleaned)}개).")
    settings = load_settings()
    settings["highlight_keywords"] = cleaned
    _write(settings)
    return settings


def save_article_line_template(template: str) -> dict:
    """기사 출력 줄 형식을 저장한다 (PRD.md 기능1 규칙 5). 검증은 validate_article_line_template 참고."""
    cleaned = validate_article_line_template(template)
    settings = load_settings()
    settings["article_line_template"] = cleaned
    _write(settings)
    return settings


def validate_schedule_times(times: list) -> list:
    """수집 시각 목록이 PRD 규칙을 어겼는지 검사해, 정리된(중복 제거·오름차순) 목록을 돌려준다.

    - 빈 칸은 버린다.
    - 각 값은 "HH:MM" 24시간제 형식이어야 한다 (input type=time이 이 형식으로 보내주지만,
      서버에서도 한 번 더 검증한다).
    - 같은 시각이 중복 등록되면 하나로 합친다.
    - 개수는 MIN_SCHEDULE_TIMES~MAX_SCHEDULE_TIMES개여야 한다 (규칙20).
    """
    cleaned = []
    for t in times:
        t = t.strip()
        if not t:
            continue
        if not _TIME_PATTERN.match(t):
            raise SettingsError(f'시각 형식이 올바르지 않습니다: "{t}" (예: 09:00)')
        if t not in cleaned:
            cleaned.append(t)
    if not (MIN_SCHEDULE_TIMES <= len(cleaned) <= MAX_SCHEDULE_TIMES):
        raise SettingsError(f"수집 시각은 {MIN_SCHEDULE_TIMES}~{MAX_SCHEDULE_TIMES}개여야 합니다 (현재 {len(cleaned)}개).")
    return sorted(cleaned)


def save_schedule_times(times: list) -> dict:
    """검증 후 수집 시각 목록을 저장한다 (PRD.md 기능1 규칙 20)."""
    cleaned = validate_schedule_times(times)
    settings = load_settings()
    settings["schedule_times"] = cleaned
    _write(settings)
    return settings


def move_outlet(name: str, direction: str) -> dict:
    """선택된 언론사 순서에서 name을 한 칸 위/아래로 옮긴다 (PRD.md 기능1 규칙 16, 버튼 방식).

    맨 위에서 "위로", 맨 아래에서 "아래로"를 누르면 조용히 아무 일도 하지 않는다
    (버튼이 원래 그 위치에서 비활성이어야 자연스럽지만, 정적 HTML 폼이라 서버에서도
    한 번 더 방어한다).
    """
    if direction not in VALID_DIRECTIONS:
        raise SettingsError(f"방향은 up 또는 down만 가능합니다: {direction!r}")

    settings = load_settings()
    order = settings.get("outlet_order", [])
    if name not in order:
        raise SettingsError(f"선택되지 않은 언론사입니다: {name!r}")

    idx = order.index(name)
    swap_with = idx - 1 if direction == "up" else idx + 1
    if 0 <= swap_with < len(order):
        order[idx], order[swap_with] = order[swap_with], order[idx]
        settings["outlet_order"] = order
        _write(settings)
    return settings
