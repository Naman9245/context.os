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

Full plan: `~/.claude/plans/lets-make-the-context-os-quirky-hopcroft.md`.

## Where things stand

| Phase | State |
|---|---|
| 00 Scaffold | done - FastAPI + SQLite tables + `contextos serve`, React shell with page placeholders |
| 01 LLM layer (Gemini / Groq, JSON mode, rate limit, cache) | not started |
| 02 File organiser (scan, extract, OCR, classify, plan, move + undo, watch) | not started |
| 03 Deadlines & tasks (extracted deadlines, CRUD, reminders) | not started |
| 04 Weekly progress (study timer, chart, AI summary) | not started |
| 05 Chat assistant + local actions | not started |
| 06 Post-v1: RAG over notes, syllabus mind map, Spotify API, packaging | not started |

## Commands

```bash
# backend (from backend/)
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/contextos serve --reload          # API on :8000
.venv/bin/python -m pytest -q && .venv/bin/ruff check src tests

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
