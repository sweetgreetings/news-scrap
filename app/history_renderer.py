# Design Ref: DESIGN.md §1 "지난 기사 더보기" — 최근 7일 회차를 날짜별 -> 시간대별 토글로 조회
import html
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.config import (
    COLOR_ACCENT,
    COLOR_BG,
    COLOR_BORDER,
    COLOR_CARD,
    COLOR_ERROR,
    COLOR_HEADER,
    COLOR_TEXT,
    COLOR_TEXT_MUTED,
    DEFAULT_ARTICLE_LINE_TEMPLATE,
    DEFAULT_HIGHLIGHT_KEYWORDS,
    FONT_STACK,
    HISTORY_HTML_PATH,
    SETTINGS_SERVER_PORT,
)
from app.atomic_write import atomic_write_text
from app.curation import filter_hidden
from app.renderer import render_article
from app.settings import load_settings
from app.storage import list_all_runs

_PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>지난 기사 더보기</title>
<style>
  body {{ margin: 0; background: {bg}; color: {text}; font-family: {font_stack}; }}
  .container {{
    max-width: 800px; margin: 24px auto; padding: 24px; background: {card};
    border: 1px solid {border}; border-radius: 8px;
  }}
  h1 {{ font-size: 1.3rem; color: {header}; }}
  .empty {{ color: {muted}; margin-top: 12px; }}
  details.date {{ margin: 10px 0; border-bottom: 1px solid {border}; padding-bottom: 8px; }}
  details.date > summary {{ cursor: pointer; font-size: 1.1rem; color: {header}; }}
  details.slot {{ margin: 8px 0 8px 20px; }}
  details.slot > summary {{ cursor: pointer; }}
  .article {{ margin: 10px 0 10px 20px; line-height: 1.5; }}
  .article summary {{ cursor: pointer; }}
  .article summary::marker {{ color: {muted}; }}
  .article-summary {{ margin: 6px 0 4px 20px; color: {text}; font-size: 0.95rem; }}
  .article-footer {{ display: flex; align-items: center; gap: 8px; }}
  .article .url {{ flex: 1; color: {muted}; font-size: 0.9rem; word-break: break-all; text-decoration: underline; }}
  .hide-btn {{
    flex-shrink: 0; background: transparent; border: none; color: {muted}; font-size: 1rem;
    cursor: pointer; padding: 2px 6px; user-select: none; -webkit-user-select: none;
  }}
  .hide-btn:hover {{ color: {error}; }}
  .back {{
    display: inline-block; margin-top: 24px; background: {accent}; color: #fff; border: none;
    border-radius: 4px; padding: 6px 14px; text-decoration: none; user-select: none; -webkit-user-select: none;
  }}
  .back:hover {{ background: {header}; }}
</style>
</head>
<body>
<div class="container">
  <h1>📅 지난 기사 더보기 (최근 7일)</h1>
  {body}
  <p><a class="back" href="index.html">메인 화면으로</a></p>
</div>
<script>
function hideArticle(btn) {{
  var url = btn.dataset.url;
  var article = btn.closest(".article");
  fetch("http://127.0.0.1:{settings_port}/hide-article", {{
    method: "POST", keepalive: true,
    headers: {{"Content-Type": "application/x-www-form-urlencoded"}},
    body: new URLSearchParams({{url: url}})
  }}).then(function(res) {{
    if (res.ok) {{ article.remove(); }}
    else {{ alert("숨기기에 실패했습니다. 다시 시도해주세요."); }}
  }}).catch(function() {{
    alert("숨기기에 실패했습니다 — 앱이 실행 중인지 확인해주세요.");
  }});
}}
</script>
</body>
</html>
"""


def _render_slot(run: dict, index: int, highlight_words: list, line_template: str) -> str:
    """회차 하나(시간대)를 토글로 렌더링한다. 소제목 재분류는 하지 않고 언론사
    우선순위 순 목록만 보여준다 (당시 화면을 그대로 복원할 필요는 없어 단순화)."""
    articles = filter_hidden(run["articles"])
    if not articles:
        body = '<p class="empty">하나도 없어요</p>'
    else:
        body = "\n".join(render_article(a, highlight_words, line_template) for a in articles)
    label = html.escape(f"{index}. {run['run_slot']}")
    return f'<details class="slot"><summary>{label}</summary>{body}</details>'


def _date_label(run_date, today) -> str:
    return f"당일 ({run_date.strftime('%m-%d')})" if run_date == today else run_date.strftime("%m-%d")


def _theme() -> dict:
    """이 페이지 템플릿이 공유하는 색상·폰트·포트 값. `.format(**_theme(), ...)`로 채운다."""
    return {
        "font_stack": FONT_STACK,
        "settings_port": SETTINGS_SERVER_PORT,
        "bg": COLOR_BG,
        "card": COLOR_CARD,
        "header": COLOR_HEADER,
        "accent": COLOR_ACCENT,
        "text": COLOR_TEXT,
        "muted": COLOR_TEXT_MUTED,
        "border": COLOR_BORDER,
        "error": COLOR_ERROR,
    }


def render_history_page(
    runs: list,
    highlight_words: Optional[list] = None,
    line_template: Optional[str] = None,
) -> str:
    """저장된 회차를 날짜별(내림차순) -> 시간대별(오름차순) 토글로 렌더링한다 (PRD.md 기능2 규칙 6).

    highlight_words: 형광펜 단어(규칙6) — 검색 키워드와 무관한 별도 설정.
    line_template: 기사 첫 줄 형식(규칙5) — 메인 화면과 동일한 설정을 공유한다.
    """
    highlight_words = highlight_words if highlight_words is not None else DEFAULT_HIGHLIGHT_KEYWORDS
    line_template = line_template if line_template is not None else DEFAULT_ARTICLE_LINE_TEMPLATE

    if not runs:
        return _PAGE_TEMPLATE.format(
            body='<p class="empty">아직 저장된 지난 기사가 없습니다.</p>',
            **_theme(),
        )

    today = datetime.now().date()
    grouped: "OrderedDict" = OrderedDict()
    for run in runs:
        run_date = datetime.fromisoformat(run["run_at"]).date()
        grouped.setdefault(run_date, []).append(run)

    sections = []
    for run_date in sorted(grouped, reverse=True):
        day_runs = sorted(grouped[run_date], key=lambda r: r["run_slot"])
        slots_html = "\n".join(
            _render_slot(r, i, highlight_words, line_template) for i, r in enumerate(day_runs, start=1)
        )
        date_label = html.escape(_date_label(run_date, today))
        sections.append(f'<details class="date"><summary>{date_label}</summary>{slots_html}</details>')

    return _PAGE_TEMPLATE.format(body="\n".join(sections), **_theme())


def generate_history_page(highlight_words: Optional[list] = None, line_template: Optional[str] = None) -> Path:
    """저장된 모든 회차(최근 7일, 보관 정책과 연동)를 history.html로 렌더링한다."""
    if highlight_words is None or line_template is None:
        settings = load_settings()
        highlight_words = highlight_words if highlight_words is not None else settings["highlight_keywords"]
        line_template = line_template if line_template is not None else settings["article_line_template"]
    html_text = render_history_page(list_all_runs(), highlight_words, line_template)
    atomic_write_text(HISTORY_HTML_PATH, html_text)
    return HISTORY_HTML_PATH
