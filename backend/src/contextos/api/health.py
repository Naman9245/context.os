from fastapi import APIRouter

from contextos import __version__
from contextos.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "version": __version__,
        "llm_provider": settings.llm_provider,
        "library_root": str(settings.library_root),
        "watch_dirs": [str(p) for p in settings.watch_dirs],
    }
