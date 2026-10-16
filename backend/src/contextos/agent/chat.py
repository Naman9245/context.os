"""Khushi's conversation loop.

1. Rules (agent/intents.py) handle everyday commands instantly, with no quota.
2. Anything else goes to the LLM, which answers and may pick ONE action from
   the same allowlist the rules use (agent/tools.py).
3. Without an LLM (or when it is out of quota) she says what she can do.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field
from sqlmodel import Session, select

from contextos.agent.intents import parse
from contextos.agent.khushi import NAME, build_briefing, greeting
from contextos.agent.tools import SUGGESTIONS, Reply, Tools, is_vague
from contextos.config import Settings
from contextos.llm import LLMError, LLMProvider
from contextos.models import ChatMessage, Subject, Task, TaskStatus
from contextos.tasks.service import long_date, short_date

log = logging.getLogger(__name__)

HISTORY_FOR_LLM = 6

HELP = (
    f"I'm {NAME}, your study assistant. I can:\n"
    "• organise your downloaded files into folders\n"
    "• keep track of assignments and remind you before deadlines\n"
    "• open apps like Spotify, Discord or Chrome, and websites like YouTube\n"
    "• search Google, Wikipedia or YouTube, and play music\n"
    "• answer quick study questions"
)


class ChatPlan(BaseModel):
    reply: str = Field(description="What Khushi says. 1-3 short, friendly sentences.")
    action: Literal["none", "open", "play", "search", "list_tasks", "add_task",
                    "complete_task", "find_files", "organize"] = "none"
    target: str | None = Field(
        None, description="open: app/website/file name. play/search/find_files: the query. "
                          "add_task: the task title. complete_task: which assignment.")
    where: str | None = Field(
        None, description="search: google|wikipedia|youtube|spotify|maps. play: youtube|spotify. "
                          "list_tasks: today|tomorrow|this week|next week|overdue")
    due_date: str | None = Field(None, description="add_task only: YYYY-MM-DD")


SYSTEM = f"""You are {NAME}, a warm, upbeat and concise study assistant for a university student.
You run on the student's own laptop and can do things for them through ONE action per reply:
- open: open an app (Spotify, Discord, Chrome, VS Code...), a website, or one of their files
- play: play music/videos (YouTube by default, or Spotify)
- search: search the web (Google by default, Wikipedia, YouTube, Spotify, Maps)
- list_tasks: show their assignments and deadlines
- add_task: add an assignment or reminder (with due_date if they gave one)
- complete_task: mark an assignment as finished
- find_files: find their notes, question papers, slides... in their library
- organize: scan and organise their downloaded files
Use action "none" for conversation and for study questions, which you answer briefly and
clearly yourself. Never claim you did something unless you chose the action for it. If a
request is unclear, ask a short question. Do not invent assignments or files."""


def _context(session: Session, now: datetime) -> str:
    tasks = session.exec(select(Task).where(Task.status == TaskStatus.todo)
                         .order_by(Task.due_at)).all()[:10]
    lines = [f"Today is {now.strftime('%A %d %B %Y, %H:%M')}."]
    if tasks:
        lines.append("Their open assignments: " + "; ".join(
            f"{t.title} (due {short_date(t.due_at) if t.due_at else 'no date'})"
            for t in tasks))
    subjects = session.exec(select(Subject.name)).all()
    if subjects:
        lines.append("Their subjects: " + ", ".join(subjects))
    return "\n".join(lines)


def _history(session: Session) -> str:
    rows = session.exec(select(ChatMessage).order_by(ChatMessage.id.desc())
                        .limit(HISTORY_FOR_LLM)).all()
    return "\n".join(f"{'Student' if m.role == 'user' else NAME}: {m.text[:300]}"
                     for m in reversed(rows))


def _run_plan(tools: Tools, plan: ChatPlan) -> Reply | None:
    t, w = plan.target or "", (plan.where or "").lower()
    match plan.action:
        case "open" if t:
            return tools.open(t)
        case "play" if t:
            return tools.play(t, "spotify" if w == "spotify" else "youtube")
        case "search" if t:
            return tools.search(t, w or "google")
        case "list_tasks":
            return tools.list_tasks(w or None)
        case "add_task" if t:
            return tools.add_task(t, plan.due_date)
        case "complete_task" if t:
            return tools.complete_task(t)
        case "find_files" if t:
            return tools.find_files(t)
        case "organize":
            return tools.organize()
    return None


def _ask_llm(session: Session, llm: LLMProvider, text: str, tools: Tools, now: datetime
             ) -> Reply:
    prompt = (f"{_context(session, now)}\n\nRecent conversation:\n{_history(session)}\n\n"
              f"Student: {text}")
    try:
        plan = llm.complete_json(prompt, ChatPlan, system=SYSTEM)
    except Exception as e:  # out of quota, offline, bad reply...
        log.warning("chat LLM failed: %s", e)
        quota = isinstance(e, LLMError) and ("quota" in str(e) or "busy" in str(e)
                                             or "no model" in str(e))
        why = "my AI brain is taking a break (free quota used up)" if quota else \
            "I couldn't reach my AI brain just now"
        return Reply(f"Sorry, {why}. I can still open apps, search the web, and track your "
                     "assignments - try one of these:", suggestions=SUGGESTIONS)
    done = _run_plan(tools, plan)
    if done is None:
        return Reply(plan.reply.strip() or "Hmm, could you say that another way?", by=llm.name)
    # Say what really happened, not what the model expected to happen.
    done.by = llm.name
    if done.unresolved and plan.reply.strip():
        done.text = plan.reply.strip()
    return done


def respond(session: Session, text: str, *, settings: Settings, llm: LLMProvider | None,
            now: datetime | None = None) -> Reply:
    now = now or datetime.now()
    tools = Tools(session, settings, now)
    intent = parse(text)

    reply: Reply | None = None
    if intent is not None:
        a = intent.args
        match intent.name:
            case "greet":
                b = build_briefing(session, now)
                reply = Reply(" ".join([b.greeting, *(line.text for line in b.lines)]),
                              suggestions=SUGGESTIONS[:3])
            case "thanks":
                reply = Reply("Anytime! Good luck with your work.")
            case "help":
                reply = Reply(HELP, suggestions=SUGGESTIONS)
            case "time":
                reply = Reply(f"It's {now.strftime('%I:%M %p').lstrip('0')}, "
                              f"{long_date(now)}.")
            case "play":
                reply = tools.play(a["q"], a.get("where", "youtube").replace("yt", "youtube"))
            case "search":
                reply = tools.search(a["q"], a.get("where", "google"))
            case "organize":
                reply = tools.organize()
            case "list_tasks":
                reply = tools.list_tasks(a.get("when"))
            case "complete_task":
                reply = tools.complete_task(a["q"])
            case "add_task":
                reply = tools.add_task(a["q"])
            case "find_files":
                reply = tools.find_files(a["q"])
            case "open":
                reply = tools.open(a["target"])

    # "search me THIS on wikipedia" only makes sense with the conversation: ask the LLM.
    query = intent.args.get("q") or intent.args.get("target") if intent else None
    vague = query is not None and is_vague(query)
    if reply is not None and not reply.unresolved and not vague:
        return reply
    if llm is not None:
        return _ask_llm(session, llm, text, tools, now)
    if reply is not None:
        return reply
    return Reply(f"I'm not sure how to help with that yet. {greeting(now).split('!')[0]}! "
                 "Here are some things I can do:", suggestions=SUGGESTIONS)
