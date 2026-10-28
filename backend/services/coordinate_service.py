"""
Coordinate Lookup Bridge mapping verbatim snippets to normalized PDF bounding boxes,
with Multi-Line Quad/Rect Highlighting and Table-Cell `(row, col)` Disambiguation.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Tuple

import pymupdf as fitz  # PyMuPDF

from backend.schemas import BoundingBoxPct


def _tokenize_words(text: str) -> List[str]:
    return re.findall(r"[a-z0-9.,%/-]+", text.lower())


def rect_to_percentages(
    rect: fitz.Rect,
    page_w: float,
    page_h: float,
) -> Tuple[float, float, float, float]:
    """Convert `[x0, y0, x1, y1]` points to `(left_pct, top_pct, width_pct, height_pct)`."""
    x0 = max(0.0, min(float(rect.x0), page_w))
    y0 = max(0.0, min(float(rect.y0), page_h))
    x1 = max(x0 + 2.0, min(float(rect.x1), page_w))
    y1 = max(y0 + 2.0, min(float(rect.y1), page_h))

    left_pct = round((x0 / page_w) * 100.0, 3) if page_w > 0 else 5.0
    top_pct = round((y0 / page_h) * 100.0, 3) if page_h > 0 else 5.0
    width_pct = round(max(1.2, ((x1 - x0) / page_w) * 100.0), 3) if page_w > 0 else 20.0
    height_pct = round(max(1.2, ((y1 - y0) / page_h) * 100.0), 3) if page_h > 0 else 2.2
    return left_pct, top_pct, width_pct, height_pct


def _rect_to_bbox_model(rect: fitz.Rect, page_w: float, page_h: float) -> BoundingBoxPct:
    l_p, t_p, w_p, h_p = rect_to_percentages(rect, page_w, page_h)
    return BoundingBoxPct(left_pct=l_p, top_pct=t_p, width_pct=w_p, height_pct=h_p)


def _group_contiguous_line_rects(rects: List[fitz.Rect]) -> List[List[fitz.Rect]]:
    """
    When `page.search_for()` returns multiple rects, group rects that belong to a contiguous
    multi-line wrap (adjacent vertical y-coordinates) vs separate occurrences on the page.
    """
    if not rects:
        return []
    groups: List[List[fitz.Rect]] = [[rects[0]]]
    for r in rects[1:]:
        prev = groups[-1][-1]
        # Same line or immediate next wrapped line within 22pt vertically
        if abs(r.y0 - prev.y0) <= 22.0 and r.y0 >= prev.y0 - 4.0:
            groups[-1].append(r)
        else:
            groups.append([r])
    return groups


def _find_matching_table_cell(
    page: fitz.Page,
    snippet: str,
    context_text: str,
) -> Tuple[Optional[fitz.Rect], Optional[str]]:
    """
    Use PyMuPDF's native `page.find_tables()` to disambiguate numbers or text inside table cells.
    Returns `(cell_rect, "Table T · Row R, Col C")` if a matching table cell is found.
    """
    try:
        finder = page.find_tables()
        tables = finder.tables if finder else []
    except Exception:
        tables = []

    if not tables:
        return None, None

    ctx_lower = f"{snippet} {context_text}".lower()
    ctx_tokens = _tokenize_words(ctx_lower)
    snip_nums = re.findall(r"\d+(?:\.\d+)?", snippet)

    best_rect: Optional[fitz.Rect] = None
    best_ref: Optional[str] = None
    best_score = 0.0

    for t_idx, tbl in enumerate(tables):
        try:
            extracted = tbl.extract()
            cells_grid = tbl.rows
        except Exception:
            continue

        for r_idx, row_cells in enumerate(extracted):
            row_text = " ".join(str(c or "") for c in row_cells).lower()
            row_overlap = sum(1 for tok in ctx_tokens if tok in row_text)
            for c_idx, cell_val in enumerate(row_cells):
                cell_str = str(cell_val or "").strip()
                if not cell_str:
                    continue
                score = 0.0
                if snippet.lower() in cell_str.lower() or cell_str.lower() in snippet.lower():
                    score += 4.0
                for num in snip_nums:
                    if num in cell_str:
                        score += 5.0
                # Also reward column header match
                if len(extracted) > 0 and c_idx < len(extracted[0]):
                    col_hdr = str(extracted[0][c_idx] or "").lower()
                    score += sum(1.5 for tok in ctx_tokens if tok in col_hdr)
                score += row_overlap * 1.2

                if score > best_score and score >= 6.0:
                    try:
                        cell_bbox = cells_grid[r_idx].cells[c_idx]
                        if cell_bbox:
                            best_score = score
                            best_rect = fitz.Rect(cell_bbox)
                            best_ref = f"Table {t_idx + 1} · Row {r_idx + 1}, Col {c_idx + 1}"
                    except Exception:
                        continue

    return best_rect, best_ref


def _pick_best_rect_group_by_context(
    page: fitz.Page,
    rects: List[fitz.Rect],
    context_text: str,
) -> List[fitz.Rect]:
    """Pick the single or multi-line rect group whose surrounding row/block best matches context."""
    groups = _group_contiguous_line_rects(rects)
    if not groups:
        return []
    if len(groups) == 1:
        return groups[0]

    ctx_tokens = _tokenize_words(context_text)
    best_group = groups[0]
    best_score = -1.0
    for grp in groups:
        union_r = grp[0]
        for r in grp[1:]:
            union_r = union_r | r
        band = fitz.Rect(
            0,
            max(0, union_r.y0 - 12),
            page.rect.width,
            min(page.rect.height, union_r.y1 + 12),
        )
        row_txt = page.get_text("text", clip=band).lower()
        score = sum(1 for t in ctx_tokens if t in row_txt)
        if score > best_score:
            best_score = score
            best_group = grp
    return best_group


def _find_nearest_heading_or_block_rect(
    page: fitz.Page,
    snippet: str,
    title: str,
) -> Tuple[fitz.Rect, str]:
    """
    Fallback when exact snippet is not found (e.g., a completely missing section):
    1. Try matching the closest line/block on the page.
    2. Otherwise anchor the bounding box to the nearest section heading on that page.
    """
    target_str = f"{snippet} {title}".lower()
    target_tokens = _tokenize_words(target_str)

    best_line_rect: Optional[fitz.Rect] = None
    best_score = 0.0
    heading_rects: List[fitz.Rect] = []

    try:
        page_dict = page.get_text("dict")
        for block in page_dict.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                spans = line.get("spans", [])
                line_text = " ".join(s.get("text", "") for s in spans).strip()
                if not line_text:
                    continue
                bbox = line.get("bbox")
                if not bbox or len(bbox) != 4:
                    continue
                r = fitz.Rect(bbox)

                max_size = max((float(s.get("size", 9.5)) for s in spans), default=9.5)
                if max_size >= 11.0 or re.match(
                    r"^(?:\d+\.\s+|Appendix\s+[A-Z]|References\b)", line_text
                ):
                    heading_rects.append(r)

                line_lower = line_text.lower()
                overlap = sum(1 for t in target_tokens if t in line_lower) / max(
                    1, len(target_tokens)
                )
                seq = SequenceMatcher(None, snippet.lower(), line_lower).ratio()
                score = overlap * 0.7 + seq * 0.3
                if score > best_score:
                    best_score = score
                    best_line_rect = r
    except Exception:
        pass

    if best_line_rect is not None and best_score >= 0.32:
        return best_line_rect, "closest_block_fallback"

    if heading_rects:
        return heading_rects[0], "nearest_heading_fallback"

    return fitz.Rect(45, 45, page.rect.width - 45, 75), "page_header_fallback"


def locate_issue_detailed_on_pdf_page(
    page: fitz.Page,
    raw_issue: Dict[str, Any],
) -> Tuple[float, float, float, float, List[BoundingBoxPct], Optional[str], str]:
    """
    Enhanced coordinate resolver returning:
    `(left_pct, top_pct, width_pct, height_pct, bboxes, table_cell_ref, match_method)`
    Supports multi-line wrapped text boxes and PyMuPDF `page.find_tables()` cell disambiguation.
    """
    pw = float(page.rect.width)
    ph = float(page.rect.height)
    snippet = str(raw_issue.get("verbatim_snippet") or "").strip()
    clean_snip = re.sub(r"\*\*|[`_#]+", " ", snippet)
    clean_snip = re.sub(r"\s+", " ", clean_snip).strip()
    context_str = (
        f"{clean_snip} {raw_issue.get('title', '')} "
        f"{raw_issue.get('issue_description', '')} {raw_issue.get('stated_expression', '')}"
    )

    # Check if the issue lies inside a native PDF table cell first
    table_rect, table_ref = _find_matching_table_cell(page, clean_snip, context_str)

    # 1. Direct `page.search_for(issue["verbatim_snippet"])`
    if snippet:
        hits = page.search_for(snippet)
        if hits:
            if table_rect is not None:
                cell_hits = [h for h in hits if h.intersects(table_rect)]
                if cell_hits:
                    chosen_grp = cell_hits
                    union_r = chosen_grp[0]
                    for r in chosen_grp[1:]:
                        union_r = union_r | r
                    l_p, t_p, w_p, h_p = rect_to_percentages(union_r, pw, ph)
                    bboxes = [_rect_to_bbox_model(r, pw, ph) for r in chosen_grp]
                    return l_p, t_p, w_p, h_p, bboxes, table_ref, "exact_table_cell"

            chosen_grp = _pick_best_rect_group_by_context(page, hits, context_str)
            union_r = chosen_grp[0]
            for r in chosen_grp[1:]:
                union_r = union_r | r
            l_p, t_p, w_p, h_p = rect_to_percentages(union_r, pw, ph)
            bboxes = [_rect_to_bbox_model(r, pw, ph) for r in chosen_grp]
            return l_p, t_p, w_p, h_p, bboxes, table_ref, "exact"

    # 2. Cleaned snippet search
    if clean_snip and clean_snip != snippet:
        hits = page.search_for(clean_snip)
        if hits:
            chosen_grp = _pick_best_rect_group_by_context(page, hits, context_str)
            union_r = chosen_grp[0]
            for r in chosen_grp[1:]:
                union_r = union_r | r
            l_p, t_p, w_p, h_p = rect_to_percentages(union_r, pw, ph)
            bboxes = [_rect_to_bbox_model(r, pw, ph) for r in chosen_grp]
            return l_p, t_p, w_p, h_p, bboxes, table_ref, "normalized"

    # 3. Table cell direct match if table_rect was resolved with high confidence
    if table_rect is not None:
        l_p, t_p, w_p, h_p = rect_to_percentages(table_rect, pw, ph)
        bboxes = [_rect_to_bbox_model(table_rect, pw, ph)]
        return l_p, t_p, w_p, h_p, bboxes, table_ref, "table_cell_box"

    # 4. Sub-phrase / numeric result search
    words = clean_snip.split()
    for win_size in (min(5, len(words)), 4, 3, 2):
        if len(words) < win_size:
            continue
        for candidate in (" ".join(words[:win_size]), " ".join(words[-win_size:])):
            if len(candidate) < 3:
                continue
            hits = page.search_for(candidate)
            if hits:
                chosen_grp = _pick_best_rect_group_by_context(page, hits, context_str)
                union_r = chosen_grp[0]
                for r in chosen_grp[1:]:
                    union_r = union_r | r
                l_p, t_p, w_p, h_p = rect_to_percentages(union_r, pw, ph)
                bboxes = [_rect_to_bbox_model(r, pw, ph) for r in chosen_grp]
                return l_p, t_p, w_p, h_p, bboxes, table_ref, "partial_match"

    # 5. Fallback: Closest line/block or Nearest Heading on that page
    fb_rect, method = _find_nearest_heading_or_block_rect(
        page, clean_snip, str(raw_issue.get("title") or "")
    )
    l_p, t_p, w_p, h_p = rect_to_percentages(fb_rect, pw, ph)
    bboxes = [_rect_to_bbox_model(fb_rect, pw, ph)]
    return l_p, t_p, w_p, h_p, bboxes, table_ref, method


def locate_issue_on_pdf_page(
    page: fitz.Page,
    raw_issue: Dict[str, Any],
) -> Tuple[float, float, float, float, str]:
    """
    Backward-compatible coordinate lookup wrapper returning
    `(left_pct, top_pct, width_pct, height_pct, match_method)`.
    """
    l_p, t_p, w_p, h_p, _bboxes, _tbl_ref, method = locate_issue_detailed_on_pdf_page(
        page, raw_issue
    )
    return l_p, t_p, w_p, h_p, method
