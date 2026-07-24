# Design Ref: PRD.md 기능1 규칙 3·16 — 언론사 우선순위(기본값, 또는 설정 화면의 사용자 지정 순서) 정렬
from typing import Optional

from app.naver_api import PRIORITY_OUTLETS


def _priority_rank(outlet: str, priority_outlets: tuple) -> int:
    try:
        return priority_outlets.index(outlet)
    except ValueError:
        return len(priority_outlets)  # 목록에 없는 언론사는 맨 뒤 순위


def sort_by_outlet_priority(articles: list[dict], priority_outlets: Optional[list] = None) -> list[dict]:
    """
    언론사 우선순위 순으로 안정 정렬한다.

    priority_outlets를 생략하면 기본 우선순위(방송사 -> 주요 언론사 -> 그 외, PRD 규칙3)를 쓴다.
    설정 화면에서 "언론사 선택"을 지정하면(PRD 규칙16) 그 순서를 여기로 넘겨 대신 쓸 수 있다 —
    이 경우 목록에 없는 언론사도 맨 뒤로 밀릴 뿐 정렬 자체는 동일하게 동작한다(제외는 이 함수의
    책임이 아니라 app.filters.filter_by_outlet_whitelist가 별도로 담당).

    목록에 없는 언론사는 제외하지 않고 맨 뒤로 보내되, 그들끼리의 원래 순서는 유지한다(안정 정렬).

    주의: 완전 동일 제목 중복 제거(app.filters.deduplicate_by_title)는
    이 정렬 이후에 호출해야 한다 — 그래야 우선순위 높은 언론사의 사본이
    남는다 (DESIGN.md 데이터 흐름 참고).
    """
    priority = tuple(priority_outlets) if priority_outlets is not None else PRIORITY_OUTLETS
    return sorted(articles, key=lambda a: _priority_rank(a["outlet"], priority))
