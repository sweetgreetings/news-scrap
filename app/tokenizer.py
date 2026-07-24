# Design Ref: PRD.md 기능2 규칙 2 — 규칙 기반(LLM 없음) 제목 토큰화. 소제목 분류와 키워드 추출이 공유한다.
import re

# 소제목·키워드로 삼기엔 의미가 옅은 일반 단어들. 제목에 흔하지만 주제를 가르지 못한다.
# [수정: 2026-07-24] 분류 기준을 제목→요약(description)으로 바꾸면서, 요약문에 흔한
# 보도체 상투어(밝혔다/전했다 등)도 추가했다 — 실제 운영해보며 계속 다듬을 예정.
STOPWORDS = {
    "관련", "대한", "위해", "통해", "밝혀", "오늘", "종합", "속보", "단독",
    "이번", "지난", "올해", "내년", "우리", "그룹", "회장", "장관", "정부",
    "밝혔다", "전했다", "말했다", "설명했다", "강조했다", "덧붙였다", "이날", "당시", "한편",
}

# 제거할 대표적인 한국어 조사 (긴 것부터 떼어내야 정확하다).
_JOSA = ("으로써", "에서의", "으로", "에서", "에게", "까지", "부터", "라며", "이라",
         "은", "는", "이", "가", "을", "를", "의", "에", "와", "과", "도", "로", "만")

# 단어 경계로 쓸 문자: 공백과 각종 문장부호·괄호.
_SPLIT_PATTERN = re.compile(r"[\s\[\]()<>·,…\"'“”‘’!?.·:;/\\|~\-—]+")

# [추가: 2026-07-24] "24일"·"3월"·"오후 2시"처럼 숫자+날짜/시간 단위로만 된 단어는 거의 항상
# 그날의 날짜·시각 표현이라 소제목감이 못 된다 (예: 요약문 대부분에 "24일"이 들어있어 그
# 자체로 소제목이 되어버리는 문제). 며칠이 지나도 계속 나올 패턴이라 불용어 목록에 하나씩
# 추가하는 대신 패턴으로 걸러낸다.
_DATE_TIME_PATTERN = re.compile(r"^\d+(일|월|년|시|분|초|주)$")


def _strip_josa(word: str) -> str:
    for josa in _JOSA:
        if len(word) > len(josa) + 1 and word.endswith(josa):
            return word[: -len(josa)]
    return word


def tokenize(title: str, stopwords: set) -> set:
    """제목을 의미 단어 집합으로 바꾼다 (2글자 이상, 조사 제거, 불용어·검색 키워드·날짜 제외)."""
    tokens = set()
    for raw in _SPLIT_PATTERN.split(title):
        word = _strip_josa(raw.strip()).lower()
        if len(word) >= 2 and word not in stopwords and not _DATE_TIME_PATTERN.match(word):
            tokens.add(word)
    return tokens
