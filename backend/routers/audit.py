"""Feature 2 API Routes: Audit Target PDF Against Master .MD Base (`/api/audit/*` & `/api/renders/*`)."""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from typing import List

from fastapi import APIRouter, Body, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from backend.config import (
    DEFAULT_OLLAMA_MODEL,
    RENDERS_DIR,
    SAMPLES_DIR,
    TEMPLATES_DIR,
    UPLOADS_DIR,
)
from backend.schemas import AUDIT_SESSION_STORE, AuditRunResponse
from backend.services.audit_service import (
    execute_audit_pipeline,
    stream_audit_pipeline_events,
)
from backend.services.pdf_service import (
    export_annotated_review_copy,
    sanitize_template_name,
)
from backend.utils.sample_factory import ensure_seed_templates_and_samples


router = APIRouter(prefix="/api", tags=["Feature 2: Target PDF Auditor"])


@router.post("/audit/run", response_model=AuditRunResponse)
async def run_target_pdf_audit(
    template_name: str = Form(...),
    target_pdf: UploadFile = File(...),
    ollama_model: str = Form(DEFAULT_OLLAMA_MODEL),
) -> AuditRunResponse:
    """
    Takes `template_name` + uploaded `target_pdf` + `ollama_model` (default `"qwen2.5:7b-instruct"`).
    Renders page images via `page.get_pixmap(dpi=150)`, runs the Ollama + SymPy audit against
    the Master `.md` Base, maps coordinates via `page.search_for()` and `page.find_tables()`,
    and returns page image URLs + the list of issues with normalized bounding box coordinates.
    """
    clean_tpl = sanitize_template_name(template_name)
    tpl_path = TEMPLATES_DIR / f"{clean_tpl}.md"
    if not tpl_path.exists():
        raise HTTPException(
            status_code=404, detail=f"Master .MD template '{clean_tpl}.md' not found."
        )

    if not target_pdf.filename or not target_pdf.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Please upload a valid Target .pdf file.")

    master_md = tpl_path.read_text(encoding="utf-8")

    upload_id = uuid.uuid4().hex[:8]
    safe_pdf_name = Path(target_pdf.filename).name
    upload_folder = UPLOADS_DIR / upload_id
    upload_folder.mkdir(parents=True, exist_ok=True)
    saved_pdf_path = upload_folder / safe_pdf_name

    with open(saved_pdf_path, "wb") as out:
        shutil.copyfileobj(target_pdf.file, out)

    return execute_audit_pipeline(
        pdf_path=saved_pdf_path,
        target_filename=safe_pdf_name,
        template_name=clean_tpl,
        master_md=master_md,
        ollama_model=ollama_model,
    )


@router.post("/audit/run-sample", response_model=AuditRunResponse)
async def run_sample_target_pdf_audit(
    template_name: str = Form("Turbine_Thermal_Standard_v1"),
    ollama_model: str = Form(DEFAULT_OLLAMA_MODEL),
) -> AuditRunResponse:
    """
    Convenience 1-click sample audit endpoint for Feature 2:
    Audits `samples/Target_Turbine_Report_With_Errors_2026.pdf` against the selected Master `.md` Base.
    """
    ensure_seed_templates_and_samples()
    clean_tpl = sanitize_template_name(template_name)
    tpl_path = TEMPLATES_DIR / f"{clean_tpl}.md"
    if not tpl_path.exists():
        tpl_path = TEMPLATES_DIR / "Turbine_Thermal_Standard_v1.md"
        clean_tpl = "Turbine_Thermal_Standard_v1"

    master_md = tpl_path.read_text(encoding="utf-8")
    target_pdf_path = SAMPLES_DIR / "Target_Turbine_Report_With_Errors_2026.pdf"

    return execute_audit_pipeline(
        pdf_path=target_pdf_path,
        target_filename=target_pdf_path.name,
        template_name=clean_tpl,
        master_md=master_md,
        ollama_model=ollama_model,
    )


@router.post("/audit/stream")
async def stream_target_pdf_audit(
    template_name: str = Form(...),
    target_pdf: UploadFile = File(...),
    ollama_model: str = Form(DEFAULT_OLLAMA_MODEL),
) -> StreamingResponse:
    """SSE streaming endpoint for real-time page rendering and progressive audit status."""
    clean_tpl = sanitize_template_name(template_name)
    tpl_path = TEMPLATES_DIR / f"{clean_tpl}.md"
    if not tpl_path.exists():
        raise HTTPException(
            status_code=404, detail=f"Master .MD template '{clean_tpl}.md' not found."
        )

    if not target_pdf.filename or not target_pdf.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Please upload a valid Target .pdf file.")

    master_md = tpl_path.read_text(encoding="utf-8")
    upload_id = uuid.uuid4().hex[:8]
    safe_pdf_name = Path(target_pdf.filename).name
    upload_folder = UPLOADS_DIR / upload_id
    upload_folder.mkdir(parents=True, exist_ok=True)
    saved_pdf_path = upload_folder / safe_pdf_name

    with open(saved_pdf_path, "wb") as out:
        shutil.copyfileobj(target_pdf.file, out)

    return StreamingResponse(
        stream_audit_pipeline_events(
            pdf_path=saved_pdf_path,
            target_filename=safe_pdf_name,
            template_name=clean_tpl,
            master_md=master_md,
            ollama_model=ollama_model,
        ),
        media_type="text/event-stream",
    )


@router.post("/audit/stream-sample")
async def stream_sample_target_pdf_audit(
    template_name: str = Form("Turbine_Thermal_Standard_v1"),
    ollama_model: str = Form(DEFAULT_OLLAMA_MODEL),
) -> StreamingResponse:
    """SSE streaming endpoint for the built-in sample Target PDF report."""
    ensure_seed_templates_and_samples()
    clean_tpl = sanitize_template_name(template_name)
    tpl_path = TEMPLATES_DIR / f"{clean_tpl}.md"
    if not tpl_path.exists():
        tpl_path = TEMPLATES_DIR / "Turbine_Thermal_Standard_v1.md"
        clean_tpl = "Turbine_Thermal_Standard_v1"

    master_md = tpl_path.read_text(encoding="utf-8")
    target_pdf_path = SAMPLES_DIR / "Target_Turbine_Report_With_Errors_2026.pdf"

    return StreamingResponse(
        stream_audit_pipeline_events(
            pdf_path=target_pdf_path,
            target_filename=target_pdf_path.name,
            template_name=clean_tpl,
            master_md=master_md,
            ollama_model=ollama_model,
        ),
        media_type="text/event-stream",
    )


@router.get("/renders/{audit_id}/{image_name}")
async def serve_rendered_page_image(audit_id: str, image_name: str) -> FileResponse:
    """Serve high-resolution 150 DPI rendered Target PDF page images."""
    img_path = RENDERS_DIR / audit_id / Path(image_name).name
    if not img_path.exists():
        raise HTTPException(status_code=404, detail="Rendered page image not found.")
    return FileResponse(str(img_path), media_type="image/png")


@router.post("/audit/{audit_id}/export-pdf")
async def export_annotated_review_pdf(
    audit_id: str,
    ignored_ids: List[str] = Body(default_factory=list),
) -> FileResponse:
    """
    Export a separate `{stem}_review_copy.pdf` with native PyMuPDF annotations
    (`page.add_rect_annot` and `page.add_squiggly_annot`) for all active (non-ignored) issues,
    leaving the original Target PDF untouched.
    """
    cached = AUDIT_SESSION_STORE.get(audit_id)
    if not cached:
        raise HTTPException(status_code=404, detail="Audit session not found.")

    pdf_path: Path = cached["pdf_path"]
    target_filename: str = cached["target_filename"]
    audit_res: AuditRunResponse = cached["response"]

    out_file = export_annotated_review_copy(
        pdf_path=pdf_path,
        target_filename=target_filename,
        audit_id=audit_id,
        issues=audit_res.issues,
        ignored_ids=set(ignored_ids),
    )

    stem = Path(target_filename).stem
    return FileResponse(
        path=str(out_file),
        media_type="application/pdf",
        filename=f"{stem}_review_copy.pdf",
    )
