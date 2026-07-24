# Design Ref: PRD.md 4절 — 앱 실행 시 자동으로 스케줄이 돌고, 브라우저가 열려 화면으로 연결됨
import logging
import threading
import webbrowser

from app.atomic_write import atomic_write_text
from app.config import COLOR_BG, COLOR_TEXT, FONT_STACK, LANDING_HTML_PATH, OUTPUT_HTML_PATH
from app.history_renderer import generate_history_page
from app.landing_renderer import generate_landing_page
from app.renderer import generate_screen
from app.scheduler import run_due_slot, run_scheduler
from app.scraper import collect_run_with_retry
from app.settings_server import run_settings_server
from app.storage import delete_expired_runs

logger = logging.getLogger(__name__)

# 이 문자열은 .format()을 거치지 않고 그대로 파일에 쓰므로, 중괄호를 이중화하지
# 않고 실제 CSS처럼 단일 중괄호로 적는다 (이중화하면 브라우저에 그대로 노출돼 깨진다).
_WAITING_PAGE = f"""<!DOCTYPE html>
<html lang="ko">
<head><meta charset="UTF-8" /><title>언론 모니터링</title>
<style>body{{margin:0;background:{COLOR_BG};color:{COLOR_TEXT};font-family:{FONT_STACK};
display:flex;align-items:center;justify-content:center;height:100vh;font-size:1.2rem;}}</style>
</head>
<body>오늘 첫 스크랩 시각이 아직 되지 않았습니다. 예정 시각이 되면 자동으로 시작됩니다.</body>
</html>
"""


def _scrape_and_render(run_slot: str) -> dict:
    """한 회차를 수집한 뒤 곧바로 메인/지난 기사/진입 화면을 다시 만든다.

    스케줄러는 이 함수를 매 회차마다 호출하므로, 09:00 이후 10:30·13:30·16:30에도
    화면 파일이 계속 최신으로 갱신된다 (수집만 하고 화면을 안 만들면, 하루 종일
    첫 회차 화면에서 멈춰 있게 된다). 진입 화면의 "당일 주요 키워드" 워드클라우드도
    회차가 바뀔 때마다 새로 반영되어야 하므로 함께 다시 만든다.
    """
    result = collect_run_with_retry(run_slot)
    generate_screen()
    generate_history_page()
    generate_landing_page()
    return result


def main() -> None:
    """앱 진입점: 켜지자마자 놓친 회차가 있으면 즉시 1회 수집한 뒤, 스케줄 루프와 설정
    저장 서버를 백그라운드로 띄우고 브라우저로 화면을 연다 (PRD.md 4절)."""
    # 며칠 꺼뒀다 켠 경우, 정리(cleanup)는 스케줄 루프 안에서만 비동기로 도는데(scheduler.py)
    # 그걸 기다리면 아래에서 만들 "지난 기사 더보기"가 7일 지난 회차까지 잠깐 보여줄 수 있다.
    # 화면을 만들기 전에 한 번 먼저 정리한다.
    try:
        delete_expired_runs()
    except Exception:
        logger.exception("시작 시 보관 기간 정리 실패 — 스케줄 루프가 이어서 재시도합니다")

    try:
        # 오늘 지나온 회차 중 아직 안 돌았으면 지금 바로 실행 (스케줄 루프의 tick을 기다리지 않음).
        # 실패해도 앱을 죽이지 않는다 — 곧 시작될 스케줄 루프의 첫 tick이 자연히 다시 시도한다.
        run_due_slot(scrape=_scrape_and_render)
    except Exception:
        logger.exception("시작 시 회차 수집 실패 — 스케줄 루프가 이어서 재시도합니다")

    threading.Thread(target=run_scheduler, kwargs={"scrape": _scrape_and_render}, daemon=True).start()
    threading.Thread(target=run_settings_server, daemon=True).start()

    try:
        generate_screen()
    except RuntimeError:
        # 오늘 첫 회차(예: 09:00) 이전에 앱을 켠 경우 — 아직 수집된 회차가 하나도 없다.
        atomic_write_text(OUTPUT_HTML_PATH, _WAITING_PAGE)
    # 아래 둘은 회차가 하나도 없어도 예외를 내지 않으므로(빈 목록/빈 워드클라우드로 처리),
    # generate_screen의 성공 여부와 무관하게 항상 만든다.
    generate_history_page()
    generate_landing_page()

    webbrowser.open(LANDING_HTML_PATH.as_uri())

    threading.Event().wait()  # 데몬 스레드가 계속 돌도록 메인 스레드를 대기시킨다 (Ctrl+C로 종료)


if __name__ == "__main__":
    main()
