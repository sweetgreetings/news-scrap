# Design Ref: PLAN.md #17 — 전체 흐름(스크랩 -> 분류 -> 화면 표시 -> 복사/내보내기) 통합 테스트
#
# pytest 같은 테스트 프레임워크 없이, 지금까지 각 작업을 검증할 때 쓰던 것과 같은 방식
# (assert + print)으로 작성한다. 네이버 API 호출 경계(app.naver_api._search_one_keyword)만
# 목으로 바꾸고, 그 뒤(정렬·필터·분류·요약·저장·렌더링·설정)는 전부 실제 코드를 그대로 돌린다.
#
# 실제 데이터 폴더(data/articles, index.html, settings.json)는 절대 건드리지 않는다 —
# 임시 폴더로 각 모듈의 경로 상수를 바꿔치기해서, 테스트가 실사용자 데이터를 지우는 사고를
# 원천적으로 막는다.
#
# 실행: python3 tests/test_integration.py
import json
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import naver_api, renderer, scraper, settings, storage  # noqa: E402

_FIXTURE_BY_KEYWORD = {
    "재정경제부": [
        {"originallink": "https://kbs.co.kr/1", "link": "https://kbs.co.kr/1",
         "title": "[포토] 재정경제부 브리핑 현장", "description": "사진 기사라 제외돼야 함"},
        {"originallink": "https://joongang.co.kr/2", "link": "https://joongang.co.kr/2",
         "title": "재정경제부 세제 개편 발표", "description": "재정경제부는 세제 개편안을 발표했다."},
        {"originallink": "https://imnews.imbc.com/3", "link": "https://imnews.imbc.com/3",
         "title": "재정경제부 세제 개편 발표", "description": "동일 제목, MBC(방송사)가 더 우선순위 높음"},
    ],
    "재경부": [
        {"originallink": "https://hankyung.com/4", "link": "https://hankyung.com/4",
         "title": "환율 급등 재경부 대응", "description": "환율이 급등하자 재경부가 대책을 내놨다."},
    ],
}


def _fake_search_one_keyword(keyword):
    return [
        {
            "outlet": naver_api._extract_outlet(item["originallink"]),
            "title": item["title"],
            "url": item["link"],
            "summary": item["description"],
        }
        for item in _FIXTURE_BY_KEYWORD.get(keyword, [])
    ]


def test_full_pipeline_happy_path():
    """스크랩 -> 정렬 -> 필터 -> 분류 -> 화면 -> 복사/내보내기 텍스트까지 한 번에 검증한다."""
    settings.save_settings(["재정경제부", "재경부"], "OR")

    with patch.object(naver_api, "_search_one_keyword", side_effect=_fake_search_one_keyword):
        result = scraper.collect_run_with_retry("09:00")

    # [포토] 제외 + 완전 동일 제목 중복 제거(우선순위 높은 MBC가 남음) -> 2건만 남아야 함
    titles = [a["title"] for a in result["articles"]]
    assert "[포토] 재정경제부 브리핑 현장" not in titles, "포토 기사가 제외되지 않음"
    assert titles.count("재정경제부 세제 개편 발표") == 1, "완전 동일 제목 중복이 제거되지 않음"
    kept = next(a for a in result["articles"] if a["title"] == "재정경제부 세제 개편 발표")
    assert kept["outlet"] == "MBC", f"우선순위 높은 MBC가 아니라 {kept['outlet']}가 남음"
    print("1) 검색/정렬/필터: 통과 (포토 제외, 중복 제거 시 우선순위 언론사 유지)")

    path = renderer.generate_screen()
    html_text = path.read_text(encoding="utf-8")
    assert "언론 모니터링 09:00 기준" in html_text, "헤더 문구 누락"
    assert "<세제>" in html_text or "세제" in html_text, "소제목 분류 결과가 화면에 없음"
    assert "하나도 없어요" not in html_text
    print("2) 화면 렌더링: 통과 (헤더 표시, 소제목 분류 반영)")

    assert "PLAIN_TEXT" in html_text
    plain_start = html_text.index("const PLAIN_TEXT = ") + len("const PLAIN_TEXT = ")
    plain_end = html_text.index(";\n", plain_start)
    plain_text = json.loads(html_text[plain_start:plain_end])
    assert plain_text.startswith("언론 모니터링 09:00 기준"), "복사/내보내기 텍스트 헤더 누락"
    assert "🤖" not in plain_text and "💬" not in plain_text, "복사/내보내기에 하단 요약 블록이 포함됨(제외 대상)"
    assert "[포토]" not in plain_text
    print("3) 복사/내보내기 텍스트: 통과 (헤더 포함, 하단 AI 블록 제외, 포토 기사 제외)")


def test_settings_actually_change_scraping():
    """설정 화면에서 저장한 키워드/모드가 실제 스크랩 호출에 반영되는지 확인한다."""
    settings.save_settings(["재정경제부", "재경부", "환율"], "AND")
    captured = {}

    def spy(keywords, mode="OR"):
        captured["keywords"] = keywords
        captured["mode"] = mode
        return []

    with patch.object(scraper, "search_articles", spy):
        scraper.collect_run("10:30")  # keywords/mode 생략 -> 설정값을 읽어야 함

    assert captured["keywords"] == ["재정경제부", "재경부", "환율"]
    assert captured["mode"] == "AND"
    print("4) 설정 연동: 통과 (저장된 키워드/모드가 실제 스크랩에 반영됨)")


def test_empty_run_shows_placeholder():
    """이번 회차에 기사가 하나도 없으면 '하나도 없어요'가 표시되는지 확인한다."""
    settings.save_settings(["재정경제부", "재경부"], "OR")
    with patch.object(naver_api, "_search_one_keyword", return_value=[]):
        scraper.collect_run_with_retry("13:30")
    html_text = renderer.generate_screen().read_text(encoding="utf-8")
    assert "하나도 없어요" in html_text
    assert "언론 모니터링 13:30 기준" in html_text
    print("5) 빈 회차 처리: 통과 ('하나도 없어요' 표시)")


def test_retention_cleanup_removes_old_runs():
    """7일 지난 회차가 자동 삭제 대상에 걸리는지 확인한다."""
    now = datetime(2026, 7, 23, 12, 0)
    old_path = storage.save_run("09:00", [], run_at=(now - timedelta(days=8)).isoformat(timespec="seconds"))
    deleted = storage.delete_expired_runs(retention_days=7, now=now)
    assert old_path in deleted
    assert not old_path.exists()
    print("6) 보관 기간 정리: 통과 (8일 지난 회차 삭제됨)")


if __name__ == "__main__":
    tests = [
        test_full_pipeline_happy_path,
        test_settings_actually_change_scraping,
        test_empty_run_shows_placeholder,
        test_retention_cleanup_removes_old_runs,
    ]

    failures = []
    # 실제 data/articles, index.html, settings.json은 절대 건드리지 않도록, 이 테스트가
    # 쓰고 지우는 모든 경로를 임시 폴더로 바꿔치기한 채로만 테스트를 돌린다.
    # 테스트마다 별도의 새 임시 폴더를 써서, 회차 저장 시각(run_at)이 같은 초에 겹쳐
    # load_latest_run이 다른 테스트의 회차를 잘못 고르는 일이 없도록 한다.
    for test in tests:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            tmp_articles_dir = tmp_dir / "articles"
            tmp_articles_dir.mkdir()

            with patch.object(storage, "ARTICLES_DIR", tmp_articles_dir), \
                 patch.object(renderer, "OUTPUT_HTML_PATH", tmp_dir / "index.html"), \
                 patch.object(settings, "SETTINGS_FILE", tmp_dir / "settings.json"):
                try:
                    test()
                except AssertionError as e:
                    failures.append((test.__name__, str(e)))
                    print(f"실패: {test.__name__} — {e}")

    print()
    if failures:
        print(f"{len(failures)}개 테스트 실패:")
        for name, msg in failures:
            print(f"  - {name}: {msg}")
        sys.exit(1)
    else:
        print(f"모든 통합 테스트({len(tests)}개) 통과 (실제 data/ 폴더는 건드리지 않음)")
