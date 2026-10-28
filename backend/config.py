"""Centralized application configuration and filesystem paths."""

from __future__ import annotations

import os
from pathlib import Path


BASE_DIR: Path = Path(__file__).resolve().parent.parent
TEMPLATES_DIR: Path = BASE_DIR / "templates"
SAMPLES_DIR: Path = BASE_DIR / "samples"
STORAGE_DIR: Path = BASE_DIR / "storage"
STATIC_DIR: Path = BASE_DIR / "static"

# Runtime storage subdirectories
UPLOADS_DIR: Path = STORAGE_DIR / "uploads"
RENDERS_DIR: Path = STORAGE_DIR / "renders"
EXPORTS_DIR: Path = STORAGE_DIR / "exports"
TEMP_DIR: Path = STORAGE_DIR / "temp"

# Environment-configurable settings
OLLAMA_CHAT_URL: str = os.getenv("OLLAMA_CHAT_URL", "http://localhost:11434/api/chat")
DEFAULT_OLLAMA_MODEL: str = os.getenv("DEFAULT_OLLAMA_MODEL", "qwen2.5:7b-instruct")
OLLAMA_TIMEOUT_SECONDS: float = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "35.0"))
RENDER_DPI: int = int(os.getenv("RENDER_DPI", "150"))
DEFAULT_MATH_TOLERANCE: float = float(os.getenv("DEFAULT_MATH_TOLERANCE", "0.01"))


def init_directories() -> None:
    """Ensure all required application directories exist on startup."""
    for directory in (
        TEMPLATES_DIR,
        SAMPLES_DIR,
        STATIC_DIR,
        UPLOADS_DIR,
        RENDERS_DIR,
        EXPORTS_DIR,
        TEMP_DIR,
    ):
        directory.mkdir(parents=True, exist_ok=True)
