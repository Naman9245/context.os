"""HTTP API. Each feature area adds its own router here."""

from fastapi import APIRouter

from contextos.api import files, health, organize, subjects

router = APIRouter()
router.include_router(health.router)
router.include_router(organize.router)
router.include_router(subjects.router)
router.include_router(files.router)
