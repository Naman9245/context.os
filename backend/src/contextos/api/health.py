from fastapi import APIRouter, Request

from contextos import __version__, frontend
from contextos.agent.notify import notifications_available
from contextos.browser import bridge
from contextos.config import get_settings
from contextos.ingest.ocr import ocr_available

router = APIRouter(tags=["health"])


@router.get("/health")
def health(request: Request) -> dict:
    settings = get_settings()
    model = {"gemini": settings.gemini_model, "groq": settings.groq_model}.get(
        settings.llm_provider)
    watcher = getattr(request.app.state, "watcher", None)
    return {
        "status": "ok",
        "version": __version__,
        "build": frontend.build_id(),
        "llm_provider": settings.llm_provider,
        "llm_model": model,
        "ocr_available": ocr_available(),
        "watching": bool(watcher and watcher.running),
        "notifications_available": notifications_available(),
        "browser_extension": bridge.connected,
        "extension_folder": str(frontend.FRONTEND_DIST.parents[1] / "browser-extension"),
        "reminder_days": settings.reminder_days,
        "library_root": str(settings.library_root),
        "watch_dirs": [str(p) for p in settings.watch_dirs],
    }
