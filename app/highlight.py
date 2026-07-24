# Design Ref: PRD.md 기능1 규칙 6 — 저장된 요약 중 일치하는 키워드를 형광 연두색(#C6FF00)으로 하이라이트
import html
import re

from app.config import HIGHLIGHT_COLOR, HIGHLIGHT_TEXT_COLOR


def highlight_keywords(summary: str, keywords: list[str]) -> str:
    """
    요약(summary) 텍스트에서 키워드와 일치하는 부분을 #C6FF00 배경의 <span>으로 감싼
    HTML 조각을 돌려준다.

    - 요약 원문은 화면에 그대로 노출되므로 HTML 특수문자(<, >, & 등)를 이스케이프한다.
      키워드로 감싸는 <span> 태그만 실제 태그로 남고, 나머지 텍스트는 안전하게 처리된다.
    - 키워드가 여러 개면 모두 하이라이트한다. 긴 키워드를 우선 적용해
      짧은 키워드가 긴 키워드 일부만 잘라 강조하는 일을 막는다 (예: "재정" vs "재정경제부").
    - 영문 키워드를 위해 대소문자를 구분하지 않고 일치시키되, 강조 시에는 원문 표기를 그대로 유지한다.
    """
    # 빈 문자열/공백 키워드는 제외한다 (빈 패턴은 모든 위치에 매칭되어 오작동한다).
    valid_keywords = [k for k in keywords if k.strip()]

    if not summary:
        return ""
    if not valid_keywords:
        return html.escape(summary)

    # 긴 키워드부터 매칭하도록 정렬한 뒤 정규식 대안(alternation)으로 합친다.
    sorted_keywords = sorted(set(valid_keywords), key=len, reverse=True)
    pattern = re.compile("|".join(re.escape(k) for k in sorted_keywords), re.IGNORECASE)

    # 매칭 부분/비매칭 부분을 나눠 각각 이스케이프하고, 매칭 부분만 span으로 감싼다.
    result = []
    last_end = 0
    for match in pattern.finditer(summary):
        result.append(html.escape(summary[last_end:match.start()]))
        matched_text = html.escape(match.group())
        result.append(
            f'<span style="background-color:{HIGHLIGHT_COLOR};color:{HIGHLIGHT_TEXT_COLOR}">{matched_text}</span>'
        )
        last_end = match.end()
    result.append(html.escape(summary[last_end:]))
    return "".join(result)
