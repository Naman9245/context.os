# ContextOS

A local AI assistant for university students (any university, any course).
Students collect hundreds of PDFs - notes, slides, assignments, question
papers, lab manuals, notices - scattered across Downloads with names like
`Module3_final(2).pdf`, with deadlines buried inside them. ContextOS scans
those folders, organises every file into `Semester/Subject/Type/`, pulls out
deadlines, tracks the student's week, and runs a chat assistant that can
open things on the laptop (Chrome search, YouTube/Spotify, files).

It is a **local desktop agent**: the FastAPI backend runs on the student's
own machine, which is what lets it move files and open the browser.

The assistant is called **Khushi** (she/her). Use that name in the chat UI,
greetings and notifications. Simple commands ("open Spotify") must work
without the LLM; the free-tier quota is saved for real understanding work.

`AGENTS.md` is a symlink to this file. Edit this one.

Full plan: `~/.claude/plans/lets-make-the-context-os-quirky-hopcroft.md`.

## Where things stand

| Phase | State |
|---|---|
| 00 Scaffold | done - FastAPI + SQLite tables + `contextos serve`, React shell with page placeholders |
| 01 LLM layer | done - Gemini + Groq over HTTP, JSON mode with one repair retry, rate limiter, disk cache, quota-aware fallback model |
| 02 File organiser | done - scan, extract (PyMuPDF / OCR / docx / pptx), rules-then-LLM classify, dry-run plan, move + undo, folder watcher; Organize, Files, Settings pages |
| 03 Assignments & reminders | done - every assignment gets a task; Khushi asks for missing deadlines and confirms found ones; to-do steps (LLM or rules from the sheet's questions); mark done; desktop reminders N days before (default 5 and 3); Khushi's briefing |
| 04 Weekly progress (study timer, chart, AI summary) | not started |
| 05 Khushi chat + local actions | done - rules-first intents (open apps/sites, play, search, what's due, add/finish tasks, find/open files, organise), LLM fallback picks one allowlisted action or answers study questions; chat history; Chat page + floating panel on every page |
| 05b Voice | done - Khushi reads replies (and their task/file cards) aloud via the browser's speechSynthesis; mic button uses Chrome's SpeechRecognition (en-IN default); voice, speed, language in Settings, stored per browser |
| 06 Post-v1: RAG over notes, syllabus mind map, Spotify API, packaging | not started |

## Commands

```bash
# backend (from backend/)
python3 -m venv .venv && .venv/bin/pip install -e ".[dev,llm,ingest]"
.venv/bin/contextos serve --reload          # API on :8000
.venv/bin/python -m pytest -q && .venv/bin/ruff check src tests
.venv/bin/python scripts/make_demo_files.py /tmp/demo/Downloads   # messy files to try it on

# frontend (from frontend/)
npm install
npm run dev                                  # :5173, proxies /api to :8000
npm run build                                # dist/ is then served by `contextos serve`
npm test                                     # vitest: pure helpers like lib/voice.ts

# browser extension (from the repo root)
node --test browser-extension/*.test.mjs     # tab logic; Load unpacked to try it in Chrome
```

## Rules

- **Never delete a user's file.** The organiser only moves, and every move
  is written to `MoveLog` so a batch can be undone.
- **Nothing moves without approval.** Scans produce a dry-run plan; the user
  approves it in the Organize page.
- **Extracted deadlines are suggestions** (`TaskStatus.suggested`) until the
  user accepts them.
- **Privacy:** only `LLM_SNIPPET_CHARS` of a document goes to the LLM, never
  the whole file. `LLM_PROVIDER=none` must keep every feature working on
  heuristics alone - tests run in that mode with a fake provider.
- **Local actions are allowlisted** (open URL, open a file inside the
  library, launch Spotify). No arbitrary shell commands from the chat agent.
- Heavy dependencies live in pyproject extras per phase (`llm`, `ingest`,
  `reminders`); import them lazily inside the module that needs them.
- This machine has no NVIDIA GPU - keep everything CPU-friendly.

## How the organiser decides (Phase 02)

- **Rules first** (`ingest/classify.py`): keywords in the file name (weight 3)
  and first 3000 chars (weight 1) pick the type; subject names, codes and
  aliases pick the subject. Short aliases (`OS`, `CN`) only count in body text
  when written in caps. Below `LLM_THRESHOLD` (0.6) the LLM is asked.
- A file with no readable text *and* a junk name (`scan0003.pdf`) never goes
  to the LLM - there is nothing to send. A filename-only LLM guess is capped
  at 0.4 confidence so the UI says "check this".
- Subjects the LLM invents are created on the fly; a subject without a
  semester learns it from the first file that states one, and files already
  planned for it are re-planned (`pipeline._learn_semester`).
- Deadlines need a deadline word on the line ("due", "submit", "last date")
  and must be in the future. `Task.due_at` is local wall-clock time
  (`NaiveDatetime`); every other timestamp is UTC.

## How assignments work (Phase 03)

- Every `DocType.assignment` document gets exactly one task
  (`tasks/service.ensure_assignment_task`, also backfilled on startup). A
  found deadline -> `suggested` with a date ("is this right?"); none found ->
  `suggested` with no date ("when is it due?"). Answering either makes it
  `todo`. "Not a deadline" -> `dismissed`, so rescans never re-suggest it.
- Reminders only go to `todo` tasks, once per offset in `REMINDER_DAYS`
  (tracked in `Task.reminded_days`, reset when the date changes). A laptop
  that was off sends one catch-up, not every missed reminder.
- Khushi's briefing (`agent/khushi.py`) is pure rules - it loads on every
  page, so it must never spend LLM quota. To-do lists use the LLM only when
  asked, and fall back to one step per question found in the sheet.
- Any exception from the LLM (not just `LLMError`) must fall back to rules.

## How Khushi's chat works (Phase 05)

- `agent/intents.py` rules run first: no quota, instant. Patterns keep the
  user's casing (titles like "DBMS mini project") and must all be `re.I` -
  a test enforces it. Add new everyday commands here, not to the LLM prompt.
- Anything unmatched, or a vague query ("search me *this*"), goes to the LLM
  with the last 6 messages and open tasks. It returns `ChatPlan` (reply +
  at most one action) and `agent/tools.py` runs it. Khushi's text then
  describes what the tool *actually* did, not what the model said.
- On Linux every launch goes through `systemd-run --user` (the desktop
  session), not a child process. A shell started inside the Claude app has
  `NoNewPrivs: 1`; children inherit it and **snap apps (VS Code, Spotify) die
  with "snap-confine ... cannot continue"**. The session also gives apps a
  clean environment (no leaked `CHROME_DESKTOP`). A launch that fails within
  `SETTLE_SECONDS` raises `LaunchFailed`, and Khushi says so - never "Opened".
- On Windows, apps are found by their `.exe` names (never a Linux program's):
  on PATH, else in the App Paths registry (`apps._app_path`), which is where
  Chrome and Firefox register - they install outside PATH. Store apps (Windows
  Terminal) start through their alias on PATH, never from the locked
  WindowsApps folder.
- Only `agent/actions.py` touches the OS: `launch_app` (allowlist in
  `agent/apps.py`, web fallback when not installed), `open_url` (http/https/
  spotify only), `open_path` (library + watched folders only). Tests patch
  `_spawn`/`_open_with_system`; never launch real apps in tests or demos.
- "Play" opens YouTube results / Spotify search - true autoplay needs the
  Spotify Web API (Premium) or YouTube Data API key (post-v1).

## Khushi for Chrome (browser-extension/)

- Opening a link through the OS always makes a new Chrome tab, and Chrome lets
  no outside program pick a tab. The extension keeps one Khushi tab per site
  (`siteOf`/`site_of`, kept identical via `site-cases.json`) and reuses it
  while it is still on that site; tabs the user opened are never touched.
- It holds a WebSocket to `/api/browser/ws`. WebSockets skip the HTTP
  middleware, so that route checks Host and requires Origin
  `chrome-extension://<EXTENSION_ID>`; the ID is fixed by the public `key` in
  manifest.json (no private key is kept - unpacked extensions don't need one).
- `actions.open_url` tries `bridge.open()` first and falls back to the normal
  launcher on no extension / no answer within `OPEN_TIMEOUT` / a refusal.
- MV3 workers sleep: server pings every 20 s keep it awake; an alarm
  reconnects every minute.
- "open it" / "play the first one": `bridge.open_first(site)` asks the extension
  to read the first result on Khushi's results tab (`firstResult`, runs in the
  page; waits for the page to load) and open it. Without the extension Khushi
  says she can't see the page - she must never pretend.

## Context and steps (chat)

- Every `Reply.context` records what it produced (search/play {query, where},
  site, files, tasks, page). `last_context()` reads it back, so "open it",
  "mark it done" and corrections work - for rules and the LLM alike.
- `split_steps()` turns "open youtube and then search X and then open the first
  video" into steps, run in order with context passed along; a failed step
  stops the rest and the reply says what was skipped. After "open YouTube", a
  plain "search X" goes to YouTube (`_inherited`).
- `_CLAIMS_ACTION`: if the LLM's reply says "Opening/Playing..." without
  choosing an action, Khushi replies that she can't do it instead.

## Voice (Phase 05b)

- All in the browser (`frontend/src/lib/voice.ts`), no backend or downloads.
  Speaking: `speechSynthesis`, chunked into ~180-char sentences (Chrome cuts
  long utterances). Listening: `webkitSpeechRecognition` - works in Google
  Chrome only and sends audio to Google; it is said so in Settings.
- The message box is a growing textarea (Enter sends, Shift+Enter = new
  line) that follows the newest words while dictating - a one-line input hid
  everything after the first sentence.
- The mic stays on until the user taps stop: `listen()` runs continuous
  recognition and, when Chrome ends a session by itself (silence, ~60 s),
  keeps the words heard (even unsettled ones) and restarts after
  `RESTART_DELAY_MS`. Speech only ever fills the message box - it is never
  sent automatically (the user asked for this explicitly).
- Voice prefs live in localStorage (per-browser convenience, safe to lose).
- A running page keeps its old JS after a rebuild. `/api/health` reports a
  `build` id (hash of dist/index.html) and `UpdateBanner` offers a reload when
  it changes; index.html is served `no-cache`. When the user reports a bug you
  already fixed, check the server log for which `/assets/index-*.js` they ran.
- Khushi is a she: `pickVoice` prefers en-IN, then female Google voices, and
  avoids known male voices. The user can pick any voice in Settings.
- The embedded browser pane has no voices and blocks the mic: verify voice
  logic by stubbing `speechSynthesis.speak`, not by listening.
- Local, offline voice (Piper TTS / faster-whisper) is a possible upgrade.

- Music requests go to Spotify when it is installed, videos (lecture,
  tutorial, trailer...) to YouTube. Moods become searches ("something nice" ->
  "chill vibes"). Service names are matched with typo tolerance
  (`intents.fuzzy_service`: "spotigfy" -> spotify). Corrections ("not on
  youtube, I want spotify") repeat the last play/search via `Reply.redo` - no LLM.

## Gemini free tier, as observed 2026-10-15

- Use a **chain** of models (`GEMINI_FALLBACK_MODEL=a,b,c`): free quotas are per
  model and Google's models take turns returning 503. A busy model is skipped at
  once (only the last in the chain is retried); `LLMUnavailable.kind` tells the
  user "busy" vs "quota" honestly.

- `gemini-3.8-flash`: **20 requests/day** on the free tier. Its 429 carries
  `RetryInfo.retryDelay` of hours, which the provider turns into
  `ModelUnavailable` -> straight to the fallback, main skipped until reset.
- `gemini-2.5-flash` is 404 "no longer available to new users".
- `thinkingLevel: minimal` halves latency (~19s -> ~9s) on 3.5-flash.
- `pkill -f "contextos serve ..."` kills the calling shell too (its own
  command line matches) - use `pkill -f "[c]ontextos serve"`.
