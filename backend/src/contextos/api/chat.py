"""Talking to Khushi."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, delete, select

from contextos.agent.chat import respond
from contextos.api.schemas import DocumentOut, documents_out
from contextos.api.tasks import TaskOut, tasks_out
from contextos.config import get_settings
from contextos.db import get_session
from contextos.llm import get_llm
from contextos.models import ChatMessage, Document, Task

router = APIRouter(prefix="/chat", tags=["chat"])

MAX_LEN = 2000


class MessageIn(BaseModel):
    text: str


class MessageOut(BaseModel):
    id: int
    role: str
    text: str
    created_at: datetime
    actions: list[dict] = []
    suggestions: list[str] = []
    by: str | None = None
    # Shown as cards with their *current* state (a task finished since shows as done).
    tasks: list[TaskOut] = []
    files: list[DocumentOut] = []


class Exchange(BaseModel):
    user: MessageOut
    reply: MessageOut


def _out(session: Session, m: ChatMessage) -> MessageOut:
    p = m.payload or {}
    tasks, files = [], []
    if p.get("task_ids"):
        found = {t.id: t for t in session.exec(select(Task).where(Task.id.in_(p["task_ids"])))}
        tasks = tasks_out(session, [found[i] for i in p["task_ids"] if i in found])
    if p.get("doc_ids"):
        found = {d.id: d for d in session.exec(select(Document).where(
            Document.id.in_(p["doc_ids"])))}
        files = documents_out(session, [found[i] for i in p["doc_ids"] if i in found])
    return MessageOut(id=m.id, role=m.role, text=m.text, created_at=m.created_at,
                      actions=p.get("actions", []), suggestions=p.get("suggestions", []),
                      by=p.get("by"), tasks=tasks, files=files)


@router.get("", response_model=list[MessageOut])
def history(limit: int = 50, session: Session = Depends(get_session)) -> list[MessageOut]:
    rows = session.exec(select(ChatMessage).order_by(ChatMessage.id.desc()).limit(limit)).all()
    return [_out(session, m) for m in reversed(rows)]


@router.post("", response_model=Exchange)
def send(body: MessageIn, session: Session = Depends(get_session)) -> Exchange:
    text = body.text.strip()
    if not text:
        raise HTTPException(422, "say something!")
    text = text[:MAX_LEN]
    reply = respond(session, text, settings=get_settings(), llm=get_llm())
    # The user's message is saved after Khushi answers, so it is not in her LLM
    # history twice (it is already the prompt's last line).
    user = ChatMessage(role="user", text=text)
    session.add(user)
    session.commit()
    khushi = ChatMessage(role="khushi", text=reply.text, payload=reply.payload())
    session.add(khushi)
    session.commit()
    session.refresh(user)
    session.refresh(khushi)
    return Exchange(user=_out(session, user), reply=_out(session, khushi))


@router.delete("", status_code=204)
def clear(session: Session = Depends(get_session)) -> None:
    session.exec(delete(ChatMessage))
    session.commit()
