"""HTTP API. Each feature area adds its own router here."""

from fastapi import APIRouter

from contextos.api import browser, chat, files, health, organize, subjects, tasks

router = APIRouter()
router.include_router(health.router)
router.include_router(organize.router)
router.include_router(subjects.router)
router.include_router(files.router)
router.include_router(tasks.router)
router.include_router(chat.router)
router.include_router(browser.router)
