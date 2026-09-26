"""HTTP API. Each feature area adds its own router here."""

from fastapi import APIRouter

from contextos.api import health

router = APIRouter()
router.include_router(health.router)
