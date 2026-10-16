"""Khushi's conversation loop.

1. Rules (agent/intents.py) handle everyday commands instantly, with no quota.
2. Anything else goes to the LLM, which answers and may pick ONE action from
   the same allowlist the rules use (agent/tools.py).
3. Without an LLM (or when it is out of quota) she says what she can do.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field
from sqlmodel import Session, select

from contextos.agent.intents import correction_target, parse, split_steps
from contextos.agent.khushi import NAME, build_briefing, greeting
from contextos.agent.tools import SUGGESTIONS, Reply, Tools, is_vague
from contextos.config import Settings
from contextos.llm import LLMProvider
from contextos.models import ChatMessage, Subject, Task, TaskStatus
from contextos.tasks.service import long_date, short_date

log = logging.getLogger(__name__)

HISTORY_FOR_LLM = 10

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
    action: Literal["none", "open", "open_result", "play", "search", "list_tasks", "add_task",
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
- open_result: open the first result/file/video of what you just searched, played or showed
  ("open it", "play the first one", "watch that video")
- play: play music/videos (YouTube by default, or Spotify)
- search: search the web (Google by default, Wikipedia, YouTube, Spotify, Maps)
- list_tasks: show their assignments and deadlines
- add_task: add an assignment or reminder (with due_date if they gave one)
- complete_task: mark an assignment as finished
- find_files: find their notes, question papers, slides... in their library
- organize: scan and organise their downloaded files
Use action "none" for conversation and for study questions, which you answer briefly and
clearly yourself. Never claim you did something unless you chose the action for it. If a
request is unclear, ask a short question. Do not invent assignments or files.
Messages are often spoken, so speech recognition may have misheard names: "play hairstyle"
means Harry Styles, "are jeet sing" means Arijit Singh. Put the real, correctly spelled
name in "target".
For "open", use the app or website the student named (fixing only obvious typos). Never
swap in a different app because it seems similar: if you don't recognise the name, use
action "none" and ask what they mean."""


def describe(ctx: dict | None) -> str | None:
    """The last thing Khushi did, in words, so "it" makes sense to the model too."""
    kind = (ctx or {}).get("kind")
    if kind == "search":
        return (f"searched {ctx.get('where', 'the web')} for “{ctx['query']}” - the results "
                "page is open in the browser")
    if kind == "play":
        return f"opened “{ctx['query']}” on {ctx.get('where', 'YouTube')}"
    if kind == "files":
        return f"showed {len(ctx.get('doc_ids', []))} of their files"
    if kind == "tasks":
        return f"showed {len(ctx.get('task_ids', []))} of their assignments"
    if kind == "page":
        return f"opened “{ctx.get('title')}”"
    return None


def _context(session: Session, now: datetime, ctx: dict | None) -> str:
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
    last = describe(ctx)
    if last:
        lines.append(f"The last thing you did: {last}.")
    return "\n".join(lines)


def _history(session: Session) -> str:
    rows = session.exec(select(ChatMessage).order_by(ChatMessage.id.desc())
                        .limit(HISTORY_FOR_LLM)).all()
    return "\n".join(f"{'Student' if m.role == 'user' else NAME}: {m.text[:300]}"
                     for m in reversed(rows))


def _run_plan(tools: Tools, plan: ChatPlan, ctx: dict | None) -> Reply | None:
    t, w = plan.target or "", (plan.where or "").lower()
    match plan.action:
        case "open_result":
            return tools.open_result(ctx)
        case "open" if t:
            return tools.open(t)
        case "play" if t:
            # The model already read the request (and fixed misheard names).
            return tools.play(t, w if w in ("spotify", "youtube") else None, resolve=False)
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


# A reply that says something is happening ("Opening the first video now!") when no
# action was chosen would be a lie: nothing happens. Khushi says so instead.
_CLAIMS_ACTION = re.compile(
    r"^(?:(?:ok(?:ay)?|sure|got it|alright|done|on it)\W+)*(?:i'?m |i am |now )?"
    r"(?:opening|playing|searching|launching|starting|loading|putting on|clicking)\b"
    r"|\bi(?:'ve| have)? (?:opened|played|started|launched|searched|loaded|clicked)\b", re.I)


def _ask_llm(session: Session, llm: LLMProvider, text: str, tools: Tools, now: datetime,
             ctx: dict | None) -> Reply:
    prompt = (f"{_context(session, now, ctx)}\n\nRecent conversation:\n{_history(session)}"
              f"\n\nStudent: {text}")
    try:
        plan = llm.complete_json(prompt, ChatPlan, system=SYSTEM)
    except Exception as e:  # out of quota, overloaded, offline, bad reply...
        log.warning("chat LLM failed: %s", e)
        kind = getattr(e, "kind", None)
        if kind == "busy":
            why = "Google's AI is overloaded right now (try again in a minute)"
        elif kind == "quota":
            why = "my free AI quota is used up for now"
        else:
            why = "I couldn't reach my AI brain just now"
        return Reply(f"Sorry, {why}. I can still open apps, play music, search the web and "
                     "track your assignments - try one of these:", suggestions=SUGGESTIONS)
    done = _run_plan(tools, plan, ctx)
    if done is None:
        said = plan.reply.strip()
        if _CLAIMS_ACTION.search(said):
            return Reply("Sorry, I can't do that part myself yet.", suggestions=SUGGESTIONS,
                         by=llm.name, unresolved=True)
        return Reply(said or "Hmm, could you say that another way?", by=llm.name)
    # Say what really happened, not what the model expected to happen.
    done.by = llm.name
    if done.unresolved and plan.reply.strip():
        done.text = plan.reply.strip()
    return done


def last_context(session: Session) -> dict | None:
    """What Khushi's most recent reply produced (a search, files, assignments...)."""
    for m in session.exec(select(ChatMessage).order_by(ChatMessage.id.desc()).limit(6)):
        if m.role == "khushi":
            p = m.payload or {}
            ctx = p.get("context") or p.get("redo")  # "redo" = before 2026-10-16
            if ctx:
                return ctx
    return None


SEARCH_SITES = {"google", "wikipedia", "youtube", "maps", "github"}
MUSIC_SITES = {"spotify", "youtube"}


def _inherited(ctx: dict | None, chained: bool, sites: set[str]) -> str | None:
    """After "open YouTube", a plain "search X" means on YouTube. Within one message
    ("search X on YouTube and then search Y") the last search's site carries on too."""
    if not ctx:
        return None
    if ctx.get("kind") == "site" or (chained and ctx.get("kind") in ("search", "play")):
        return ctx.get("where") if ctx.get("where") in sites else None
    return None


def respond(session: Session, text: str, *, settings: Settings, llm: LLMProvider | None,
            now: datetime | None = None) -> Reply:
    now = now or datetime.now()
    tools = Tools(session, settings, now, llm)
    ctx = last_context(session)
    steps = split_steps(text)
    if len(steps) == 1:
        return _respond_one(session, text, tools, llm, now, ctx, chained=False)

    # "open YouTube and then search X and then open the first video": in order, each
    # step seeing what the one before it did. Stop at the first step that fails.
    replies: list[Reply] = []
    for step in steps:
        reply = _respond_one(session, step, tools, llm, now, ctx, chained=True)
        replies.append(reply)
        ctx = reply.context or ctx
        if reply.unresolved or any(not a.get("ok") for a in reply.actions):
            break
    return _combine(replies, steps)


def _combine(replies: list[Reply], steps: list[str]) -> Reply:
    last = replies[-1]
    lines = [r.text for r in replies]
    skipped = steps[len(replies):]
    if skipped:
        lines.append("I stopped there, so I didn't do: " + "; ".join(skipped) + ".")
    return Reply(
        "\n".join(lines),
        actions=[a for r in replies for a in r.actions],
        task_ids=next((r.task_ids for r in reversed(replies) if r.task_ids), []),
        doc_ids=next((r.doc_ids for r in reversed(replies) if r.doc_ids), []),
        suggestions=last.suggestions,
        by=next((r.by for r in replies if r.by != "rules"), "rules"),
        context=next((r.context for r in reversed(replies) if r.context), None),
    )


def _respond_one(session: Session, text: str, tools: Tools, llm: LLMProvider | None,
                 now: datetime, ctx: dict | None, *, chained: bool) -> Reply:
    # "not on YouTube, I want Spotify": repeat the last request where they asked.
    target = correction_target(text)
    if target and ctx and ctx.get("kind") in ("search", "play"):
        return tools.redo(ctx, target)

    intent = parse(text)
    # "open it" / "mark it done": "it" is whatever Khushi just showed.
    if intent is not None and intent.name == "open_result":
        reply = tools.open_result(ctx)
        if not reply.unresolved or llm is None:
            return reply
        return _ask_llm(session, llm, text, tools, now, ctx)
    if intent is not None and intent.name == "complete_task" and is_vague(intent.args["q"]):
        reply = tools.complete_in_context(ctx)
        if not reply.unresolved or llm is None:
            return reply
        return _ask_llm(session, llm, text, tools, now, ctx)

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
                reply = tools.play(a["q"], a.get("where") or _inherited(ctx, chained,
                                                                        MUSIC_SITES))
            case "search":
                reply = tools.search(a["q"], a.get("where") or _inherited(ctx, chained,
                                                                          SEARCH_SITES)
                                     or "google")
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
        return _ask_llm(session, llm, text, tools, now, ctx)
    if reply is not None:
        return reply
    return Reply(f"I'm not sure how to help with that yet. {greeting(now).split('!')[0]}! "
                 "Here are some things I can do:", suggestions=SUGGESTIONS)
