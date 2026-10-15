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
| 05 Chat assistant + local actions | not started |
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

## Gemini free tier, as observed 2026-10-15

- `gemini-3.8-flash`: **20 requests/day** on the free tier. Its 429 carries
  `RetryInfo.retryDelay` of hours, which the provider turns into
  `ModelUnavailable` -> straight to the fallback, main skipped until reset.
- `gemini-2.5-flash` is 404 "no longer available to new users".
- `thinkingLevel: minimal` halves latency (~19s -> ~9s) on 3.5-flash.
- `pkill -f "contextos serve ..."` kills the calling shell too (its own
  command line matches) - use `pkill -f "[c]ontextos serve"`.
