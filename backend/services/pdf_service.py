"""PDF extraction, high-resolution rendering, SHA-256 integrity, and native PDF annotation export."""

from __future__ import annotations

import hashlib
import os
import re
import stat
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

import pymupdf as fitz  # PyMuPDF
import pymupdf4llm

from backend.config import EXPORTS_DIR, RENDERS_DIR, RENDER_DPI
from backend.schemas import AuditIssueOut, PageRenderOut


def compute_sha256(file_path: Path) -> str:
    """Compute SHA-256 hex digest of a file without modifying it."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def lock_file_readonly(file_path: Path) -> None:
    """Set read-only OS permission bit on an uploaded PDF file."""
    try:
        os.chmod(file_path, stat.S_IREAD)
    except OSError:
        pass


def sanitize_template_name(raw_name: str) -> str:
    """Sanitize a template name for safe storage inside ./templates/."""
    cleaned = re.sub(r"\.md$", "", raw_name.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"[^a-zA-Z0-9_\-\s]", "", cleaned).strip()
    cleaned = re.sub(r"\s+", "_", cleaned)
    return cleaned or "Master_Standard_Template"


def convert_pdf_to_structured_markdown(
    pdf_path: Path,
    title_label: str | None = None,
) -> Tuple[str, List[str]]:
    """
    Use `pymupdf4llm.to_markdown(pdf_path, page_chunks=True)` supplemented by PyMuPDF
    table detection to convert a PDF into a clean, page-indexed Markdown (.md) string.
    Returns `(full_markdown, per_page_markdown_list)`.
    """
    chunks: List[Dict[str, Any]] = []
    try:
        chunks = pymupdf4llm.to_markdown(
            str(pdf_path),
            page_chunks=True,
            write_images=False,
        )
    except Exception:
        chunks = []

    doc = fitz.open(str(pdf_path))
    page_count = len(doc)
    per_page_md: List[str] = []

    doc_title = title_label or pdf_path.name
    header_lines = [
        "---",
        "schema: template_audit_master_v2",
        f'source_document: "{doc_title}"',
        f"page_count: {page_count}",
        'unit_system: "SI (kWh, MWh, K, m/s, kN, V)"',
        "math_engine: sympy_deterministic",
        "---",
        "",
        f"# Master Audit Standard — {doc_title}",
        f"> Extracted via `pymupdf4llm` | Pages: {page_count}",
        "",
        "## Audit Checklist & Enforcement Rules",
        "- [x] Enforce all section headings, numbered references, and appendices present in this Master `.md` Base.",
        "- [x] Verify all inline formulas and Markdown table row/column totals deterministically using Python `sympy`.",
        "- [x] Enforce standard SI engineering units (`kWh`, `MWh`, `K`, `m/s`, `kN`, `V`) and technical spelling.",
        "",
        "---",
    ]

    full_sections: List[str] = ["\n".join(header_lines)]

    for idx in range(page_count):
        page_num = idx + 1
        page = doc[idx]
        page_text = ""
        if idx < len(chunks) and isinstance(chunks[idx], dict):
            page_text = (chunks[idx].get("text") or "").strip()

        if not page_text:
            page_text = page.get_text("text").strip()

        # Scanned PDF OCR fallback if embedded text layer is empty
        if not page_text:
            try:
                tp_ocr = page.get_textpage_ocr(flags=0, full=False)
                page_text = page.get_text("text", textpage=tp_ocr).strip()
            except Exception:
                page_text = ""

        # Supplement with PyMuPDF table markdown if table pipes aren't present
        if "|" not in page_text:
            try:
                tabs = page.find_tables()
                if tabs and tabs.tables:
                    extra = [t.to_markdown().strip() for t in tabs.tables if t.to_markdown()]
                    if extra:
                        page_text = page_text + "\n\n" + "\n\n".join(extra)
            except Exception:
                pass

        per_page_md.append(page_text)
        full_sections.append(f"## Page {page_num}\n\n{page_text}\n\n---")

    doc.close()
    return "\n\n".join(full_sections).strip() + "\n", per_page_md


def render_pdf_pages_to_images(
    pdf_path: Path,
    audit_id: str,
    dpi: int = RENDER_DPI,
) -> List[PageRenderOut]:
    """Render each PDF page at `dpi` (default 150 DPI) and return page image descriptors."""
    render_dir = RENDERS_DIR / audit_id
    render_dir.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(str(pdf_path))
    pages_out: List[PageRenderOut] = []

    for idx in range(len(doc)):
        page_num = idx + 1
        page = doc[idx]
        pix = page.get_pixmap(dpi=dpi, alpha=False)
        img_name = f"page_{page_num}.png"
        pix.save(str(render_dir / img_name))

        pages_out.append(
            PageRenderOut(
                page_number=page_num,
                image_url=f"/api/renders/{audit_id}/{img_name}",
                width_pt=round(float(page.rect.width), 2),
                height_pt=round(float(page.rect.height), 2),
                width_px=int(pix.width),
                height_px=int(pix.height),
            )
        )

    doc.close()
    return pages_out


def export_annotated_review_copy(
    pdf_path: Path,
    target_filename: str,
    issues: List[AuditIssueOut],
    ignored_ids: Set[str] | None = None,
) -> Path:
    """
    Create a separate `{stem}_review_copy.pdf` with native PyMuPDF rectangle and
    squiggly annotations (`page.add_rect_annot` and `page.add_squiggly_annot`) for all
    active (non-ignored) issues, leaving the original PDF untouched.
    """
    ignored_set = ignored_ids or set()
    sha_before = compute_sha256(pdf_path)

    doc = fitz.open(str(pdf_path))
    for issue in issues:
        if issue.id in ignored_set:
            continue
        p_idx = issue.page_number - 1
        if p_idx < 0 or p_idx >= len(doc):
            continue
        page = doc[p_idx]
        pw, ph = float(page.rect.width), float(page.rect.height)
        x0 = (issue.left_pct / 100.0) * pw
        y0 = (issue.top_pct / 100.0) * ph
        x1 = x0 + (issue.width_pct / 100.0) * pw
        y1 = y0 + (issue.height_pct / 100.0) * ph
        rect = fitz.Rect(x0, y0, x1, y1)

        if issue.category == "calculation":
            rgb = (0.937, 0.267, 0.267)  # Red #ef4444
        elif issue.category in ("missing_reference", "structure_mismatch"):
            rgb = (0.961, 0.620, 0.043)  # Amber #f59e0b
        else:
            rgb = (0.024, 0.714, 0.831)  # Cyan #06b6d4

        annot = page.add_rect_annot(rect)
        annot.set_colors(stroke=rgb, fill=rgb)
        annot.set_opacity(0.26)
        if issue.category in ("missing_reference", "structure_mismatch"):
            annot.set_border(width=1.5, dashes=[3, 2])
        else:
            annot.set_border(width=1.5)

        popup_text = (
            f"[{issue.category.upper()} | {issue.severity.upper()}] {issue.title}\n"
            f"Issue: {issue.issue_description}\n"
            f"Suggestion to Fix: {issue.suggestion_to_fix}\n"
            f"Why to Ignore: {issue.why_to_ignore}"
        )
        annot.set_info(title="TemplateAudit AI", subject=issue.title, content=popup_text)
        annot.update()

        try:
            sq = page.add_squiggly_annot(rect)
            sq.set_colors(stroke=rgb)
            sq.update()
        except Exception:
            pass

    stem = Path(target_filename).stem
    out_file = EXPORTS_DIR / f"{stem}_review_copy.pdf"
    doc.save(str(out_file), garbage=4, deflate=True)
    doc.close()

    sha_after = compute_sha256(pdf_path)
    if sha_before != sha_after:
        raise RuntimeError("Original PDF integrity check failed!")

    return out_file
