"""TemplateAudit AI — FastAPI Application Entrypoint."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from backend.config import STATIC_DIR, init_directories
from backend.routers import audit, system, templates
from backend.utils.sample_factory import ensure_seed_templates_and_samples


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Initialize runtime storage folders and seed sample templates/PDFs on startup."""
    init_directories()
    ensure_seed_templates_and_samples()
    yield


def create_app() -> FastAPI:
    """Construct and configure the FastAPI application instance."""
    init_directories()
    ensure_seed_templates_and_samples()

    application = FastAPI(
        title="TemplateAudit AI",
        description=(
            "Local-First Master .MD Base Builder & Non-Destructive Target PDF Report Auditor "
            "powered by PyMuPDF4LLM, Local Ollama, and Python SymPy."
        ),
        version="2.0.0",
        lifespan=lifespan,
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register modular API routers
    application.include_router(system.router)
    application.include_router(templates.router)
    application.include_router(audit.router)

    # Mount static frontend assets (CSS & JS modules)
    application.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @application.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def serve_frontend() -> HTMLResponse:
        """Serve the main application UI."""
        index_file = STATIC_DIR / "index.html"
        if not index_file.exists():
            raise HTTPException(status_code=404, detail="static/index.html not found.")
        return HTMLResponse(content=index_file.read_text(encoding="utf-8"))

    return application


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
