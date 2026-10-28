"""Pydantic v2 request and response schemas for TemplateAudit AI."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field

from backend.config import DEFAULT_OLLAMA_MODEL, OLLAMA_CHAT_URL


IssueCategory = Literal["calculation", "missing_reference", "structure_mismatch", "typo"]
IssueSeverity = Literal["critical", "warning", "info"]


class OllamaStatusResponse(BaseModel):
    """Status of the local Ollama server and installed models."""

    connected: bool
    available_models: List[str] = Field(default_factory=list)
    recommended_model: str = DEFAULT_OLLAMA_MODEL
    error: Optional[str] = None


class ExtractPdfResponse(BaseModel):
    """Response returned when converting a Perfect/Reference PDF into a Master .MD Base."""

    filename: str
    suggested_name: str
    page_count: int
    markdown: str


class AIAssistRequest(BaseModel):
    """Request payload for AI-assisted rule injection into a Master .MD Base."""

    markdown: str = Field(..., description="Current Markdown (.md) content in the editor")
    instruction: str = Field(..., description="User instruction describing rules or edits to inject")
    ollama_model: str = Field(default=DEFAULT_OLLAMA_MODEL)
    ollama_url: str = Field(default=OLLAMA_CHAT_URL)


class DiffLineItem(BaseModel):
    """Single line entry in a before/after Markdown diff."""

    type: Literal["added", "removed", "unchanged"]
    content: str
    line_num: Optional[int] = None


class AIAssistResponse(BaseModel):
    """Response payload containing the updated Master .MD Base content and diff lines."""

    markdown: str
    previous_markdown: str = ""
    engine_used: str
    summary: str
    diff_lines: List[DiffLineItem] = Field(default_factory=list)


class SaveTemplateRequest(BaseModel):
    """Request payload for saving a Master .MD Base to ./templates/{name}.md."""

    name: str = Field(..., description="Template name to save under ./templates/{name}.md")
    markdown: str = Field(..., description="Full Markdown content to save")


class TemplateItem(BaseModel):
    """Metadata and content of a saved Master .MD Base."""

    name: str
    filename: str
    markdown: str
    size_bytes: int
    updated_at: str


class TemplateListResponse(BaseModel):
    """List of all saved Master .MD Base files in ./templates/."""

    templates: List[TemplateItem]


class BoundingBoxPct(BaseModel):
    """Normalized percentage bounding box `[0..100]` on a rendered PDF page."""

    left_pct: float
    top_pct: float
    width_pct: float
    height_pct: float


class AuditIssueOut(BaseModel):
    """
    A single audit issue found when comparing the Target PDF against the Master .MD Base,
    complete with Dual Reasoning (`suggestion_to_fix` and `why_to_ignore`), multi-line
    normalized bounding boxes (`bboxes`), table-cell coordinate tags, and Master .MD rule context.
    """

    id: str
    page_number: int = Field(..., ge=1)
    category: IssueCategory
    severity: IssueSeverity
    title: str
    verbatim_snippet: str
    issue_description: str
    suggestion_to_fix: str
    why_to_ignore: str
    stated_expression: Optional[str] = None
    stated_result: Optional[str] = None
    true_result: Optional[str] = None
    discrepancy: Optional[str] = None
    left_pct: float
    top_pct: float
    width_pct: float
    height_pct: float
    bboxes: List[BoundingBoxPct] = Field(default_factory=list)
    table_cell_ref: Optional[str] = None
    master_rule_ref: Optional[str] = None
    match_method: str = "exact"
    source_engine: str = "ollama+sympy"


class PageRenderOut(BaseModel):
    """Metadata and image URL for a rendered Target PDF page."""

    page_number: int
    image_url: str
    width_pt: float
    height_pt: float
    width_px: int
    height_px: int


class SymbolEntryOut(BaseModel):
    """Named engineering parameter extracted into the cross-page symbol registry."""

    symbol: str
    label: str
    value: float
    unit: str
    page_number: int


class AuditRunResponse(BaseModel):
    """Full response returned by POST /api/audit/run."""

    audit_id: str
    target_filename: str
    template_name: str
    ollama_model: str
    ollama_connected: bool
    original_sha256: str
    integrity_preserved: bool
    duration_seconds: float
    pages: List[PageRenderOut]
    issues: List[AuditIssueOut]
    symbol_registry: List[SymbolEntryOut] = Field(default_factory=list)


# In-memory registry of completed audit runs for annotated PDF copy export
AUDIT_SESSION_STORE: Dict[str, Dict[str, Any]] = {}
