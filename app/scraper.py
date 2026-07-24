# Design Ref: DESIGN.md §2 데이터 흐름 — 검색 -> 정렬 -> 필터 -> 저장을 한 회차로 이어 실행
import time
from datetime import datetime
from typing import Callable, Optional

import requests

from app.config import MAX_RETRIES, RETRY_INTERVAL_SEC
from app.filters import filter_articles, filter_by_outlet_whitelist
from app.naver_api import search_articles
from app.settings import load_settings
from app.sorter import sort_by_outlet_priority
from app.storage import save_run


def collect_run(
    run_slot: str,
    keywords: Optional[list[str]] = None,
    mode: Optional[str] = None,
    outlet_order: Optional[list[str]] = None,
    run_at: Optional[str] = None,
) -> dict:
    """
    한 회차의 기사를 수집해 로컬 JSON 파일로 저장하고, 저장된 회차 데이터를 반환한다.

    처리 순서 (DESIGN.md §2):
      1. search_articles: 설정된 키워드로 검색 (mode="OR"/"AND")
      2. outlet_order가 있으면(PRD 규칙16) 그 언론사만 남기고(filter_by_outlet_whitelist)
         그 순서로 정렬, 없으면 기본 우선순위(PRD 규칙3)로 정렬
      3. filter_articles: 사진기사 제외(PHOTO_HINT_WORDS, [속보] 예외) -> 완전 동일 제목 중복 제거
         (정렬을 먼저 해야 중복 중 우선순위 높은 언론사 사본이 남는다)
      4. save_run: 언론사·제목·URL·요약을 JSON 파일로 저장

    run_slot: 이 회차의 예정 시각 (예: "09:00"). 헤더 "언론 모니터링 09:00 기준"에 쓰인다.
    keywords: 검색 키워드 목록. 생략하면 설정 화면에 저장된 값을 쓴다.
    mode:     "OR"(하나라도 포함) / "AND"(모두 포함). 생략하면 저장된 설정값을 쓴다.
    outlet_order: 선택된 언론사(화이트리스트) 및 그 순서. 생략하면 저장된 설정값을 쓰며,
                  빈 리스트면 화이트리스트 없이 기본 우선순위 동작을 그대로 따른다.
    run_at:   실제 실행 시각. 놓친 회차 보충 실행 시 run_slot과 달라질 수 있다.
    """
    if keywords is None or mode is None or outlet_order is None:
        settings = load_settings()
        keywords = keywords if keywords is not None else settings["keywords"]
        mode = mode if mode is not None else settings["mode"]
        outlet_order = outlet_order if outlet_order is not None else settings.get("outlet_order", [])
    # 저장 파일과 반환값의 run_at이 어긋나지 않도록 여기서 한 번만 확정한다.
    run_at = run_at or datetime.now().isoformat(timespec="seconds")

    articles = search_articles(keywords, mode=mode)
    if outlet_order:
        articles = filter_by_outlet_whitelist(articles, outlet_order)
        articles = sort_by_outlet_priority(articles, priority_outlets=outlet_order)
    else:
        articles = sort_by_outlet_priority(articles)
    articles = filter_articles(articles)

    save_run(run_slot, articles, run_at=run_at)
    return {"run_slot": run_slot, "run_at": run_at, "articles": articles}


def collect_run_with_retry(
    run_slot: str,
    keywords: Optional[list[str]] = None,
    mode: Optional[str] = None,
    outlet_order: Optional[list[str]] = None,
    max_retries: int = MAX_RETRIES,
    retry_interval_sec: int = RETRY_INTERVAL_SEC,
    sleep: Callable[[float], None] = time.sleep,
) -> dict:
    """
    collect_run을 감싸, 네트워크 오류로 스크랩이 실패하면 자동 재시도한다 (PRD.md 기능1 규칙 8).

    최초 1회 시도 후 실패하면 retry_interval_sec(기본 300초=5분) 간격으로 최대
    max_retries회(기본 3회) 재시도한다. 즉 최대 (1 + max_retries)회까지 시도한다.
    재시도 사이 대기는 sleep 함수로 주입할 수 있어 테스트에서 실제 5분을 기다리지 않아도 된다.

    재시도 대상은 네트워크·API 오류(requests.exceptions.RequestException)뿐이다.
    수집 결과가 0건인 것은 실패가 아니라 정상(화면에 "하나도 없어요")이므로 재시도하지 않는다.
    max_retries회를 모두 소진해도 실패하면 마지막 예외를 그대로 올린다.

    run_at은 각 시도 시점의 실제 시각으로 기록되므로(collect_run이 매번 확정), 재시도로
    성공한 회차의 run_at은 실제 성공 시각을 가리킨다. run_slot은 예정 시각으로 고정된다.

    단, 4xx 클라이언트 오류(잘못된 API 키 401, 잘못된 요청 400 등)는 재시도해도 결과가
    바뀌지 않으므로 즉시 예외를 올린다. 일시적 오류(연결 실패·타임아웃·5xx 서버 오류·429
    rate limit)만 재시도한다.
    """
    last_error: Optional[Exception] = None
    for attempt in range(max_retries + 1):
        try:
            return collect_run(run_slot, keywords=keywords, mode=mode, outlet_order=outlet_order)
        except requests.exceptions.RequestException as error:
            if not _is_retryable(error):
                raise
            last_error = error
            if attempt < max_retries:
                sleep(retry_interval_sec)
    raise last_error


def _is_retryable(error: requests.exceptions.RequestException) -> bool:
    """일시적 오류(재시도할 가치가 있는 오류)인지 판단한다.

    4xx 클라이언트 오류는 재시도해도 소용없으므로 False (단 429 rate limit은 예외적으로 재시도).
    연결 실패·타임아웃 등 응답 자체가 없는 오류나 5xx 서버 오류는 True.
    """
    response = getattr(error, "response", None)
    if response is None:
        return True  # 연결 실패·타임아웃 등 — 재시도 대상
    if response.status_code == 429:
        return True  # rate limit — 잠시 후 재시도하면 풀릴 수 있음
    return not (400 <= response.status_code < 500)  # 그 외 4xx는 재시도 안 함
