# Design Ref: DESIGN.md §0 진입 화면 (home.html — 앱이 브라우저로 맨 처음 여는 화면), PRD.md 기능3
import html
import math
from pathlib import Path
from typing import Optional

from app.config import (
    COLOR_ACCENT,
    COLOR_BG,
    COLOR_BORDER,
    COLOR_CARD,
    COLOR_HEADER,
    COLOR_TEXT,
    COLOR_TEXT_MUTED,
    FONT_STACK,
    LANDING_HTML_PATH,
    LANDING_KEYWORD_COUNT,
    LOGO_PATH,
    SETTINGS_SERVER_PORT,
)
from app.atomic_write import atomic_write_text
from app.curation import filter_hidden
from app.settings import load_settings
from app.storage import load_latest_run
from app.summarizer import extract_keyword_frequencies

_PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>재정경제부 언론 모니터링</title>
<style>
  body {{
    margin: 0; background: {bg}; color: {text}; font-family: {font_stack};
    min-height: 100vh; display: flex; align-items: center; justify-content: center;
  }}
  .container {{
    max-width: 600px; margin: 24px auto; padding: 40px 24px; text-align: center;
    background: {card}; border: 1px solid {border}; border-radius: 8px;
  }}
  .logo {{ max-width: 160px; max-height: 160px; margin-bottom: 16px; border-radius: 50%; }}
  h1 {{ font-size: 1.3rem; font-weight: 600; margin: 0 0 32px; line-height: 1.5; color: {header}; }}
  h2 {{ font-size: 1rem; color: {text_muted}; font-weight: 500; margin-bottom: 12px; }}
  .wordcloud {{ position: relative; width: 300px; height: 220px; margin: 0 auto 36px; }}
  .wc-word {{ position: absolute; transform: translate(-50%, -50%); white-space: nowrap; font-weight: 600; }}
  .empty {{ color: {text_muted}; font-size: 0.9rem; margin-bottom: 36px; }}
  .nav {{ display: flex; flex-direction: column; gap: 12px; align-items: center; margin-bottom: 32px; }}
  .nav a {{
    background: {accent}; color: #ffffff; border: none; border-radius: 6px;
    padding: 10px 24px; font-size: 1.05rem; text-decoration: none; display: inline-block; width: 200px;
  }}
  .nav a:hover {{ background: {header}; }}
  .contact {{ color: {text_muted}; font-size: 0.85rem; }}
  .contact a {{ color: {accent}; }}
</style>
</head>
<body>
<div class="container">
  {logo_html}
  <h1>재정경제부 온라인 뉴스 모아보기 🧺👀</h1>
  {wordcloud_html}
  <div class="nav">
    <a href="index.html">👓 스크랩 보러 가기</a>
    <a href="http://127.0.0.1:{settings_port}/">⚙️ 설정</a>
  </div>
  <p class="contact">문의 📧 <a href="mailto:sweetgreetings@naver.com">sweetgreetings@naver.com</a></p>
</div>
</body>
</html>
"""

# [수정: 2026-07-24] 무궁화를 떠올리도록 단어를 가운데(1위)+안쪽 고리(금색)+바깥 고리(분홍)
# 세 층으로 방사형 배치한다. 실제 꽃 그림은 안 그린다 — 단어 배치만으로 충분하다는 피드백.
_INNER_FONT_RANGE = (1.05, 1.35)
_OUTER_FONT_RANGE = (0.8, 1.1)
# [수정: 2026-07-24] 색 배정을 "1위=금색(가운데, 굵게) → 중간=빨강(안쪽 고리) →
# 나머지=분홍(바깥 고리)" 순으로 재조정. 순수 노랑은 밝은 배경에서 안 보여 짙은
# 금색을 쓴다.
_CENTER_COLOR = "#B8860B"
_MID_COLOR = "#C81E4C"
_PETAL_COLORS = ["#D6499C", "#C43D91", "#B8348A"]  # 분홍 계열, 바깥 고리에서 순환 사용


def _place_ring(items: list, radius_pct: float, colors: list, size_range: tuple, min_count: int, max_count: int) -> list:
    spans = []
    count = len(items)
    for i, (word, freq) in enumerate(items):
        angle = math.radians((360 / count) * i - 90) if count else 0
        top = 50 + radius_pct * math.sin(angle)
        left = 50 + radius_pct * math.cos(angle)
        if max_count == min_count:
            size = sum(size_range) / 2
        else:
            ratio = (freq - min_count) / (max_count - min_count)
            size = size_range[0] + ratio * (size_range[1] - size_range[0])
        color = colors[i % len(colors)]
        spans.append(
            f'<span class="wc-word" style="top:{top:.1f}%; left:{left:.1f}%; '
            f'font-size:{size:.2f}rem; color:{color};">{html.escape(word)}</span>'
        )
    return spans


def render_word_cloud(freqs: list) -> str:
    """(단어, 빈도) 목록을 무궁화를 연상시키는 방사형 배치로 렌더링한다 (PRD.md 기능3 규칙 3).

    통계적으로 정확할 필요는 없는 눈요기용이다. 1위 단어는 가운데에 가장 크고 굵은
    금색으로, 2~4위는 안쪽 고리에 빨강으로, 나머지는 바깥 고리에 분홍 계열로 돌아가며
    배치한다 — 실제 꽃 그림 없이 단어 배치만으로 무궁화 느낌을 낸다. 글자 사이 여백이
    넓다는 피드백으로 고리 반지름을 좁혀 중앙 단어를 중심으로 촘촘하게 모았다.
    """
    if not freqs:
        return '<p class="empty">아직 수집된 키워드가 없습니다.</p>'

    top_word, _ = freqs[0]
    rest = freqs[1:]
    inner, outer = rest[:3], rest[3:]
    counts = [c for _, c in freqs]
    min_count, max_count = min(counts), max(counts)

    spans = [
        f'<span class="wc-word" style="top:50%; left:50%; font-size:2.1rem; '
        f'color:{_CENTER_COLOR}; font-weight:700;">{html.escape(top_word)}</span>'
    ]
    spans += _place_ring(inner, 19, [_MID_COLOR], _INNER_FONT_RANGE, min_count, max_count)
    spans += _place_ring(outer, 33, _PETAL_COLORS, _OUTER_FONT_RANGE, min_count, max_count)
    return f'<div class="wordcloud">{"".join(spans)}</div>'


def _render_logo() -> str:
    """LOGO_PATH 파일이 있으면 보여주고, 없으면 자리를 아예 만들지 않는다 (깨진 이미지 아이콘 방지)."""
    if LOGO_PATH.exists():
        return f'<img class="logo" src="{LOGO_PATH.name}" alt="로고">'
    return ""


def render_landing_page(freqs: list) -> str:
    """진입 화면 HTML을 렌더링한다 (PRD.md 기능3)."""
    return _PAGE_TEMPLATE.format(
        font_stack=FONT_STACK,
        logo_html=_render_logo(),
        wordcloud_html=render_word_cloud(freqs),
        settings_port=SETTINGS_SERVER_PORT,
        bg=COLOR_BG,
        card=COLOR_CARD,
        header=COLOR_HEADER,
        accent=COLOR_ACCENT,
        text=COLOR_TEXT,
        text_muted=COLOR_TEXT_MUTED,
        border=COLOR_BORDER,
    )


def generate_landing_page(keywords: Optional[list] = None) -> Path:
    """저장된 최신 회차의 기사 제목에서 당일 주요 키워드를 뽑아 home.html을 렌더링한다.

    generate_screen과 달리, 아직 저장된 회차가 없어도 예외를 내지 않고 빈 화면을
    보여준다 — 진입 화면은 앱이 가장 먼저 여는 화면이라, 오늘 첫 스크랩 전에도
    떠 있어야 한다.
    """
    keywords = keywords if keywords is not None else load_settings()["keywords"]
    run = load_latest_run()
    articles = filter_hidden(run["articles"]) if run else []
    freqs = extract_keyword_frequencies(articles, keywords, top_n=LANDING_KEYWORD_COUNT)
    html_text = render_landing_page(freqs)
    atomic_write_text(LANDING_HTML_PATH, html_text)
    return LANDING_HTML_PATH
