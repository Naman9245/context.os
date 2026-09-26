# context.os

**Your university life, organised.** ContextOS is a local AI assistant for
students who are drowning in PDFs, assignments and deadlines.

- **Organises your files.** It scans your Downloads and other folders, reads
  every PDF (including scanned ones), works out the subject and type, and
  moves it into a clean `Semester / Subject / Type /` library. You approve
  every move first, and any move can be undone.
- **Finds your deadlines.** It pulls due dates out of assignment sheets and
  notices and turns them into tasks with desktop reminders.
- **Tracks your week.** It includes a study timer, a weekly progress chart,
  and an AI summary of where your time went.
- **Does things for you.** "What's due this week?", "search normalisation in
  DBMS", "play lofi on YouTube": the chat assistant runs on your own laptop.

It runs entirely on your machine. With `LLM_PROVIDER=none` nothing leaves it
at all. With a free Gemini or Groq key, only a short snippet of each
document is sent for classification.

## Quick start

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
cp ../.env.example .env        # optional
.venv/bin/contextos serve --reload
```

```bash
cd frontend
npm install && npm run dev     # open http://localhost:5173
```

## Stack

FastAPI · SQLite (SQLModel) · React + Vite + TypeScript · Tailwind · Recharts ·
PyMuPDF + Tesseract OCR · Gemini / Groq (free tier)

## Status

Early development. See the phase table in [CLAUDE.md](CLAUDE.md).
