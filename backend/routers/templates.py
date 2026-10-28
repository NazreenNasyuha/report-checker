"""Feature 1 API Routes: Master .MD Base Builder (`/api/templates/*`)."""

from __future__ import annotations

import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from fastapi import APIRouter, File, HTTPException, UploadFile

from backend.config import SAMPLES_DIR, TEMP_DIR, TEMPLATES_DIR
from backend.schemas import (
    AIAssistRequest,
    AIAssistResponse,
    ExtractPdfResponse,
    SaveTemplateRequest,
    TemplateItem,
    TemplateListResponse,
)
from backend.services.ollama_service import (
    apply_ai_assist_to_markdown,
    compute_markdown_diff_lines,
)
from backend.services.pdf_service import (
    convert_pdf_to_structured_markdown,
    sanitize_template_name,
)
from backend.utils.sample_factory import (
    ensure_seed_templates_and_samples,
    generate_perfect_turbine_reference_pdf,
)


router = APIRouter(prefix="/api/templates", tags=["Feature 1: Master .MD Base Builder"])


@router.post("/extract-pdf", response_model=ExtractPdfResponse)
async def extract_perfect_pdf_to_md(file: UploadFile = File(...)) -> ExtractPdfResponse:
    """
    Upload a "Perfect/Reference PDF Report" -> uses `pymupdf4llm.to_markdown(pdf_path, page_chunks=True)`
    to convert it into a clean, structured `.md` string.
    """
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Please upload a valid .pdf file.")

    temp_id = uuid.uuid4().hex[:8]
    safe_name = Path(file.filename).name
    temp_pdf_path = TEMP_DIR / f"{temp_id}_{safe_name}"

    with open(temp_pdf_path, "wb") as out:
        shutil.copyfileobj(file.file, out)

    try:
        md_text, per_page = convert_pdf_to_structured_markdown(temp_pdf_path, title_label=safe_name)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to extract Markdown from PDF: {exc}") from exc

    suggested_name = sanitize_template_name(Path(safe_name).stem + "_Master_Standard")
    return ExtractPdfResponse(
        filename=safe_name,
        suggested_name=suggested_name,
        page_count=len(per_page),
        markdown=md_text,
    )


@router.post("/load-sample-perfect", response_model=ExtractPdfResponse)
async def load_sample_perfect_pdf() -> ExtractPdfResponse:
    """
    Extract the built-in `Perfect_Reference_Turbine_Report_2026.pdf` via `pymupdf4llm`
    so the user can test the Master .MD Base Builder with 1 click.
    """
    perfect_pdf = SAMPLES_DIR / "Perfect_Reference_Turbine_Report_2026.pdf"
    if not perfect_pdf.exists():
        generate_perfect_turbine_reference_pdf(perfect_pdf)
    md_text, per_page = convert_pdf_to_structured_markdown(
        perfect_pdf,
        title_label=perfect_pdf.name,
    )
    return ExtractPdfResponse(
        filename=perfect_pdf.name,
        suggested_name="Turbine_Thermal_Standard_v1",
        page_count=len(per_page),
        markdown=md_text,
    )


@router.post("/ai-assist", response_model=AIAssistResponse)
async def ai_assist_markdown_edit(req: AIAssistRequest) -> AIAssistResponse:
    """
    Takes current `.md` text + user instruction string -> uses local Ollama
    (`http://localhost:11434/api/chat`) to insert/edit rules in the `.md`
    (with deterministic rule-injection fallback) -> returns updated `.md` text
    along with `previous_markdown` and `diff_lines` for inline Red/Green diff inspection.
    """
    if not req.instruction.strip():
        raise HTTPException(status_code=400, detail="Instruction cannot be empty.")

    updated_md, engine_used, summary = apply_ai_assist_to_markdown(
        current_md=req.markdown,
        instruction=req.instruction,
        ollama_model=req.ollama_model,
        ollama_url=req.ollama_url,
    )
    diff_lines = compute_markdown_diff_lines(req.markdown, updated_md)
    return AIAssistResponse(
        markdown=updated_md,
        previous_markdown=req.markdown,
        engine_used=engine_used,
        summary=summary,
        diff_lines=diff_lines,
    )


@router.post("/save", response_model=TemplateItem)
async def save_master_template(req: SaveTemplateRequest) -> TemplateItem:
    """Saves the edited `.md` file to `./templates/{name}.md`."""
    clean_name = sanitize_template_name(req.name)
    if not req.markdown.strip():
        raise HTTPException(status_code=400, detail="Markdown content cannot be empty.")

    target_path = TEMPLATES_DIR / f"{clean_name}.md"
    target_path.write_text(req.markdown, encoding="utf-8")
    stat_info = target_path.stat()

    return TemplateItem(
        name=clean_name,
        filename=target_path.name,
        markdown=req.markdown,
        size_bytes=stat_info.st_size,
        updated_at=datetime.fromtimestamp(stat_info.st_mtime, tz=timezone.utc).isoformat(),
    )


@router.get("/list", response_model=TemplateListResponse)
async def list_saved_templates() -> TemplateListResponse:
    """Lists all saved Master `.md` files in `./templates/` and their contents."""
    ensure_seed_templates_and_samples()
    items: List[TemplateItem] = []
    for p in sorted(TEMPLATES_DIR.glob("*.md")):
        try:
            st = p.stat()
            content = p.read_text(encoding="utf-8")
            items.append(
                TemplateItem(
                    name=p.stem,
                    filename=p.name,
                    markdown=content,
                    size_bytes=st.st_size,
                    updated_at=datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
                )
            )
        except Exception:
            continue
    return TemplateListResponse(templates=items)
