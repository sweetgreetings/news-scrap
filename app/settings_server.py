# Design Ref: DESIGN.md §1 설정 화면 목업(메뉴+하위 6페이지), §3 "최소 로컬 서버" (PRD 규칙 17)
import html
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Optional
from urllib.parse import parse_qs

from app.config import (
    COLOR_ACCENT,
    COLOR_BG,
    COLOR_BORDER,
    COLOR_CARD,
    COLOR_ERROR,
    COLOR_HEADER,
    COLOR_HOVER,
    COLOR_TEXT,
    COLOR_TEXT_MUTED,
    FONT_STACK,
    HISTORY_HTML_PATH,
    LANDING_HTML_PATH,
    LOGO_PATH,
    MAX_HIGHLIGHT_KEYWORDS,
    MAX_KEYWORDS,
    MAX_SCHEDULE_TIMES,
    MIN_SCHEDULE_TIMES,
    OUTPUT_HTML_PATH,
    SETTINGS_SERVER_PORT,
)
from app.curation import (
    hide_article,
    load_group_overrides,
    load_hidden_urls,
    move_article,
    set_group_label,
    set_group_override,
    unhide_article,
)
from app.history_renderer import generate_history_page
from app.landing_renderer import generate_landing_page
from app.naver_api import OUTLET_CATEGORIES
from app.renderer import apply_line_template, generate_screen
from app.settings import (
    SettingsError,
    load_settings,
    move_outlet,
    save_article_line_template,
    save_highlight_keywords,
    save_outlet_selection,
    save_schedule_times,
    save_settings,
)
from app.storage import list_all_runs, load_latest_run, update_run_articles

# 페이지마다 공통으로 쓰는 스타일 조각. 아직 .format()으로 값을 채우기 전(중괄호가 전부
# {{ }}로 이중화된 상태)이라, 각 페이지 템플릿에 문자열로 이어붙인 뒤 페이지 전체를
# 한 번에 .format()해야 한다 — 미리 풀어서 이어붙이면 CSS의 실제 중괄호가 남아
# 바깥쪽 .format() 호출과 충돌한다.
_BASE_STYLE = """
  body {{ margin: 0; background: {bg}; color: {text}; font-family: {font_stack}; }}
  .container {{
    max-width: 480px; margin: 24px auto; padding: 24px; background: {card};
    border: 1px solid {border}; border-radius: 8px;
  }}
  h1 {{ font-size: 1.3rem; color: {header}; }}
  .hint {{ color: {muted}; font-size: 0.85rem; margin-bottom: 16px; }}
  .error {{ color: {error}; margin: 12px 0; }}
  .nav {{ margin-top: 24px; display: flex; gap: 8px; }}
  button, a.btn {{
    background: {accent}; color: #ffffff; border: none; border-radius: 4px;
    padding: 8px 16px; font-size: 1rem; cursor: pointer; text-decoration: none; display: inline-block;
  }}
  button:hover, a.btn:hover {{ background: {header}; }}
  button:disabled {{ background: {border}; color: {muted}; cursor: not-allowed; }}
  input[type=text], input[type=time] {{
    background: {bg}; color: {text}; border: 1px solid {border}; border-radius: 4px;
    padding: 6px 10px; font-size: 1rem;
  }}
"""

_NAV_HTML = (
    '<div class="nav">'
    '<a class="btn" href="/">⚙️ 설정 메뉴로</a>'
    '<a class="btn" href="{index_href}">메인 화면으로</a>'
    "</div>"
)

_MENU_TEMPLATE = (
    """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>설정</title>
<style>"""
    + _BASE_STYLE
    + """
  .menu a {{
    display: block; margin: 4px 0; padding: 10px 12px; font-size: 1.05rem;
    color: {accent}; text-decoration: none; border-radius: 6px;
  }}
  .menu a:hover {{ background: {hover}; }}
  .menu-group + .menu-group {{ margin-top: 16px; padding-top: 16px; border-top: 1px solid {border}; }}
</style>
</head>
<body>
<div class="container">
  <h1>⚙️ 설정</h1>
  <div class="menu">
    <div class="menu-group">
      <a href="/keywords">🔎 검색 키워드</a>
      <a href="/outlets">📰 주요 언론사 선택 및 순서 지정</a>
      <a href="/schedule">⏰ 스크랩 시간 및 횟수</a>
    </div>
    <div class="menu-group">
      <a href="/highlight">💡 형광펜 단어</a>
      <a href="/format">🖊️ 본문 형식</a>
    </div>
    <div class="menu-group">
      <a href="/hidden">🗑️ 숨긴 기사 관리</a>
    </div>
  </div>
  <p><a class="btn" href="{index_href}">메인 화면으로</a></p>
</div>
</body>
</html>
"""
)

_KEYWORDS_TEMPLATE = (
    """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>검색 키워드</title>
<style>"""
    + _BASE_STYLE
    + """
  .keyword-row {{ margin: 8px 0; }}
  .keyword-row input {{ width: 220px; }}
  .mode {{ margin: 20px 0; }}
  .mode label {{ margin-right: 16px; }}
</style>
</head>
<body>
<div class="container">
  <h1>🔎 검색 키워드 (최대 {max_keywords}개)</h1>
  <p class="hint">빈 칸으로 두면 그 자리는 삭제됩니다. 최소 1개는 남겨야 합니다.</p>
  {error_html}
  <form method="POST" action="/save">
    {keyword_inputs}
    {mode_html}
    <p><button type="submit">저장</button></p>
  </form>
  """
    + _NAV_HTML
    + """
</div>
</body>
</html>
"""
)

_OUTLETS_TEMPLATE = (
    """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>주요 언론사 선택 및 순서 지정</title>
<style>"""
    + _BASE_STYLE
    + """
  .category {{ margin: 12px 0; }}
  .category-name {{ color: {muted}; font-size: 0.85rem; margin-bottom: 4px; }}
  .category label {{ margin-right: 14px; white-space: nowrap; }}
  .order-list {{ margin-top: 16px; }}
  .order-row {{ display: flex; align-items: center; gap: 8px; margin: 4px 0; }}
  .order-row .name {{ width: 160px; }}
  .order-row form {{ display: inline; }}
  .order-row button {{ padding: 2px 10px; font-size: 0.85rem; }}
</style>
</head>
<body>
<div class="container">
  <h1>📰 주요 언론사 선택 및 순서 지정</h1>
  <p class="hint">
    스크랩 원하는 언론사를 클릭해주세요. 선택한 언론사의 네이버 뉴스 기사만 스크랩합니다.<br>
    순서를 바꾸려면 아래 "현재 선택 순서" 목록의 ↑/↓ 버튼을 눌러주세요.<br>
    하나도 안 고르면 기본 우선순위(방송사 → 주요 언론사 → 그 외)로 전체 언론사를 수집합니다.
  </p>
  {error_html}
  <form method="POST" action="/save-outlets">
    {outlet_categories}
    <p><button type="submit">저장</button></p>
  </form>
  {outlet_order_html}
  """
    + _NAV_HTML
    + """
</div>
</body>
</html>
"""
)

_HIGHLIGHT_TEMPLATE = (
    """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>형광펜 단어</title>
<style>"""
    + _BASE_STYLE
    + """
  .keyword-row {{ margin: 8px 0; }}
  .keyword-row input {{ width: 220px; }}
</style>
</head>
<body>
<div class="container">
  <h1>💡 형광펜 단어</h1>
  <p class="hint">
    각 기사 아래 요약본에 아래 키워드가 있을 경우 형광펜 처리 됩니다.<br>
    검색 키워드와는 별개입니다. ※ 최대 {max_highlight}개까지 입력 가능
  </p>
  {error_html}
  <form method="POST" action="/save-highlight">
    {highlight_inputs}
    <p><button type="submit">저장</button></p>
  </form>
  """
    + _NAV_HTML
    + """
</div>
</body>
</html>
"""
)


_FORMAT_TEMPLATE = (
    """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>본문 형식</title>
<style>"""
    + _BASE_STYLE
    + """
  input[type=text] {{ width: 100%; max-width: 360px; box-sizing: border-box; }}
  .preview {{ margin-top: 12px; color: {muted}; }}
  code {{ background: {bg}; border: 1px solid {border}; padding: 2px 6px; border-radius: 4px; color: {text}; }}
</style>
</head>
<body>
<div class="container">
  <h1>🖊️ 본문 형식</h1>
  <p class="hint">
    기사 목록 첫 줄의 형식을 바꿀 수 있습니다.<br>
    <code>{{outlet}}</code>은 언론사명, <code>{{title}}</code>은 기사 제목으로 바뀝니다.<br>
    ※ 두 자리표시자를 각각 정확히 1번씩 포함해야 합니다. (URL 줄·게시일자는 이 설정과 무관합니다)
  </p>
  {error_html}
  <form method="POST" action="/save-format">
    <input type="text" name="line_template" value="{template_value}">
    <p class="preview">미리보기: <code>{preview}</code></p>
    <p><button type="submit">저장</button></p>
  </form>
  """
    + _NAV_HTML
    + """
</div>
</body>
</html>
"""
)


_SCHEDULE_TEMPLATE = (
    """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>스크랩 시간 및 횟수</title>
<style>"""
    + _BASE_STYLE
    + """
  .time-row {{ margin: 8px 0; }}
  .add-row button {{ background: {card}; color: {accent}; border: 1px solid {accent}; }}
  .add-row button:hover {{ background: {hover}; }}
  .add-row button:disabled {{ background: {border}; color: {muted}; border-color: {border}; }}
</style>
</head>
<body>
<div class="container">
  <h1>⏰ 스크랩 시간 및 횟수</h1>
  <p class="hint">
    스크랩을 실행할 시각을 등록하세요. 등록한 개수만큼 하루에 자동 실행됩니다
    (최소 {min_times}개, 최대 {max_times}개). 빈 칸으로 두면 그 자리는 삭제됩니다.<br>
    화면 상단 "언론 모니터링 [시각] 기준" 제목도 여기서 설정한 시각을 그대로 따라갑니다.
  </p>
  {error_html}
  <form method="POST" action="/save-schedule">
    {time_inputs}
    <p class="add-row"><button type="submit" formaction="/schedule/add-slot"{add_disabled}>+ 시간대 추가</button></p>
    <p><button type="submit">저장</button></p>
  </form>
  """
    + _NAV_HTML
    + """
</div>
</body>
</html>
"""
)


_HIDDEN_TEMPLATE = (
    """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>숨긴 기사 관리</title>
<style>"""
    + _BASE_STYLE
    + """
  .hidden-row {{ display: flex; align-items: center; justify-content: space-between; gap: 8px; margin: 10px 0; }}
  .hidden-row .name {{ flex: 1; font-size: 0.95rem; }}
  .hidden-row form {{ display: inline; flex-shrink: 0; }}
</style>
</head>
<body>
<div class="container">
  <h1>🗑️ 숨긴 기사 관리</h1>
  <p class="hint">
    화면의 🗑️ 버튼으로 숨긴 기사 목록입니다. 원본 데이터는 지워지지 않았으며,
    "되돌리기"를 누르면 숨긴 기사가 다시 화면에 보이게 됩니다.
  </p>
  {rows_html}
  """
    + _NAV_HTML
    + """
</div>
</body>
</html>
"""
)


def _render_keyword_inputs(keywords: list) -> str:
    rows = []
    for i in range(MAX_KEYWORDS):
        value = html.escape(keywords[i]) if i < len(keywords) else ""
        rows.append(
            f'<div class="keyword-row">'
            f'<input type="text" name="keyword{i + 1}" value="{value}" placeholder="키워드 {i + 1}">'
            f"</div>"
        )
    return "\n".join(rows)


_DEFAULT_VISIBLE_SLOTS = 4  # PRD 규칙20 — 처음엔 4개만 보이고, 그 이상은 "+"로 늘린다


def _render_time_inputs(schedule_times: list, slots: int) -> str:
    rows = []
    for i in range(slots):
        value = html.escape(schedule_times[i]) if i < len(schedule_times) else ""
        rows.append(
            f'<div class="time-row"><input type="time" name="time{i + 1}" value="{value}"></div>'
        )
    return "\n".join(rows)


def _render_highlight_inputs(highlight_words: list) -> str:
    rows = []
    for i in range(MAX_HIGHLIGHT_KEYWORDS):
        value = html.escape(highlight_words[i]) if i < len(highlight_words) else ""
        rows.append(
            f'<div class="keyword-row">'
            f'<input type="text" name="highlight{i + 1}" value="{value}" placeholder="형광펜 단어 {i + 1}">'
            f"</div>"
        )
    return "\n".join(rows)


def _render_mode(settings: dict) -> str:
    # DESIGN.md §1 — 키워드가 2개 이상 등록됐을 때만 OR/AND 선택 항목을 보여준다.
    if len(settings["keywords"]) < 2:
        return ""
    or_checked = "checked" if settings["mode"] == "OR" else ""
    and_checked = "checked" if settings["mode"] == "AND" else ""
    return (
        '<div class="mode">검색 방식: '
        f'<label><input type="radio" name="mode" value="OR" {or_checked}> OR - 하나라도 포함</label>'
        f'<label><input type="radio" name="mode" value="AND" {and_checked}> AND - 모두 포함</label>'
        "</div>"
    )


def _render_outlet_categories(selected: list) -> str:
    """카테고리별 언론사 체크박스를 렌더링한다 (PRD.md 기능1 규칙 16)."""
    selected_set = set(selected)
    blocks = []
    for category, names in OUTLET_CATEGORIES.items():
        checkboxes = "\n".join(
            f'<label><input type="checkbox" name="outlet" value="{html.escape(name)}"'
            f'{" checked" if name in selected_set else ""}> {html.escape(name)}</label>'
            for name in names
        )
        blocks.append(
            f'<div class="category"><div class="category-name">&lt;{html.escape(category)}&gt;</div>{checkboxes}</div>'
        )
    return "\n".join(blocks)


def _render_outlet_order(order: list) -> str:
    """현재 선택된 언론사를 순서대로, ↑/↓ 버튼과 함께 보여준다 (드래그 앤 드롭 대신 가벼운 방식)."""
    if not order:
        return ""
    rows = []
    last_index = len(order) - 1
    for i, name in enumerate(order):
        escaped = html.escape(name)
        up_button = (
            f'<form method="POST" action="/move-outlet">'
            f'<input type="hidden" name="outlet" value="{escaped}">'
            f'<input type="hidden" name="direction" value="up">'
            f'<button type="submit"{" disabled" if i == 0 else ""}>↑</button></form>'
        )
        down_button = (
            f'<form method="POST" action="/move-outlet">'
            f'<input type="hidden" name="outlet" value="{escaped}">'
            f'<input type="hidden" name="direction" value="down">'
            f'<button type="submit"{" disabled" if i == last_index else ""}>↓</button></form>'
        )
        rows.append(f'<div class="order-row"><span class="name">{i + 1}. {escaped}</span>{up_button}{down_button}</div>')
    return f'<div class="order-list"><p class="hint">현재 선택 순서:</p>{"".join(rows)}</div>'


def _theme() -> dict:
    """모든 설정 페이지 템플릿이 공유하는 색상·폰트 값. `.format(**_theme(), ...)`로 채운다."""
    return {
        "font_stack": FONT_STACK,
        "bg": COLOR_BG,
        "card": COLOR_CARD,
        "header": COLOR_HEADER,
        "accent": COLOR_ACCENT,
        "text": COLOR_TEXT,
        "muted": COLOR_TEXT_MUTED,
        "border": COLOR_BORDER,
        "hover": COLOR_HOVER,
        "error": COLOR_ERROR,
    }


# [수정: 2026-07-24] "메인 화면으로" 링크가 예전엔 file:// 경로를 가리켰는데, 최신
# 브라우저(사파리 포함)는 보안상 http 페이지에서 file 경로로의 이동을 막아 버튼이
# 먹통이었다. 그래서 설정 서버가 정적 화면 파일도 같은 127.0.0.1 출처로 함께 서빙하고,
# 이 링크도 file:// 대신 그 http 주소를 가리키도록 바꿨다.
_STATIC_HTML_ROUTES = {
    "/index.html": lambda: OUTPUT_HTML_PATH,
    "/history.html": lambda: HISTORY_HTML_PATH,
    "/home.html": lambda: LANDING_HTML_PATH,
}


def _home_href() -> str:
    # [수정: 2026-07-24] 설정 화면의 "메인 화면으로"는 스크랩 결과 화면(index.html)이
    # 아니라 로고가 있는 진입 화면(home.html)으로 가도록 변경 — 사용자 요청.
    return f"http://127.0.0.1:{SETTINGS_SERVER_PORT}/home.html"


def render_menu_page() -> str:
    """설정 메뉴 화면을 렌더링한다 (PRD.md 기능1 규칙 17)."""
    return _MENU_TEMPLATE.format(**_theme(), index_href=_home_href())


def render_keywords_page(settings: dict, error: str = "") -> str:
    """검색 키워드 설정 화면을 렌더링한다 (PRD.md 기능1 규칙 15)."""
    error_html = f'<p class="error">{html.escape(error)}</p>' if error else ""
    return _KEYWORDS_TEMPLATE.format(
        **_theme(),
        max_keywords=MAX_KEYWORDS,
        error_html=error_html,
        keyword_inputs=_render_keyword_inputs(settings["keywords"]),
        mode_html=_render_mode(settings),
        index_href=_home_href(),
    )


def render_outlets_page(settings: dict, error: str = "") -> str:
    """언론사 선택 화면을 렌더링한다 (PRD.md 기능1 규칙 16)."""
    error_html = f'<p class="error">{html.escape(error)}</p>' if error else ""
    outlet_order = settings.get("outlet_order", [])
    return _OUTLETS_TEMPLATE.format(
        **_theme(),
        error_html=error_html,
        outlet_categories=_render_outlet_categories(outlet_order),
        outlet_order_html=_render_outlet_order(outlet_order),
        index_href=_home_href(),
    )


def render_highlight_page(settings: dict, error: str = "") -> str:
    """형광펜 단어 설정 화면을 렌더링한다 (PRD.md 기능1 규칙 6)."""
    error_html = f'<p class="error">{html.escape(error)}</p>' if error else ""
    return _HIGHLIGHT_TEMPLATE.format(
        **_theme(),
        max_highlight=MAX_HIGHLIGHT_KEYWORDS,
        error_html=error_html,
        highlight_inputs=_render_highlight_inputs(settings.get("highlight_keywords", [])),
        index_href=_home_href(),
    )


def _render_schedule_preview(times: list, slots: int) -> str:
    """"+ 시간대 추가" 직후의 미리보기를 렌더링한다. render_schedule_page와 달리 저장된
    "설정"이 아니라 지금 입력하던 값을 그대로(정렬·빈칸 제거 없이) 다시 보여준다."""
    return _SCHEDULE_TEMPLATE.format(
        **_theme(),
        min_times=MIN_SCHEDULE_TIMES,
        max_times=MAX_SCHEDULE_TIMES,
        error_html="",
        time_inputs=_render_time_inputs(times, slots),
        add_disabled=" disabled" if slots >= MAX_SCHEDULE_TIMES else "",
        index_href=_home_href(),
    )


def render_schedule_page(settings: dict, error: str = "", slots: Optional[int] = None) -> str:
    """수집 시각/횟수 설정 화면을 렌더링한다 (PRD.md 기능1 규칙 20).

    slots를 생략하면 "저장된 개수, 최소 _DEFAULT_VISIBLE_SLOTS개"만큼 입력칸을 보여준다
    (처음엔 4개만 보이게). "+ 시간대 추가" 버튼을 누르면 slots를 1 늘려 다시 렌더링한다.
    """
    times = sorted(settings.get("schedule_times", []))
    if slots is None:
        slots = max(len(times), _DEFAULT_VISIBLE_SLOTS)
    slots = min(max(slots, len(times)), MAX_SCHEDULE_TIMES)
    error_html = f'<p class="error">{html.escape(error)}</p>' if error else ""
    return _SCHEDULE_TEMPLATE.format(
        **_theme(),
        min_times=MIN_SCHEDULE_TIMES,
        max_times=MAX_SCHEDULE_TIMES,
        error_html=error_html,
        time_inputs=_render_time_inputs(times, slots),
        add_disabled=" disabled" if slots >= MAX_SCHEDULE_TIMES else "",
        index_href=_home_href(),
    )


def render_format_page(settings: dict, error: str = "") -> str:
    """출력 형식 설정 화면을 렌더링한다 (PRD.md 기능1 규칙 5)."""
    error_html = f'<p class="error">{html.escape(error)}</p>' if error else ""
    template = settings.get("article_line_template", "")
    # 미리보기는 실제로 저장하기 전에 결과를 보여주는 용도라, 저장 여부와 무관하게
    # 항상 예시 언론사/제목으로 렌더링해본다 (템플릿이 잘못돼 있어도 여기선 안전한
    # apply_line_template의 단순 치환이라 오류가 날 일이 없다).
    preview = apply_line_template(html.escape(template), "한겨레", "예시 기사 제목입니다")
    return _FORMAT_TEMPLATE.format(
        **_theme(),
        error_html=error_html,
        template_value=html.escape(template),
        preview=preview,
        index_href=_home_href(),
    )


def _known_articles_by_url() -> dict:
    """숨긴 기사의 언론사·제목을 보여주려고, 최근 7일 회차에서 URL로 원본 정보를 찾는다
    (숨긴 목록 자체는 URL만 저장하므로)."""
    lookup = {}
    for run in list_all_runs():
        for article in run["articles"]:
            lookup.setdefault(article["url"], article)
    return lookup


def render_hidden_page() -> str:
    """숨긴 기사 목록과 되돌리기 버튼을 렌더링한다 (PRD.md 기능1 규칙 19)."""
    hidden_urls = sorted(load_hidden_urls())
    if not hidden_urls:
        rows_html = '<p class="hint">숨긴 기사가 없습니다.</p>'
    else:
        lookup = _known_articles_by_url()
        rows = []
        for url in hidden_urls:
            info = lookup.get(url)
            escaped_url = html.escape(url)
            label = f'({html.escape(info["outlet"])}) {html.escape(info["title"])}' if info else escaped_url
            rows.append(
                '<div class="hidden-row">'
                f"<span class=\"name\">{label}</span>"
                '<form method="POST" action="/unhide-article">'
                f'<input type="hidden" name="url" value="{escaped_url}">'
                "<button type=\"submit\">되돌리기</button>"
                "</form>"
                "</div>"
            )
        rows_html = "\n".join(rows)
    return _HIDDEN_TEMPLATE.format(**_theme(), rows_html=rows_html, index_href=_home_href())


class _SettingsHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in _STATIC_HTML_ROUTES:
            self._respond_static_html(_STATIC_HTML_ROUTES[self.path]())
        elif LOGO_PATH.exists() and self.path == f"/{LOGO_PATH.name}":
            self._respond_static_binary(LOGO_PATH, "image/svg+xml")
        elif self.path == "/":
            self._respond(render_menu_page())
        elif self.path == "/keywords":
            self._respond(render_keywords_page(load_settings()))
        elif self.path == "/outlets":
            self._respond(render_outlets_page(load_settings()))
        elif self.path == "/highlight":
            self._respond(render_highlight_page(load_settings()))
        elif self.path == "/format":
            self._respond(render_format_page(load_settings()))
        elif self.path == "/schedule":
            self._respond(render_schedule_page(load_settings()))
        elif self.path == "/hidden":
            self._respond(render_hidden_page())
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        form = parse_qs(self.rfile.read(length).decode("utf-8"))

        if self.path == "/save":
            self._handle_save_keywords(form)
        elif self.path == "/save-outlets":
            self._handle_save_outlets(form)
        elif self.path == "/move-outlet":
            self._handle_move_outlet(form)
        elif self.path == "/save-highlight":
            self._handle_save_highlight(form)
        elif self.path == "/save-format":
            self._handle_save_format(form)
        elif self.path == "/save-schedule":
            self._handle_save_schedule(form)
        elif self.path == "/schedule/add-slot":
            self._handle_add_schedule_slot(form)
        elif self.path == "/move-article":
            self._handle_move_article(form)
        elif self.path == "/rename-group":
            self._handle_rename_group(form)
        elif self.path == "/hide-article":
            self._handle_hide_article(form)
        elif self.path == "/unhide-article":
            self._handle_unhide_article(form)
        else:
            self.send_response(404)
            self.end_headers()

    def _handle_save_keywords(self, form: dict) -> None:
        keywords = [form.get(f"keyword{i + 1}", [""])[0] for i in range(MAX_KEYWORDS)]
        mode = form.get("mode", ["OR"])[0]
        try:
            save_settings(keywords, mode)
        except SettingsError as error:
            # 검증 실패 시 저장하지 않고, 입력했던 값을 그대로 보여주며 오류 메시지만 추가한다.
            attempted = {**load_settings(), "keywords": [k for k in keywords if k.strip()], "mode": mode}
            self._respond(render_keywords_page(attempted, error=str(error)))
            return
        self._redirect("/keywords")

    def _handle_save_outlets(self, form: dict) -> None:
        selected = form.get("outlet", [])
        try:
            save_outlet_selection(selected)
        except SettingsError as error:
            attempted = {**load_settings(), "outlet_order": selected}
            self._respond(render_outlets_page(attempted, error=str(error)))
            return
        self._redirect("/outlets")

    def _handle_move_outlet(self, form: dict) -> None:
        outlet = form.get("outlet", [""])[0]
        direction = form.get("direction", [""])[0]
        try:
            move_outlet(outlet, direction)
        except SettingsError as error:
            self._respond(render_outlets_page(load_settings(), error=str(error)))
            return
        self._redirect("/outlets")

    def _handle_save_highlight(self, form: dict) -> None:
        words = [form.get(f"highlight{i + 1}", [""])[0] for i in range(MAX_HIGHLIGHT_KEYWORDS)]
        try:
            save_highlight_keywords(words)
        except SettingsError as error:
            attempted = {**load_settings(), "highlight_keywords": [w for w in words if w.strip()]}
            self._respond(render_highlight_page(attempted, error=str(error)))
            return
        self._redirect("/highlight")

    def _handle_save_format(self, form: dict) -> None:
        template = form.get("line_template", [""])[0]
        try:
            save_article_line_template(template)
        except SettingsError as error:
            attempted = {**load_settings(), "article_line_template": template}
            self._respond(render_format_page(attempted, error=str(error)))
            return
        self._redirect("/format")

    def _handle_save_schedule(self, form: dict) -> None:
        times = [form.get(f"time{i + 1}", [""])[0] for i in range(MAX_SCHEDULE_TIMES)]
        try:
            save_schedule_times(times)
        except SettingsError as error:
            attempted = {**load_settings(), "schedule_times": [t for t in times if t.strip()]}
            self._respond(render_schedule_page(attempted, error=str(error)))
            return
        self._redirect("/schedule")

    def _handle_add_schedule_slot(self, form: dict) -> None:
        """"+ 시간대 추가" 버튼 — 저장하지 않고, 지금까지 입력하던 값을 위치 그대로 유지한 채
        입력칸을 하나 더 보여준다 (같은 폼의 formaction만 다르게 지정해 자바스크립트 없이 구현).
        중간에 빈 칸이 있어도 뒤 칸 값이 앞으로 당겨지지 않도록, 걸러내지 않고 그대로 넘긴다."""
        visible = 0
        while f"time{visible + 1}" in form:
            visible += 1
        times = [form.get(f"time{i + 1}", [""])[0] for i in range(visible)]
        self._respond(_render_schedule_preview(times, min(visible + 1, MAX_SCHEDULE_TIMES)))

    def _handle_move_article(self, form: dict) -> None:
        """index.html의 ↑/↓ 버튼이 fetch로 호출한다 (PRD.md 기능1 규칙 21).

        현재 화면(최신 회차)에 보이는 기사만 대상으로 한다 — 지난 기사는 재분류를
        하지 않아 "그룹 내 순서"라는 개념이 없으므로 버튼 자체를 보여주지 않는다.
        """
        url = form.get("url", [""])[0]
        direction = form.get("direction", [""])[0]
        if url and direction in ("up", "down"):
            run = load_latest_run()
            if run is not None:
                keywords = load_settings()["keywords"]
                overrides = load_group_overrides()
                new_articles, new_override = move_article(run["articles"], keywords, url, direction, overrides)
                changed = False
                if new_articles is not run["articles"] and update_run_articles(run, new_articles):
                    changed = True
                if new_override is not None:
                    set_group_override(*new_override)
                    changed = True
                if changed:
                    self._regenerate_screens()
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

    def _handle_rename_group(self, form: dict) -> None:
        """소제목 옆 ✏️ 버튼이 fetch로 호출한다 (PRD.md 기능2 규칙 8).

        name(원래 소제목 단어)은 그대로 두고 표시 이름만 바꾼다 — 분류 로직에는
        영향이 없다.
        """
        name = form.get("name", [""])[0]
        label = form.get("label", [""])[0].strip()
        if name and label:
            set_group_label(name, label)
            self._regenerate_screens()
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

    def _handle_hide_article(self, form: dict) -> None:
        """index.html/history.html(file://로 열림)의 🗑️ 버튼이 fetch로 호출한다.
        file:// 오리진은 CORS상 "null"로 취급되므로, 성공/실패를 JS가 읽을 수 있도록
        Access-Control-Allow-Origin을 열어준다 (로컬 단일 사용자 도구라 위험 없음)."""
        url = form.get("url", [""])[0]
        if url:
            hide_article(url)
            self._regenerate_screens()
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

    def _handle_unhide_article(self, form: dict) -> None:
        url = form.get("url", [""])[0]
        if url:
            unhide_article(url)
            self._regenerate_screens()
        self._redirect("/hidden")

    def _regenerate_screens(self) -> None:
        """숨김 상태가 바뀌면 정적 화면 3개를 즉시 다시 만든다 (새로고침해도 최신 상태가 보이도록).

        아직 저장된 회차가 하나도 없으면 generate_screen만 RuntimeError를 내므로,
        메인 화면 생성 실패와 무관하게 지난 기사·진입 화면은 항상 다시 만든다.
        """
        try:
            generate_screen()
        except RuntimeError:
            pass
        generate_history_page()
        generate_landing_page()

    def _redirect(self, path: str) -> None:
        # Post/Redirect/Get 패턴: 새로고침해도 저장이 중복 제출되지 않도록 리다이렉트한다.
        # 메뉴로 보내지 않고 자기 페이지로 되돌려, 이어서 같은 항목을 계속 손보기 편하게 한다.
        self.send_response(303)
        self.send_header("Location", path)
        self.end_headers()

    def _respond(self, html_text: str, status: int = 200) -> None:
        body = html_text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _respond_static_html(self, path) -> None:
        """index.html/history.html/home.html을 같은 127.0.0.1 출처로 그대로 서빙한다.

        파일이 아직 없으면(예: 오늘 첫 스크랩 전) 404 대신 안내 문구를 보여준다 —
        설정 화면에서 "메인 화면으로"를 눌렀는데 그냥 죽은 링크처럼 보이지 않도록.
        """
        if not path.exists():
            self._respond('<p style="font-family:sans-serif;padding:24px;">아직 생성된 화면이 없습니다.</p>', status=404)
            return
        self._respond(path.read_text(encoding="utf-8"))

    def _respond_static_binary(self, path, content_type: str) -> None:
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass  # 로컬 단일 사용자 도구라 매 요청을 콘솔에 찍지 않는다.


def run_settings_server(port: int = SETTINGS_SERVER_PORT) -> None:
    """설정 저장용 최소 로컬 서버를 실행한다 (블로킹). 127.0.0.1에서만 연다."""
    HTTPServer(("127.0.0.1", port), _SettingsHandler).serve_forever()
