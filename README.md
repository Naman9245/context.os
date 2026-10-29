# context.os

**Your university life, organised.** ContextOS is a local AI assistant for
students who are drowning in PDFs, assignments and deadlines.

- **Organises your files.** It scans your Downloads and other folders, reads
  every PDF (including scanned ones), works out the subject and type, and
  moves it into a clean `Semester / Subject / Type /` library. You approve
  every move first, and any move can be undone.
- **Keeps track of your assignments.** Khushi, the assistant, finds due dates in
  assignment sheets and notices, asks you when one has none, writes a to-do
  checklist for each assignment, and reminds you 5 and 3 days before.
- **Tracks your week.** It includes a study timer, a weekly progress chart,
  and an AI summary of where your time went.
- **Talks to you.** Chat with Khushi from any page: "what's due this week?",
  "open Spotify", "play lofi on YouTube", "search black holes on Wikipedia",
  "I finished the DBMS assignment", "open my OS notes". Everyday commands work
  instantly without any AI; study questions go to Gemini. Khushi reads her
  replies aloud, and in Chrome you can talk to her with the mic button.

It runs entirely on your machine. With `LLM_PROVIDER=none` nothing leaves it
at all. With a free Gemini or Groq key, only a short snippet of each
document is sent for classification.

## Quick start

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -e ".[dev,llm,ingest]"
cp ../.env.example .env        # optional: add a free Gemini or Groq key
.venv/bin/contextos serve --reload
```

To read scanned PDFs, also install Tesseract (`sudo apt install tesseract-ocr`).

Want to try it without touching your real Downloads? Generate a folder of
messy demo files and point ContextOS at it:

```bash
.venv/bin/python scripts/make_demo_files.py ~/contextos-demo/Downloads
WATCH_DIRS=~/contextos-demo/Downloads LIBRARY_ROOT=~/contextos-demo/Library \
  .venv/bin/contextos serve
```

```bash
cd frontend
npm install && npm run dev     # open http://localhost:5173
```

## Stack

FastAPI · SQLite (SQLModel) · React + Vite + TypeScript · Tailwind · Recharts ·
PyMuPDF + Tesseract OCR · Gemini / Groq (free tier)

## Status

The file organiser, assignments with reminders, and Khushi's chat and voice work end
to end. Next: a weekly progress page, then starting with the laptop - see the
[plan](docs/PLAN.md). How it is built: [architecture](docs/ARCHITECTURE.md).
