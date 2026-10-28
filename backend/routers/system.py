"""System health and local Ollama connection status routes."""

from __future__ import annotations

from typing import Any, Dict
from fastapi import APIRouter

from backend.config import DEFAULT_OLLAMA_MODEL, OLLAMA_CHAT_URL
from backend.schemas import OllamaStatusResponse
from backend.services.ollama_service import check_ollama_available


router = APIRouter(prefix="/api", tags=["System & Ollama Status"])


@router.get("/health")
async def health_check() -> Dict[str, Any]:
    """Return service health metadata."""
    return {"status": "ok", "service": "TemplateAudit AI", "version": "2.0.0"}


@router.get("/ollama/status", response_model=OllamaStatusResponse)
async def get_ollama_status(model: str = DEFAULT_OLLAMA_MODEL) -> Dict[str, Any]:
    """Check whether local Ollama is reachable and return installed models."""
    return check_ollama_available(OLLAMA_CHAT_URL, model)
