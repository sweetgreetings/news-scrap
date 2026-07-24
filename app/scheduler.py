# Design Ref: PRD.md 기능1 규칙 1·9·20 — 자동 실행(설정한 시각·횟수) + 놓친 회차는 가장 최근 1개만 보충
import logging
import time
from datetime import datetime
from typing import Callable, List, Optional

from app.scraper import collect_run_with_retry
from app.settings import load_settings
from app.storage import delete_expired_runs, run_exists

logger = logging.getLogger(__name__)

# 폴링 간격(초). 1분마다 현재 시각을 확인해 실행할 회차가 있는지 본다.
POLL_INTERVAL_SEC = 60


def _resolve_schedule_times(schedule_times: Optional[List[str]]) -> List[str]:
    """schedule_times를 생략하면 설정 화면에 저장된 값을 매번 새로 읽는다 (규칙20).

    스케줄 루프가 매 tick마다 이 함수를 거치므로, 앱을 재시작하지 않아도 설정 화면에서
    바꾼 시각·횟수가 다음 tick(최대 POLL_INTERVAL_SEC 이내)부터 바로 반영된다.
    """
    return schedule_times if schedule_times is not None else load_settings()["schedule_times"]


def current_active_slot(now: datetime, schedule_times: Optional[List[str]] = None) -> Optional[str]:
    """지금 시각 기준으로 '오늘 이미 지나온 회차 중 가장 최근 회차'를 돌려준다.

    예) 지금이 11:00이고 회차가 09:00·10:30이면 10:30을 반환.
    아직 첫 회차 전이면 오늘 지나온 회차가 없으므로 None.
    """
    schedule_times = _resolve_schedule_times(schedule_times)
    now_hm = now.strftime("%H:%M")
    passed = [slot for slot in schedule_times if slot <= now_hm]
    return max(passed) if passed else None


def find_slot_to_run(
    now: datetime,
    schedule_times: Optional[List[str]] = None,
    already_run: Callable[[str], bool] = run_exists,
) -> Optional[str]:
    """지금 실행해야 할 회차를 돌려준다. 없으면 None.

    '가장 최근 회차'가 아직 오늘 실행되지 않았을 때만 그 회차를 반환한다.
    이 규칙 하나로 두 동작이 모두 처리된다:
      - 정시 실행: 시계가 회차 시각을 막 넘기면 그 회차가 '가장 최근'이 되어 실행됨
      - 놓친 회차 보충: 여러 회차를 놓쳐도 '가장 최근' 1개만 실행되고 이전 회차는
        영영 '가장 최근'이 되지 못해 자연히 건너뛰어짐 (PRD 규칙 9)
    """
    slot = current_active_slot(now, schedule_times)
    if slot is not None and not already_run(slot):
        return slot
    return None


def run_due_slot(
    now: Optional[datetime] = None,
    schedule_times: Optional[List[str]] = None,
    scrape: Callable[[str], dict] = collect_run_with_retry,
) -> Optional[str]:
    """한 번의 확인(tick)을 수행한다. 실행할 회차가 있으면 수집하고 그 회차명을, 없으면 None을 반환한다."""
    now = now or datetime.now()
    slot = find_slot_to_run(now, schedule_times)
    if slot is None:
        return None
    scrape(slot)
    return slot


def run_scheduler(
    poll_interval_sec: int = POLL_INTERVAL_SEC,
    now_fn: Callable[[], datetime] = datetime.now,
    sleep: Callable[[float], None] = time.sleep,
    schedule_times: Optional[List[str]] = None,
    scrape: Callable[[str], dict] = collect_run_with_retry,
    cleanup: Callable[[], list] = delete_expired_runs,
    should_continue: Callable[[], bool] = lambda: True,
) -> None:
    """앱이 켜져 있는 동안 poll_interval_sec마다 실행할 회차가 있는지 확인하고 수집한다.

    앱 시작 직후 첫 tick에서 놓친 회차를 바로 보충 실행하고, 이후 회차 시각마다 정시 실행한다.
    잠자기 모드 중에는 이 루프도 함께 멈추므로 정시 실행이 보장되지 않지만, 컴퓨터가 깨어나면
    다음 tick에서 '가장 최근 놓친 회차'를 감지해 즉시 보충 실행한다.

    매 tick마다 7일 지난 회차 삭제(cleanup, PRD.md 7절)도 함께 실행해 별도 배치 없이
    "자동" 삭제가 되도록 한다. 파일 수가 적어(최대 하루 MAX_SCHEDULE_TIMES개) 매번 스캔해도 비용이 작다.

    now_fn/sleep/scrape/cleanup/should_continue는 테스트에서 주입할 수 있다.

    한 회차 수집이나 정리 작업이 실패해 예외가 나도 루프는 멈추지 않는다. 실패한 회차는
    파일이 저장되지 않아 run_exists가 False로 남으므로, 다음 tick(최대 poll_interval_sec
    이내)에 자연히 다시 시도된다. 이 방어가 없으면 일시적 오류 하나로 이후 모든 자동 실행이
    조용히 중단된다.
    """
    while should_continue():
        try:
            run_due_slot(now=now_fn(), schedule_times=schedule_times, scrape=scrape)
            cleanup()
        except Exception:
            logger.exception("스크랩 회차 실행 중 오류 — 다음 회차에 다시 시도합니다")
        sleep(poll_interval_sec)
