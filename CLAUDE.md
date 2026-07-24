# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

No application code exists yet — this repo currently contains only planning documents (`PRD.md`, `prd_lite.md`) and a `.env` with Naver API credentials (`NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET`). There is no `package.json`, no Python project files, and no build/lint/test tooling set up. Once the project is scaffolded, this file should be updated with the actual commands (`uvicorn` entry point, test runner, etc.).

## What this app is

A single-user, local-only desktop-style web app for a press-monitoring worker at the Ministry of Economy and Finance (재정경제부). It periodically scrapes Naver News search results for configured keywords, groups the articles into auto-generated sub-headings, and shows the results in a browser at `localhost`. Full spec: [PRD.md](PRD.md); condensed version: [prd_lite.md](prd_lite.md).

## Planned architecture (from PRD section 8)

- **Backend**: Python + FastAPI, serving both the API and the browser UI at `localhost`.
- **Storage**: SQLite for article persistence.
- **Scheduling**: APScheduler, running 3x/day (09:00 / 13:30 / 16:30 KST). Must catch up on missed runs if the app was closed during a scheduled time (run the missed slot immediately on next startup), and survive OS sleep.
- **External API**: Naver News Search API — credentials read from `.env` (`NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET`), never hardcoded or committed.
- **Target OS**: Windows, single local user, no auth/login layer.
- No separate LLM/AI API is used for classification — sub-heading grouping, summaries, and keyword extraction are rule-based (word-frequency grouping over article titles), explicitly to avoid API costs.

## Core business rules to preserve (PRD section 5)

These are product-defined constraints, not implementation details — get them wrong and the feature is wrong even if the code runs:

- **Collection**: OR-match across 3–4 user-configurable keywords (default: "재정경제부", "재경부"), no result-count cap, editable from a settings screen (no code change needed).
- **Dedup rule**: keep duplicate articles across outlets/editions, but collapse articles with an *identical* title down to one. Articles whose title contains a photo-article hint word (`PHOTO_HINT_WORDS` in `app/filters.py`: 포토/사진/화보/포토뉴스/PHOTO, case-insensitive) are excluded entirely, not just deduped — except titles containing `[속보]`, which are always kept regardless of other hint words.
- **Outlet ordering**: broadcasters (KBS, MBC) first, then a fixed list of major outlets (조선일보, 중앙일보, 동아일보, 한국경제, 매일경제, 서울경제, 한국일보, 머니투데이, 이데일리, 연합뉴스, 뉴시스, …), then everything else appended at the end (never dropped).
- **Output line format** (no publish date shown):
  ```
  ㅇ (언론사) 기사제목
  URL
  ```
- **No full-text crawling** — only store the Naver API's `description` summary field. Highlight keyword matches within it in `#C6FF00`.
- Empty result for a run → show "하나도 없어요", not an empty list.
- Failed scrape → retry up to 3x, 5 minutes apart.
- Header on screen/export: "언론 모니터링 [HH:MM] 기준" using the run's scheduled slot time.
- **Sub-heading classification**: regenerated fresh each run (not fixed categories), max 5 sub-headings, each article assigned to exactly one. Every group — including the first — is rendered with a `<소제목N>` label.
- Within a sub-heading, articles are still ordered by the outlet-priority rule above.
- Screen shows only the latest run's results — no history/date browsing.
- Bottom-of-page summary block (once per run, across all results, in this order): `🤖 AI가 추출한 주요 키워드` (comma-separated list, no `#` tags) then `💬 AI가 읽은 소제목별 주요 요약` (per sub-heading, ≤3 sentences / ≤150 chars).
- Export: copy-to-clipboard or `.txt` download of the sub-heading-grouped list.
- Data retention: delete stored articles after 7 days.
- Explicitly out of scope for this version: other news sources (Daum, Google News), user accounts/login, email notifications, per-outlet filter/search UI, remote/mobile access off the local network.

## Design direction

[Updated: 2026-07-24] Light card-based theme (switched from the original dark navy theme after readability feedback, esp. links). Palette (`app/config.py` `COLOR_*`): background `#F8FAFC`, card `#FFFFFF`, header/heading `#1E3A5F`, accent (links/buttons) `#2563EB`, body text `#1F2937`, muted text `#6B7280`, border/divider `#E5E7EB`, hover `#EFF6FF`, error `#DC2626`. Desktop-first layout, responsive enough to be viewable on mobile.

## Working rules

- 모든 설명과 주석은 한국어로 작성한다.
- 새 파일은 `my-app` 폴더 안에만 만든다.
- 코드를 바꾸면 반드시 무엇을 왜 바꿨는지 한 줄로 알려준다.
- `.env` 등 비밀 정보 파일은 `.gitignore`에 등록해 두고, 절대 커밋하지 않는다.
- 파일을 지워야 할 때는 바로 삭제하지 말고, `trash-can` 폴더를 만들어 그 안으로 옮겨만 둔다. 작업이 끝난 뒤 사용자가 직접 확인하고 삭제한다.
- 이미 설치된 서브에이전트(bkit의 gap-detector 등)를 필요할 때마다 적극 활용한다.

## 작업 절차(검증 루프)

아래 순서를 매번 반복한다:

1. 변경한다.
2. 결과를 직접 확인한다 (브라우저로 열기/실행).
3. 스스로 코드 리뷰한다.
4. 문제가 있으면 고치고 다시 1)로 돌아간다.
5. 통과하면 무엇을 왜 바꿨는지 한 줄로 요약한다.
