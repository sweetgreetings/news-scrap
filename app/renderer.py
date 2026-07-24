# Design Ref: DESIGN.md §1 화면 구성 — 최신 회차를 밝은 카드형 정적 HTML 화면으로 렌더링
import html
import json
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import quote

from app.classifier import classify_articles
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
    DEFAULT_KEYWORDS,
    FONT_STACK,
    OUTPUT_HTML_PATH,
    REFRESH_INTERVAL_SEC,
    SETTINGS_SERVER_PORT,
)
from app.atomic_write import atomic_write_text
from app.curation import display_group_name, filter_hidden, load_group_labels, load_group_overrides
from app.highlight import highlight_keywords
from app.settings import load_settings
from app.storage import load_latest_run
from app.summarizer import extract_keywords, summarize_groups

_PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<meta http-equiv="refresh" content="{refresh_interval}" />
<title>언론 모니터링</title>
<style>
  body {{ margin: 0; background: {bg}; color: {text}; font-family: {font_stack}; }}
  .container {{
    max-width: 800px; margin: 24px auto; padding: 24px; background: {card};
    border: 1px solid {border}; border-radius: 8px;
  }}
  header h1 {{ font-size: 1.4rem; margin-bottom: 4px; color: {header}; }}
  .refresh-indicator {{
    color: {muted}; font-size: 0.85rem; margin: 0 0 12px;
    user-select: none; -webkit-user-select: none;
  }}
  @keyframes spin {{ from {{ transform: rotate(0deg); }} to {{ transform: rotate(360deg); }} }}
  .refresh-indicator .spin-icon {{ display: inline-block; animation: spin 1.2s ease-out 1; }}
  .actions {{ display: flex; gap: 8px; }}
  button, a.btn {{
    background: {accent}; color: #ffffff; border: none; border-radius: 4px;
    padding: 6px 14px; font-size: 0.9rem; cursor: pointer; text-decoration: none;
    display: inline-block; user-select: none; -webkit-user-select: none;
  }}
  button:hover, a.btn:hover {{ background: {header}; }}
  .subheading {{ margin-top: 28px; }}
  .subheading h2 {{ font-size: 1.1rem; color: {header}; border-bottom: 1px solid {border}; padding-bottom: 6px; }}
  .rename-btn {{
    background: transparent; border: none; color: {muted}; font-size: 0.9rem; cursor: pointer;
    vertical-align: middle; user-select: none; -webkit-user-select: none;
  }}
  .article {{ margin: 10px 0; line-height: 1.5; }}
  .article summary {{ cursor: pointer; }}
  .article summary::marker {{ color: {muted}; }}
  .article-summary {{ margin: 6px 0 4px 20px; color: {text}; font-size: 0.95rem; }}
  .article-footer {{ display: flex; align-items: center; gap: 8px; }}
  .article .url {{ flex: 1; color: {muted}; font-size: 0.9rem; word-break: break-all; text-decoration: underline; }}
  .move-btn, .hide-btn {{
    flex-shrink: 0; background: transparent; border: none; color: {muted}; font-size: 1rem;
    cursor: pointer; padding: 2px 6px; user-select: none; -webkit-user-select: none;
  }}
  .move-btn:disabled {{ color: {border}; cursor: not-allowed; }}
  .hide-btn:hover {{ color: {error}; }}
  .empty {{ text-align: center; margin-top: 80px; font-size: 1.3rem; color: {muted}; }}
  .bottom {{ margin-top: 40px; border-top: 1px solid {border}; padding-top: 16px; }}
  .bottom h3 {{ font-size: 1rem; color: {header}; }}
</style>
</head>
<body>
<div class="container">
  <header>
    <h1>언론 모니터링 {run_slot} 기준</h1>
    <p class="refresh-indicator"><span class="spin-icon">🔄</span> {last_updated} 업데이트</p>
    <div class="actions">
      <button onclick="copyPlainText()">복사</button>
      <a class="btn" href="data:text/plain;charset=utf-8,{export_href}" download="{export_filename}">내보내기</a>
      <a class="btn" href="http://127.0.0.1:{settings_port}/">설정</a>
      <a class="btn" href="history.html">📅 지난 기사 더보기</a>
    </div>
  </header>
  {body}
  <p><a class="btn" href="home.html">🏠 메인으로 가기</a></p>
</div>
<script>
const PLAIN_TEXT = {plain_text_json};
function copyPlainText() {{
  navigator.clipboard.writeText(PLAIN_TEXT)
    .then(() => alert("클립보드에 복사했습니다."))
    .catch(() => alert("복사에 실패했습니다."));
}}
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
function moveArticle(btn) {{
  var url = btn.dataset.url;
  var direction = btn.dataset.direction;
  fetch("http://127.0.0.1:{settings_port}/move-article", {{
    method: "POST", keepalive: true,
    headers: {{"Content-Type": "application/x-www-form-urlencoded"}},
    body: new URLSearchParams({{url: url, direction: direction}})
  }}).then(function(res) {{
    if (res.ok) {{ location.reload(); }}
    else {{ alert("순서 변경에 실패했습니다. 다시 시도해주세요."); }}
  }}).catch(function() {{
    alert("순서 변경에 실패했습니다 — 앱이 실행 중인지 확인해주세요.");
  }});
}}
function renameGroup(btn) {{
  var name = btn.dataset.name;
  var current = btn.dataset.current;
  var newLabel = prompt("소제목 이름을 입력하세요", current);
  if (newLabel === null) return;
  newLabel = newLabel.trim();
  if (!newLabel) {{ alert("소제목 이름은 비워둘 수 없습니다."); return; }}
  fetch("http://127.0.0.1:{settings_port}/rename-group", {{
    method: "POST", keepalive: true,
    headers: {{"Content-Type": "application/x-www-form-urlencoded"}},
    body: new URLSearchParams({{name: name, label: newLabel}})
  }}).then(function(res) {{
    if (res.ok) {{ location.reload(); }}
    else {{ alert("이름 변경에 실패했습니다. 다시 시도해주세요."); }}
  }}).catch(function() {{
    alert("이름 변경에 실패했습니다 — 앱이 실행 중인지 확인해주세요.");
  }});
}}
</script>
</body>
</html>
"""


def apply_line_template(template: str, outlet: str, title: str) -> str:
    """{outlet}·{title} 자리표시자를 치환한다 (PRD.md 기능1 규칙 5).

    str.format이 아니라 단순 문자열 치환(.replace)을 쓴다 — outlet/title 값이나
    template 자체에 우연히 중괄호가 들어 있어도 format 필드로 잘못 해석되거나
    깨지지 않는다(DESIGN.md §3).
    """
    return template.replace("{outlet}", outlet).replace("{title}", title)


def render_article(
    article: dict,
    highlight_words: list,
    line_template: str = DEFAULT_ARTICLE_LINE_TEMPLATE,
    move: Optional[dict] = None,
) -> str:
    """기사 한 건을 렌더링한다.

    제목 줄은 <details>/<summary>로 감싸 클릭하면 저장된 요약이 펼쳐지고(PRD 규칙13,
    자바스크립트 없이 HTML 기본 기능만 사용), URL은 새 탭으로 여는 링크다(PRD 규칙14).
    펼쳐지는 요약에는 형광펜 단어 하이라이트를 적용한다(PRD 규칙6). highlight_words는
    검색 키워드와 무관한, 설정 화면에서 별도로 지정하는 값이다. line_template은 첫
    줄("ㅇ (언론사) 제목")의 형식을 정하며, 설정 화면에서 바꿀 수 있다(규칙5).

    move: {"disable_up": bool, "disable_down": bool} — 소제목 안에서 위/아래로 옮기는
    ↑/↓ 버튼을 보여준다(규칙21). None이면 버튼 자체를 안 보여준다 (지난 기사 화면처럼
    소제목 재분류가 없는 곳에서는 "그룹 내 순서"라는 개념이 없어 의미가 없다).
    """
    outlet = html.escape(article["outlet"])
    title = html.escape(article["title"])
    url = html.escape(article["url"])
    summary_html = highlight_keywords(article.get("summary", ""), highlight_words)
    # 템플릿 자체도 이스케이프해, 사용자가 입력한 특수문자가 HTML로 해석되지 않게 한다.
    line_html = apply_line_template(html.escape(line_template), outlet, title)
    move_html = ""
    if move is not None:
        up_disabled = " disabled" if move.get("disable_up") else ""
        down_disabled = " disabled" if move.get("disable_down") else ""
        move_html = (
            f'<button class="move-btn" type="button" data-url="{url}" data-direction="up" '
            f'onclick="moveArticle(this)"{up_disabled} title="위로 이동">↑</button>'
            f'<button class="move-btn" type="button" data-url="{url}" data-direction="down" '
            f'onclick="moveArticle(this)"{down_disabled} title="아래로 이동">↓</button>'
        )
    return (
        '<div class="article">'
        "<details>"
        f"<summary>{line_html}</summary>"
        f'<p class="article-summary">{summary_html}</p>'
        "</details>"
        '<div class="article-footer">'
        f'<a class="url" href="{url}" target="_blank" rel="noopener noreferrer">{url}</a>'
        f"{move_html}"
        f'<button class="hide-btn" type="button" data-url="{url}" onclick="hideArticle(this)" '
        'title="이 기사 숨기기 (되돌리기 가능)">🗑️</button>'
        "</div>"
        "</div>"
    )


def _render_groups(groups: list, highlight_words: list, line_template: str, labels: dict) -> str:
    """소제목별 화면을 렌더링한다.

    ↑/↓ 버튼은 각 소제목 안에서만이 아니라 소제목 경계도 넘나들 수 있어(규칙21),
    맨 처음 소제목의 첫 기사(↑)·맨 마지막 소제목의 마지막 기사(↓)일 때만 버튼을
    비활성화한다. 그 외 소제목 경계에서는 버튼이 계속 활성 상태이고, 클릭하면
    서버(move_article)가 "같은 소제목 내 순서 변경"과 "옆 소제목으로 이동"을 알아서
    구분해 처리한다 — 화면(버튼) 쪽은 이 둘을 구분할 필요가 없다.

    소제목 옆 ✏️ 버튼은 표시 이름만 바꾼다(기능2 규칙 8) — 분류 자체는 항상 원래
    소제목 단어(group["name"])를 기준으로 하므로, 버튼의 data-name에는 원래 단어를
    그대로 담아 서버가 어떤 단어의 이름표를 바꿀지 정확히 알 수 있게 한다.
    """
    sections = []
    last_group_index = len(groups) - 1
    for group_index, group in enumerate(groups):
        original_name = html.escape(group["name"])
        display_name = html.escape(display_group_name(group["name"], labels))
        last_index = len(group["articles"]) - 1
        articles_html = "\n".join(
            render_article(
                a,
                highlight_words,
                line_template,
                move={
                    "disable_up": i == 0 and group_index == 0,
                    "disable_down": i == last_index and group_index == last_group_index,
                },
            )
            for i, a in enumerate(group["articles"])
        )
        heading = (
            f'<h2>&lt;{display_name}&gt; '
            f'<button class="rename-btn" type="button" data-name="{original_name}" '
            f'data-current="{display_name}" onclick="renameGroup(this)" title="소제목 이름 바꾸기">✏️</button></h2>'
        )
        sections.append(f'<section class="subheading">{heading}{articles_html}</section>')
    return "\n".join(sections)


def _render_bottom(articles: list, groups: list, keywords: list, highlight_words: list, labels: dict) -> str:
    # keywords(검색어)는 소제목/키워드 추출에서 "뻔한 단어"를 걸러내는 용도로만 쓰고,
    # 실제로 형광펜을 칠하는 기준은 highlight_words(형광펜 단어, 별도 설정)다.
    keyword_tags = ", ".join(html.escape(k) for k in extract_keywords(articles, keywords))
    summary_lines = "\n".join(
        f'<p><strong>&lt;{html.escape(display_group_name(s["name"], labels))}&gt;</strong> '
        f'{highlight_keywords(s["summary"], highlight_words)}</p>'
        for s in summarize_groups(groups)
    )
    return (
        '<div class="bottom">'
        "<h3>🤖 AI가 추출한 주요 키워드</h3>"
        f"<p>{keyword_tags}</p>"
        "<h3>💬 AI가 읽은 소제목별 주요 요약</h3>"
        f"{summary_lines}"
        "</div>"
    )


def _build_plain_text(run_slot: str, groups: list, line_template: str, labels: dict) -> str:
    """복사/내보내기용 메모장 형식 텍스트를 만든다 (PRD.md 기능1 규칙 5·10·11).

    화면에 표시된 언론사·기사제목·URL 목록만 담는다 — 하단의 🤖 키워드·💬 요약
    블록은 규칙10이 "소제목별 스크랩 목록(언론사·기사제목·URL)"만 명시하므로 제외한다.
    첫 줄 형식은 화면과 동일하게 line_template을 따른다. 소제목 이름은 사용자가 붙인
    이름표(labels)가 있으면 그걸로 표시한다 — 화면과 항상 같은 이름을 보여줘야 한다.
    """
    lines = [f"언론 모니터링 {run_slot} 기준", ""]
    if not groups:
        lines.append("하나도 없어요")
    else:
        for group in groups:
            lines.append(f"<{display_group_name(group['name'], labels)}>")
            for article in group["articles"]:
                lines.append(apply_line_template(line_template, article["outlet"], article["title"]))
                lines.append(article["url"])
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_page(
    run_slot: str,
    articles: list,
    keywords: Optional[list] = None,
    highlight_words: Optional[list] = None,
    line_template: Optional[str] = None,
) -> str:
    """한 회차 데이터를 완성된 HTML 문서 문자열로 렌더링한다.

    수집된 기사가 없으면 (PRD.md 기능1 규칙 7) 본문을 "하나도 없어요"로 대체한다.
    헤더의 회차 시각(run_slot)은 이 경우에도 그대로 표시한다.

    keywords: 검색 키워드 — 소제목 분류·주요 키워드 추출에서 "뻔한 단어"를 제외하는 데 쓴다.
    highlight_words: 형광펜 단어 — 요약에 하이라이트를 칠하는 기준이며 keywords와 무관하다(규칙6).
    line_template: 기사 첫 줄("ㅇ (언론사) 제목") 형식. keywords/highlight_words와도 무관하다(규칙5).
    """
    keywords = keywords if keywords is not None else DEFAULT_KEYWORDS
    highlight_words = highlight_words if highlight_words is not None else DEFAULT_HIGHLIGHT_KEYWORDS
    line_template = line_template if line_template is not None else DEFAULT_ARTICLE_LINE_TEMPLATE
    labels = load_group_labels()
    if not articles:
        body = '<div class="empty">하나도 없어요</div>'
        groups = []
    else:
        groups = classify_articles(articles, keywords, forced_groups=load_group_overrides())
        body = _render_groups(groups, highlight_words, line_template, labels) + _render_bottom(
            articles, groups, keywords, highlight_words, labels
        )

    plain_text = _build_plain_text(run_slot, groups, line_template, labels)
    export_filename = f"언론모니터링_{run_slot.replace(':', '-')}.txt"

    return _PAGE_TEMPLATE.format(
        run_slot=html.escape(run_slot),
        body=body,
        # json.dumps로 JS 문자열 리터럴로 안전하게 이스케이프하고, "</script"가 섞여
        # 있어도 스크립트 태그가 조기 종료되지 않도록 "</"를 "<\/"로 한 번 더 바꾼다.
        plain_text_json=json.dumps(plain_text, ensure_ascii=False).replace("</", "<\\/"),
        export_href=quote(plain_text),
        export_filename=html.escape(export_filename),
        settings_port=SETTINGS_SERVER_PORT,
        refresh_interval=REFRESH_INTERVAL_SEC,
        last_updated=datetime.now().strftime("%H:%M"),
        font_stack=FONT_STACK,
        bg=COLOR_BG,
        card=COLOR_CARD,
        header=COLOR_HEADER,
        accent=COLOR_ACCENT,
        text=COLOR_TEXT,
        muted=COLOR_TEXT_MUTED,
        border=COLOR_BORDER,
        error=COLOR_ERROR,
    )


def generate_screen(
    keywords: Optional[list] = None,
    highlight_words: Optional[list] = None,
    line_template: Optional[str] = None,
) -> Path:
    """저장된 최신 회차를 읽어 index.html로 렌더링한다 (PRD.md 기능2 규칙 6: 최신 회차만 표시).

    keywords/highlight_words/line_template을 생략하면 설정 화면에 저장된 값을 각각 쓴다
    (규칙2 검색 키워드, 규칙6 형광펜 단어, 규칙5 출력 줄 형식 — 서로 별개 설정).
    """
    run = load_latest_run()
    if run is None:
        raise RuntimeError("아직 저장된 회차가 없습니다 — 먼저 스크랩을 실행해야 합니다.")
    if keywords is None or highlight_words is None or line_template is None:
        settings = load_settings()
        keywords = keywords if keywords is not None else settings["keywords"]
        highlight_words = highlight_words if highlight_words is not None else settings["highlight_keywords"]
        line_template = line_template if line_template is not None else settings["article_line_template"]
    articles = filter_hidden(run["articles"])
    html_text = render_page(run["run_slot"], articles, keywords, highlight_words, line_template)
    atomic_write_text(OUTPUT_HTML_PATH, html_text)
    return OUTPUT_HTML_PATH
