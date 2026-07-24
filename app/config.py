# Design Ref: DESIGN.md §3 기술 선택 — 서버 프레임워크 없이 .env에서 네이버 API 키를 불러오는 설정 모듈
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

NAVER_CLIENT_ID = os.getenv("NAVER_CLIENT_ID")
NAVER_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET")

if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
    raise RuntimeError(
        ".env 파일에 NAVER_CLIENT_ID / NAVER_CLIENT_SECRET이 설정되어 있지 않습니다."
    )

# PRD.md 기능1 규칙 2 — 기본 검색 키워드 (설정 화면에서 최대 7개까지 등록/수정/삭제 가능)
DEFAULT_KEYWORDS = ["재정경제부", "재경부"]

# PRD.md 기능1 규칙 1 — 자동 실행 시각의 기본값(설정 화면에서 바꾸기 전 최초 상태).
# 스케줄러가 "HH:MM" 문자열을 사전식으로 비교하므로, 반드시 24시간제 제로패딩 형식으로
# 적어야 한다 (예: "9:00"이 아니라 "09:00"). 패딩이 깨지면 시각 정렬이 어긋난다.
SCHEDULE_TIMES = ["09:00", "10:30", "13:30", "16:30"]
# PRD.md 기능1 규칙 20 — [추가: 2026-07-24] 설정 화면에서 등록 가능한 시각 개수 범위.
# 너무 잦으면(예: 5분 간격) 거의 같은 내용이 계속 새 회차로 쌓여 "지난 기사" 목록만
# 어수선해지므로, 업무 시간 내 촘촘히 잡아도(1~2시간 간격) 충분한 상한으로 10개를 둔다.
MIN_SCHEDULE_TIMES = 1
MAX_SCHEDULE_TIMES = 10

# PRD.md 기능1 규칙 22 — [추가: 2026-07-24, 수정: 2026-07-24] 메인 화면 자동 새로고침 간격(초).
# 실무자가 바로바로 확인하고 싶다는 요청으로 3분에서 1분으로 단축.
REFRESH_INTERVAL_SEC = 60

# PRD.md 7절 — 수집 데이터 보관 기간
RETENTION_DAYS = 7

# PRD.md 기능1 규칙 8 — 스크랩 실패 시 재시도 정책 (5분 간격, 최대 3회 재시도)
MAX_RETRIES = 3
RETRY_INTERVAL_SEC = 300

# PRD.md 디자인 방향 — [수정: 2026-07-24] 어두운 남색 배경에 흰 글자(구버전)가 링크 등에서
# 가독성이 떨어진다는 피드백으로, 밝은 배경 + 카드 구조의 라이트 테마로 전환.
COLOR_BG = "#F8FAFC"
COLOR_CARD = "#FFFFFF"
COLOR_HEADER = "#1E3A5F"
COLOR_ACCENT = "#2563EB"
COLOR_TEXT = "#1F2937"
COLOR_TEXT_MUTED = "#6B7280"
COLOR_BORDER = "#E5E7EB"
COLOR_HOVER = "#EFF6FF"
COLOR_ERROR = "#DC2626"  # 밝은 배경에서도 잘 보이도록 새로 정한 오류 문구 색상

# PRD.md 기능1 규칙 6 — 요약 내 형광펜 단어 하이라이트 색상·기본값·최대 개수.
# [수정: 2026-07-23] 하이라이트 대상은 검색 키워드(DEFAULT_KEYWORDS)와 완전히 별개 설정이다.
HIGHLIGHT_COLOR = "#C6FF00"
# [추가: 2026-07-24] 하이라이트 배경(연두색) 위 글자색. 기본 글자색을 그대로 쓰면 연두색
# 배경과 대비가 약해 잘 안 보이므로, 짙은 색으로 바꿔 대비를 준다.
HIGHLIGHT_TEXT_COLOR = COLOR_TEXT
DEFAULT_HIGHLIGHT_KEYWORDS = ["재정경제부", "재경부"]
MAX_HIGHLIGHT_KEYWORDS = 3

# PRD.md 기능2 규칙 1 — 소제목은 매 회차 자동 생성, 최대 5개까지만
MAX_SUBHEADINGS = 5

# PRD.md 기능2 규칙 4·5 — 전체 주요 키워드 개수, 소제목별 요약 길이 제한
MAIN_KEYWORD_COUNT = 5
SUMMARY_MAX_SENTENCES = 3
SUMMARY_MAX_CHARS = 150

# DESIGN.md §3 — SQLite 대신 로컬 JSON 파일로 기사 데이터 저장
DATA_DIR = BASE_DIR / "data"
SETTINGS_FILE = DATA_DIR / "settings.json"
ARTICLES_DIR = DATA_DIR / "articles"
# PRD.md 기능1 규칙 19 — [추가: 2026-07-24] 숨긴 기사 URL 목록 (원본 회차 데이터와 분리 보관)
HIDDEN_ARTICLES_FILE = DATA_DIR / "hidden_articles.json"
# PRD.md 기능1 규칙 21 — [추가: 2026-07-24] 소제목 경계를 넘어 수동으로 옮긴 기사의 강제 소제목 기록
GROUP_OVERRIDES_FILE = DATA_DIR / "group_overrides.json"
# PRD.md 기능2 규칙 8 — [추가: 2026-07-24] 자동 생성된 소제목 단어에 사용자가 붙인 표시용 이름
GROUP_LABELS_FILE = DATA_DIR / "group_labels.json"

# DESIGN.md §1/§3 — 스크립트가 생성하는 화면 파일
OUTPUT_HTML_PATH = BASE_DIR / "index.html"
HISTORY_HTML_PATH = BASE_DIR / "history.html"
LANDING_HTML_PATH = BASE_DIR / "home.html"
LOGO_PATH = BASE_DIR / "logo.svg"

# DESIGN.md §3 — 설정 저장을 위한 유일한 "서버" 예외. 로컬(127.0.0.1)에서만 연다.
SETTINGS_SERVER_PORT = 8765

# PRD.md 기능1 규칙 15 — [수정: 2026-07-23] 검색 키워드는 최소 1개, 최대 7개까지 등록 가능
MIN_KEYWORDS = 1
MAX_KEYWORDS = 7

# PRD.md 기능1 규칙 18 — 우선 Pretendard, 없으면 Noto Sans KR, 그래도 없으면 시스템 기본
FONT_STACK = "'Pretendard', 'Noto Sans KR', sans-serif"

# PRD.md 기능1 규칙 5 — [추가: 2026-07-23] 기사 출력 줄 형식 템플릿 (URL 줄·날짜 미표시는 범위 밖)
DEFAULT_ARTICLE_LINE_TEMPLATE = "ㅇ ({outlet}) {title}"

# PRD.md 기능3 규칙 3 — [추가: 2026-07-23] 진입 화면 워드클라우드에 뽑을 최대 키워드 개수
LANDING_KEYWORD_COUNT = 12

DATA_DIR.mkdir(exist_ok=True)
ARTICLES_DIR.mkdir(exist_ok=True)
