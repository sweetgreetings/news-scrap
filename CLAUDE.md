# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

The app is implemented and working. Entry point: `python3 main.py` (starts the scheduler loop, the local settings/curation server, and opens the browser). Tests: `python3 tests/test_integration.py`. No package manager beyond `requirements.txt` (`requests`, `python-dotenv`) — no linter or type checker is configured.

## What this app is

A single-user, local-only desktop-style web app for a press-monitoring worker at the Ministry of Economy and Finance (재정경제부). It periodically scrapes Naver News search results for configured keywords, groups the articles into auto-generated sub-headings, and shows the results in a browser at `localhost`. Full spec: [PRD.md](PRD.md); condensed version: [prd_lite.md](prd_lite.md).

## Architecture (PRD section 8 original plan superseded — see DESIGN.md §3)

The original PRD plan (FastAPI + SQLite + APScheduler) was replaced during design with a simpler file-based approach to lower implementation difficulty. This is what's actually built:

- **No web framework**: plain Python scripts regenerate static HTML files (`index.html`, `history.html`, `home.html`) that are opened in the browser. No FastAPI, no Django.
- **Storage**: local JSON files under `data/` (`articles/`, `settings.json`, `hidden_articles.json`, `group_overrides.json`, `group_labels.json`) — no SQLite.
- **Scheduling**: a lightweight polling loop (`app/scheduler.py`, no APScheduler), checking every 60s. Default run times are 09:00 / 10:30 / 13:30 / 16:30 KST (4x/day), but the count and times are user-editable from the settings screen (1–10 slots, no code change needed). Only the single most-recently-missed slot is caught up on next tick if the app was closed during a scheduled time; the loop pauses during OS sleep like any other process and resumes catch-up on wake.
- **One exception to "no server"**: `app/settings_server.py` is a minimal `http.server`-only local HTTP server on `127.0.0.1:8765` that handles settings saves and article curation (hide/reorder/rename), and also serves the three static HTML screens from the same origin (needed because browsers block navigation from `http://` pages to `file://` paths).
- **External API**: Naver News Search API — credentials read from `.env` (`NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET`), never hardcoded or committed.
- **Target OS**: Windows, single local user, no auth/login layer.
- No separate LLM/AI API is used for classification — sub-heading grouping, summaries, and keyword extraction are rule-based (word-frequency grouping over article **descriptions**, not titles — title wording varies too much by outlet to group well), explicitly to avoid API costs.

## Core business rules to preserve (PRD section 5)

These are product-defined constraints, not implementation details — get them wrong and the feature is wrong even if the code runs:

- **Collection**: OR/AND-match across 1–7 user-configurable keywords (default: "재정경제부", "재경부"; OR is default, AND requires ≥2 keywords), no result-count cap, only same-day (KST) articles, editable from a settings screen (no code change needed).
- **Dedup rule**: keep duplicate articles across outlets/editions, but collapse articles with an *identical* title down to one (keeps the first-seen, so apply after outlet-priority sort). Articles whose title contains a photo-article hint word (`PHOTO_HINT_WORDS` in `app/filters.py`: 포토/사진/화보/포토뉴스/PHOTO, case-insensitive) are excluded entirely, not just deduped — except titles containing `[속보]`, which are always kept regardless of other hint words.
- **Outlet ordering**: broadcasters (KBS, MBC) first, then a fixed list of major outlets (조선일보, 중앙일보, 동아일보, 한국경제, 매일경제, 서울경제, 한국일보, 머니투데이, 이데일리, 연합뉴스, 뉴시스, …), then everything else appended at the end (never dropped) — **unless** the user has picked an outlet whitelist in settings, in which case only the checked outlets are kept, in the user-chosen order (`app/settings.py` `save_outlet_selection`, `app/filters.py` `filter_by_outlet_whitelist`).
- **Output line format** (no publish date shown), customizable via a `{outlet}`/`{title}` template in settings (default shown below); the URL line and the absence of a publish date are not customizable:
  ```
  ㅇ (언론사) 기사제목
  URL
  ```
- **No full-text crawling** — only store the Naver API's `description` summary field. Highlight keyword matches within it in `#C6FF00` (highlight keywords are a separate settings field from search keywords, max 3).
- Empty result for a run → show "하나도 없어요", not an empty list.
- Failed scrape → retry up to 3x, 5 minutes apart.
- Header on screen/export: "언론 모니터링 [HH:MM] 기준" using the run's scheduled slot time.
- **Sub-heading classification**: regenerated fresh each run from article descriptions (not fixed categories), max 5 sub-headings, each article assigned to exactly one — except a user's manual drag-across-boundary reassignment (see curation below), which overrides auto-classification as long as that sub-heading still exists in later runs. Every group — including the first — is rendered with a `<소제목N>` label, which can be renamed by the user (renaming only changes the display label, not the underlying grouping key).
- Within a sub-heading, articles are still ordered by the outlet-priority rule above.
- **Curation** (main screen, latest run only): each article has 🗑️ hide/restore (hidden articles stay in storage, just excluded from screen/export/wordcloud; reversible from the settings screen's "숨긴 기사 관리") and ↑/↓ reorder (moves within a sub-heading; at a group boundary, moves the article into the adjacent sub-heading).
- **History**: the last 7 days of runs are browsable (`history.html`), grouped by date → time slot; it does not re-run sub-heading classification, so no per-run curation there.
- Main screen (`index.html`) auto-refreshes every 60s via `<meta http-equiv="refresh">` (no JS needed for this).
- Bottom-of-page summary block (once per run, across all results, in this order): `🤖 AI가 추출한 주요 키워드` (comma-separated list, no `#` tags) then `💬 AI가 읽은 소제목별 주요 요약` (per sub-heading, ≤3 sentences / ≤150 chars).
- Export: copy-to-clipboard or `.txt` download of the sub-heading-grouped list (curation buttons and icon glyphs are excluded from the copied/exported text).
- Data retention: delete stored articles after 7 days.
- Explicitly out of scope for this version: other news sources (Daum, Google News), user accounts/login, email notifications, per-outlet filter/search UI, remote/mobile access off the local network.

## Design direction

[Updated: 2026-07-24] Light card-based theme (switched from the original dark navy theme after readability feedback, esp. links). Palette (`app/config.py` `COLOR_*`): background `#F8FAFC`, card `#FFFFFF`, header/heading `#1E3A5F`, accent (links/buttons) `#2563EB`, body text `#1F2937`, muted text `#6B7280`, border/divider `#E5E7EB`, hover `#EFF6FF`, error `#DC2626`. Desktop-first layout, responsive enough to be viewable on mobile.

## Working rules

- 모든 설명과 주석은 한국어로 작성한다.
- 새 파일은 이 프로젝트 루트 폴더(`my_app`) 안에만 만든다.
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
