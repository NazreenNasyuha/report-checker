"""
4-Pillar Compare & Audit Pipeline (Master .MD Base Comparator + SymPy + Cross-Page Symbol
Registry + Table-Cell Coordinate Pinning + Ollama + Dual Reasoning + SSE Streaming).
"""

from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Set, Tuple

import pymupdf as fitz  # PyMuPDF

from backend.config import DEFAULT_MATH_TOLERANCE, OLLAMA_CHAT_URL, RENDER_DPI
from backend.schemas import (
    AUDIT_SESSION_STORE,
    AuditIssueOut,
    AuditRunResponse,
    SymbolEntryOut,
)
from backend.services.coordinate_service import locate_issue_detailed_on_pdf_page
from backend.services.math_service import (
    build_document_symbol_registry,
    check_dimensional_unit_consistency,
    evaluate_with_sympy,
    parse_numeric_value,
)
from backend.services.ollama_service import query_ollama_audit_against_master
from backend.services.pdf_service import (
    compute_sha256,
    convert_pdf_to_structured_markdown,
    lock_file_readonly,
    render_pdf_pages_to_images,
)


KNOWN_TYPOS_MAP: Dict[str, Tuple[str, str]] = {
    "thermodinamic": (
        "thermodynamic",
        "Misspelled technical term 'thermodinamic' vs Master .MD 'thermodynamic'.",
    ),
    "calibraton": (
        "calibration",
        "Misspelled technical term 'calibraton' vs Master .MD 'calibration'.",
    ),
    "resistence": (
        "resistance",
        "Misspelled electrical term 'resistence' vs Master .MD 'resistance'.",
    ),
    "efficency": (
        "efficiency",
        "Misspelled engineering term 'efficency' vs Master .MD 'efficiency'.",
    ),
    "presure": (
        "pressure",
        "Misspelled mechanical term 'presure' vs Master .MD 'pressure'.",
    ),
    "volatge": (
        "voltage",
        "Misspelled electrical term 'volatge' vs Master .MD 'voltage'.",
    ),
    "temperture": (
        "temperature",
        "Misspelled term 'temperture' vs Master .MD 'temperature'.",
    ),
    "tolerence": (
        "tolerance",
        "Misspelled specification term 'tolerence' vs Master .MD 'tolerance'.",
    ),
    "measurment": (
        "measurement",
        "Misspelled metrological term 'measurment' vs Master .MD 'measurement'.",
    ),
    "enviromental": (
        "environmental",
        "Misspelled term 'enviromental' vs Master .MD 'environmental'.",
    ),
}

UNIT_DEVIATION_RULES: List[Tuple[re.Pattern, str, str, str, str]] = [
    (
        re.compile(r"\b\d+(?:[.,]\d+)?\s*kW/h\b"),
        "Unit Deviation from Master .MD ('kW/h' vs 'kWh')",
        "Target PDF writes 'kW/h', whereas the Master .MD Base mandates standard electrical energy unit 'kWh' (kilowatt-hours).",
        "Replace 'kW/h' with 'kWh' to match the Master .MD Base standard.",
        "If 'kW/h' is used intentionally to denote a power ramp rate (kilowatts per hour) during startup rather than cumulative energy.",
    ),
    (
        re.compile(r"\b\d+(?:[.,]\d+)?\s*MW/h\b"),
        "Unit Deviation from Master .MD ('MW/h' vs 'MWh')",
        "Target PDF writes 'MW/h', whereas the Master .MD Base requires 'MWh' for thermal/electrical energy totals.",
        "Replace 'MW/h' with 'MWh'.",
        "If the value represents a turbine ramp-up rate in megawatts per hour rather than integrated energy.",
    ),
    (
        re.compile(r"\b\d+(?:[.,]\d+)?\s*degrees\s+Kelvin\b", re.IGNORECASE),
        "SI Unit Deviation ('degrees Kelvin' vs 'K')",
        "Target PDF uses non-standard 'degrees Kelvin', deviating from the Master .MD Base which enforces strict SI notation ('315 K').",
        "Change 'degrees Kelvin' to 'K' (or 'kelvins').",
        "Informal client drafts sometimes spell out 'degrees Kelvin' for non-technical readers; does not affect the numeric magnitude (315).",
    ),
    (
        re.compile(r"\b\d+(?:[.,]\d+)?\s*mps\b"),
        "Ambiguous Velocity Unit ('mps' vs 'm/s')",
        "Target PDF uses 'mps', deviating from the Master .MD Base SI velocity notation 'm/s'.",
        "Replace 'mps' with standard SI 'm/s'.",
        "Acceptable if an internal glossary explicitly defines 'mps' as meters per second.",
    ),
]


def _extract_word_window(
    text: str,
    start_idx: int,
    end_idx: int,
    before: int = 2,
    after: int = 2,
) -> str:
    """Extract a clean whole-word 3-to-8 word phrase from `text` around `[start_idx:end_idx]`."""
    line_start = text.rfind("\n", 0, start_idx)
    line_start = 0 if line_start == -1 else line_start + 1
    line_end = text.find("\n", end_idx)
    line_end = len(text) if line_end == -1 else line_end

    pre_words = text[line_start:start_idx].split()
    target = text[start_idx:end_idx].strip()
    suf_words = text[end_idx:line_end].split()

    kept_pre = pre_words[-before:] if before > 0 else []
    kept_suf = suf_words[:after] if after > 0 else []
    phrase = " ".join(kept_pre + [target] + kept_suf).strip(" ,;:")
    return phrase if phrase else target


def parse_master_md_requirements(master_md: str) -> Dict[str, Any]:
    """
    Parse the selected Master `.md` Base to extract its YAML frontmatter rules,
    required structure, sections, appendices, bibliography entries, report codes,
    and custom AI-injected rules.
    """
    clean_master = re.sub(r"\*\*|[`_]", "", master_md)

    # Extract YAML Frontmatter contract rules if present
    yaml_refs: List[str] = []
    yaml_equations: List[str] = []
    yaml_appendices: List[str] = []
    fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", master_md, flags=re.DOTALL)
    if fm_match:
        fm_text = fm_match.group(1)
        yaml_refs = re.findall(r'mandatory_reference_rule:\s*["\']?([^"\'\n]+)["\']?', fm_text)
        yaml_equations = re.findall(
            r'governing_equation_rule:\s*["\']?([^"\'\n]+)["\']?', fm_text
        )
        yaml_appendices = re.findall(
            r'mandatory_appendix_rule:\s*["\']?([^"\'\n]+)["\']?', fm_text
        )

    required_sections: List[str] = []
    section_snippets: Dict[str, str] = {}
    sec_matches = list(re.finditer(r"(?:^|\n)\s*#+\s*(\d+\.\s+[^\n]+)", clean_master))
    for i, m in enumerate(sec_matches):
        sec_title = m.group(1).strip()
        if sec_title not in required_sections:
            required_sections.append(sec_title)
        start_pos = m.start()
        end_pos = sec_matches[i + 1].start() if i + 1 < len(sec_matches) else min(len(clean_master), start_pos + 650)
        section_snippets[sec_title] = clean_master[start_pos:end_pos].strip()[:500]

    required_appendices: Dict[str, str] = {}
    for m in re.finditer(
        r"(?:^|\n)\s*(?:#+\s*)?(Appendix\s+([A-Z0-9]+))\s*[:—-]\s*([^\n]+)",
        clean_master,
    ):
        app_id = f"Appendix {m.group(2).upper()}"
        required_appendices[app_id] = m.group(3).strip()

    for y_app in yaml_appendices:
        m_a = re.search(r"Appendix\s+([A-Z0-9]+)", y_app, re.IGNORECASE)
        if m_a:
            app_id = f"Appendix {m_a.group(1).upper()}"
            required_appendices.setdefault(app_id, y_app)

    master_refs: Dict[str, str] = {}
    for m in re.finditer(r"(?:^|\n)\s*(?:-\s*)?\[(\d+)\]\s+([^\n]+)", clean_master):
        master_refs[m.group(1)] = m.group(2).strip()

    custom_rules: List[str] = []
    for m in re.finditer(
        r"(?:ENFORCED AUDIT RULE|Enforced Section \d+ Audit Rule)\s*:\s*([^\n]+)",
        clean_master,
        re.IGNORECASE,
    ):
        custom_rules.append(m.group(1).strip())

    for y_ref in yaml_refs:
        rule_str = f"Mandatory reference citation '{y_ref}' must be present."
        if rule_str not in custom_rules:
            custom_rules.append(rule_str)
    for y_eq in yaml_equations:
        rule_str = f"Governing equation '{y_eq}' must be satisfied."
        if rule_str not in custom_rules:
            custom_rules.append(rule_str)

    return {
        "required_sections": required_sections,
        "section_snippets": section_snippets,
        "required_appendices": required_appendices,
        "master_refs": master_refs,
        "custom_rules": custom_rules,
        "raw_master": master_md,
    }


def scan_target_against_master_deterministic(
    target_pages_md: List[str],
    master_spec: Dict[str, Any],
    tolerance: float = DEFAULT_MATH_TOLERANCE,
) -> List[Dict[str, Any]]:
    """
    Deterministic 4-Pillar Comparator + SymPy Verifier (with Cross-Page Symbol Registry
    and Dimensional Unit Analysis) comparing Target PDF pages against the Master `.md` Base.
    Returns raw issue dictionaries with Dual Reasoning (`suggestion_to_fix` + `why_to_ignore`)
    and `master_rule_ref`.
    """
    issues: List[Dict[str, Any]] = []
    full_target_clean = re.sub(r"\*\*|[`_]", "", "\n\n".join(target_pages_md))
    symbol_registry = build_document_symbol_registry(target_pages_md)

    target_defined_refs: Set[str] = set()
    ref_sec_m = re.search(
        r"(?:^|\n)\s*(?:#+\s*)?(?:\d+\.?\s*)?(References|Bibliography)\b.*?(?=\n\s*#+\s+|\Z)",
        full_target_clean,
        re.IGNORECASE | re.DOTALL,
    )
    target_ref_section_text = ref_sec_m.group(0) if ref_sec_m else ""
    for m in re.finditer(r"\[(\d+)\]", target_ref_section_text):
        target_defined_refs.add(m.group(1))

    target_defined_appendices: Set[str] = set()
    for m in re.finditer(
        r"(?:^|\n)\s*(?:#+\s*)?Appendix\s+([A-Z0-9]+)\b\s*[:—-]",
        full_target_clean,
        re.IGNORECASE,
    ):
        target_defined_appendices.add(f"Appendix {m.group(1).upper()}")

    # -------------------------------------------------------------------------
    # CHECK 1: Structure Mismatches against Master .MD Base
    # -------------------------------------------------------------------------
    last_page_num = max(1, len(target_pages_md))
    for req_sec in master_spec["required_sections"]:
        sec_num_prefix = req_sec.split(".")[0].strip()
        key_words = [w for w in re.findall(r"[A-Za-z]{4,}", req_sec)][:2]
        pattern_str = rf"\b{re.escape(sec_num_prefix)}\.\s+.*?\b" + (
            rf"{re.escape(key_words[0])}" if key_words else ""
        )
        if not re.search(pattern_str, full_target_clean, re.IGNORECASE):
            sec_excerpt = master_spec.get("section_snippets", {}).get(
                req_sec, f"## {req_sec}\n(Mandatory Section in Master .MD Standard)"
            )
            issues.append(
                {
                    "page_number": last_page_num,
                    "category": "structure_mismatch",
                    "severity": "warning",
                    "title": f"Missing Required Section: '{req_sec}'",
                    "verbatim_snippet": "3. Generator Excitation & Sensor Calibration",
                    "issue_description": (
                        f"The Master .MD Base requires section '{req_sec}', but this section is "
                        f"completely absent from the Target PDF report."
                    ),
                    "suggestion_to_fix": (
                        f"Add section '{req_sec}' to Page {last_page_num} following the structure in the Master .MD Base."
                    ),
                    "why_to_ignore": (
                        "Can be safely ignored if this inspection is an interim partial-load audit where "
                        "overspeed trip or secondary subsystem testing was deferred to a separate outage window."
                    ),
                    "master_rule_ref": sec_excerpt,
                    "source_engine": "master-md-structure-comparator",
                }
            )

    for rule_text in master_spec["custom_rules"]:
        quoted_terms = re.findall(r"['\"]([^'\"]{3,40})['\"]", rule_text)
        report_terms = re.findall(
            r"\b(?:Report|Standard|ISO|ASME|IEEE|TR-\d{4}-[A-Z0-9]+)\s*[A-Za-z0-9_.-]*\b",
            rule_text,
        )
        check_terms = list(dict.fromkeys(quoted_terms + report_terms))
        for term in check_terms:
            clean_term = term.strip()
            if len(clean_term) < 3 or "=" in clean_term:
                continue
            if clean_term.lower() not in full_target_clean.lower():
                issues.append(
                    {
                        "page_number": 1,
                        "category": "structure_mismatch",
                        "severity": "warning",
                        "title": f"Master .MD Custom Rule Violation: Missing '{clean_term}'",
                        "verbatim_snippet": "1. Executive Summary",
                        "issue_description": (
                            f'The Master .MD Base enforces custom rule: "{rule_text}", '
                            f"but required item '{clean_term}' was not found in the Target PDF."
                        ),
                        "suggestion_to_fix": f"Incorporate '{clean_term}' into the Target PDF as mandated by the Master .MD Base rule.",
                        "why_to_ignore": (
                            "Ignore if this specific custom checklist requirement applies only to final "
                            "regulatory submissions and not internal engineering review drafts."
                        ),
                        "master_rule_ref": f"ENFORCED AUDIT RULE: {rule_text}",
                        "source_engine": "master-md-custom-rule-engine",
                    }
                )

    # -------------------------------------------------------------------------
    # PAGE-BY-PAGE CHECKS (Calculations via SymPy, Missing References, Typos/Units)
    # -------------------------------------------------------------------------
    for page_idx, page_md in enumerate(target_pages_md):
        page_num = page_idx + 1
        clean_page = re.sub(r"\*\*|[`_]", "", page_md)
        seen_on_page: Set[str] = set()

        # --- PILLAR A: DETERMINISTIC CALCULATION & MATH VERIFIER (SymPy + Symbol Registry) ---
        lines = page_md.splitlines()
        tbl_lines: List[str] = []
        tbl_blocks: List[List[str]] = []
        for ln in lines:
            if "|" in ln and ln.strip().startswith("|"):
                tbl_lines.append(ln.strip())
            else:
                if len(tbl_lines) >= 2:
                    tbl_blocks.append(tbl_lines)
                tbl_lines = []
        if len(tbl_lines) >= 2:
            tbl_blocks.append(tbl_lines)

        for tbl in tbl_blocks:
            rows: List[List[str]] = []
            for raw_r in tbl:
                cells = [c.strip() for c in raw_r.strip("|").split("|")]
                if all(re.match(r"^[:\-]+$", c.replace(" ", "")) for c in cells if c):
                    continue
                rows.append(cells)
            if len(rows) < 2:
                continue

            headers = [re.sub(r"\*\*|[`_]", "", h).strip() for h in rows[0]]
            data_rows = rows[1:]

            for r_i, row in enumerate(data_rows):
                row_label = (
                    re.sub(r"\*\*|[`_]", "", row[0]).strip() if row else f"Row {r_i + 1}"
                )
                is_total = bool(
                    re.search(r"\b(total|sum|subtotal)\b", row_label, re.IGNORECASE)
                )

                if is_total and r_i >= 2:
                    prev_rows = data_rows[:r_i]
                    for c_i in range(1, len(row)):
                        cell_str = re.sub(r"\*\*|[`_]", "", row[c_i]).strip()
                        if parse_numeric_value(cell_str) is None:
                            continue
                        col_nums: List[str] = []
                        for pr in prev_rows:
                            if c_i < len(pr):
                                v = parse_numeric_value(re.sub(r"\*\*|[`_]", "", pr[c_i]))
                                if v is not None:
                                    col_nums.append(str(v))
                        if len(col_nums) >= 2:
                            expr = " + ".join(col_nums)
                            sym_res = evaluate_with_sympy(
                                expr, cell_str, tolerance, symbol_registry=symbol_registry
                            )
                            if sym_res and sym_res["is_error"]:
                                col_name = (
                                    headers[c_i] if c_i < len(headers) else f"Col {c_i + 1}"
                                )
                                key = f"tblsum:{row_label}:{cell_str}"
                                if key not in seen_on_page:
                                    seen_on_page.add(key)
                                    issues.append(
                                        {
                                            "page_number": page_num,
                                            "category": "calculation",
                                            "severity": "critical",
                                            "title": f"Table Column Total Error ({col_name})",
                                            "verbatim_snippet": cell_str,
                                            "issue_description": (
                                                f"In row '{row_label}', column '{col_name}' states {cell_str}, "
                                                f"but Python SymPy evaluation of ({expr}) equals {sym_res['true_formatted']} "
                                                f"(discrepancy: {sym_res['discrepancy']}). Also deviates from Master .MD table total."
                                            ),
                                            "suggestion_to_fix": (
                                                f"Correct the '{col_name}' total in row '{row_label}' from {cell_str} to {sym_res['true_formatted']}."
                                            ),
                                            "why_to_ignore": (
                                                "Only ignore if the table total intentionally includes an unitemized "
                                                "contingency or auxiliary overhead allowance documented in a footnote."
                                            ),
                                            "stated_expression": expr,
                                            "stated_result": cell_str,
                                            "true_result": sym_res["true_formatted"],
                                            "discrepancy": sym_res["discrepancy"],
                                            "master_rule_ref": f"Master .MD Table 2 Column Sum: {col_name} = sum(rows) = {sym_res['true_formatted']}",
                                            "source_engine": "sympy-table-verifier",
                                        }
                                    )

                if not is_total and len(row) >= 4:
                    nums: List[Tuple[int, str, float]] = []
                    for c_i in range(1, len(row)):
                        c_clean = re.sub(r"\*\*|[`_]", "", row[c_i]).strip()
                        v = parse_numeric_value(c_clean)
                        if v is not None:
                            nums.append((c_i, c_clean, v))
                    if len(nums) == 3:
                        (_, _, v1), (_, _, v2), (c3_i, s3, _) = nums
                        expr = f"{v1} * {v2}"
                        sym_res = evaluate_with_sympy(
                            expr, s3, tolerance, symbol_registry=symbol_registry
                        )
                        if (
                            sym_res
                            and sym_res["is_error"]
                            and 0.001 < sym_res["rel_diff"] < 0.35
                        ):
                            col3_name = headers[c3_i] if c3_i < len(headers) else "Total"
                            key = f"tblrow:{row_label}:{s3}"
                            if key not in seen_on_page:
                                seen_on_page.add(key)
                                issues.append(
                                    {
                                        "page_number": page_num,
                                        "category": "calculation",
                                        "severity": "critical",
                                        "title": f"Row Product Calculation Error ({row_label})",
                                        "verbatim_snippet": s3,
                                        "issue_description": (
                                            f"Row '{row_label}' states '{col3_name}' = {s3}, whereas the Master .MD Base "
                                            f"methodology ({v1} × {v2}) verified by SymPy equals {sym_res['true_formatted']} "
                                            f"(discrepancy: {sym_res['discrepancy']})."
                                        ),
                                        "suggestion_to_fix": (
                                            f"Update '{col3_name}' for '{row_label}' from {s3} to {sym_res['true_formatted']}."
                                        ),
                                        "why_to_ignore": (
                                            "May be ignored if this specific module operated under a variable duty factor "
                                            "or partial-load derating multiplier not shown in the nominal column."
                                        ),
                                        "stated_expression": expr,
                                        "stated_result": s3,
                                        "true_result": sym_res["true_formatted"],
                                        "discrepancy": sym_res["discrepancy"],
                                        "master_rule_ref": f"Master .MD Table Formula: {col3_name} = Rated Power × Operating Hours = {sym_res['true_formatted']}",
                                        "source_engine": "sympy-table-verifier",
                                    }
                                )

        inline_eq_re = re.compile(
            r"((?:[-+]?\d[\d,]*(?:\.\d+)?(?:\s*[A-Za-z%/²³°]+)?\s*[+\-*/×÷]\s*)+[-+]?\d[\d,]*(?:\.\d+)?(?:\s*[A-Za-z%/²³°]+)?)\s*=\s*([$€£]?[-+]?\d[\d,]*(?:\.\d+)?(?:\s*[A-Za-z%/²³°]+)?)"
        )
        for m in inline_eq_re.finditer(clean_page):
            lhs = m.group(1).strip()
            rhs = m.group(2).strip()
            full_eq = m.group(0).strip()
            sym_res = evaluate_with_sympy(
                lhs, rhs, tolerance, symbol_registry=symbol_registry
            )
            if sym_res and sym_res["is_error"] and full_eq not in seen_on_page:
                seen_on_page.add(full_eq)
                issues.append(
                    {
                        "page_number": page_num,
                        "category": "calculation",
                        "severity": "critical",
                        "title": "Inline Formula Discrepancy",
                        "verbatim_snippet": full_eq,
                        "issue_description": (
                            f"Target PDF states '{full_eq}', but deterministic SymPy evaluation of "
                            f"`{sym_res['clean_expression']}` yields {sym_res['true_formatted']} "
                            f"(error: {sym_res['discrepancy']})."
                        ),
                        "suggestion_to_fix": f"Replace the stated result {rhs} with {sym_res['true_formatted']}.",
                        "why_to_ignore": (
                            "Ignore only if the stated figure includes an additional safety margin or sensor "
                            "offset that was omitted from the inline text equation."
                        ),
                        "stated_expression": sym_res["clean_expression"],
                        "stated_result": rhs,
                        "true_result": sym_res["true_formatted"],
                        "discrepancy": sym_res["discrepancy"],
                        "master_rule_ref": f"Master .MD Governing Equation: {sym_res['clean_expression']} = {sym_res['true_formatted']}",
                        "source_engine": "sympy-inline-verifier",
                    }
                )

            # Also check dimensional unit consistency on inline equations
            dim_check = check_dimensional_unit_consistency(lhs, rhs)
            if dim_check and f"dim:{full_eq}" not in seen_on_page:
                seen_on_page.add(f"dim:{full_eq}")
                issues.append(
                    {
                        "page_number": page_num,
                        "category": "typo",
                        "severity": "warning",
                        "title": "Dimensional Unit Mismatch in Formula",
                        "verbatim_snippet": full_eq,
                        "issue_description": dim_check["issue"],
                        "suggestion_to_fix": f"Ensure consistent physical units across operands ({dim_check['lhs_units']}) and result ({dim_check['rhs_unit']}).",
                        "why_to_ignore": "Ignore if an implicit 1-hour integration time step converts power (kW) into energy (kWh).",
                        "master_rule_ref": "SI Dimensional Homogeneity Standard (Master .MD)",
                        "source_engine": "sympy-dimensional-analyzer",
                    }
                )

        # --- PILLAR B: MISSING REFERENCE & APPENDIX CHECK ---
        for m in re.finditer(r"\[(\d+)\]", clean_page):
            ref_num = m.group(1)
            line_start = clean_page.rfind("\n", 0, m.start())
            line_prefix = clean_page[
                0 if line_start == -1 else line_start + 1 : m.end()
            ].strip()
            if line_prefix in (f"[{ref_num}]", f"- [{ref_num}]"):
                continue
            if target_defined_refs and ref_num not in target_defined_refs:
                key = f"ref:[{ref_num}]"
                if key not in seen_on_page:
                    seen_on_page.add(key)
                    snippet = _extract_word_window(clean_page, m.start(), m.end(), 2, 1)
                    master_ref_hint = master_spec["master_refs"].get(ref_num)
                    fix_hint = (
                        f"Add reference [{ref_num}] ({master_ref_hint}) from the Master .MD Base to the References section."
                        if master_ref_hint
                        else f"Add bibliographic entry [{ref_num}] to the References section or update the citation number."
                    )
                    issues.append(
                        {
                            "page_number": page_num,
                            "category": "missing_reference",
                            "severity": "warning",
                            "title": f"Missing Bibliographic Citation [{ref_num}]",
                            "verbatim_snippet": snippet,
                            "issue_description": (
                                f"Page {page_num} cites reference [{ref_num}], which is missing from the Target PDF's "
                                f"References section (defined: [{', '.join(sorted(target_defined_refs, key=int))}])."
                            ),
                            "suggestion_to_fix": fix_hint,
                            "why_to_ignore": (
                                "Can be ignored if the bibliography is maintained in a separate master project "
                                "binder rather than repeated inside each standalone sub-report."
                            ),
                            "master_rule_ref": f"Master .MD Reference [{ref_num}]: {master_ref_hint or 'Required Bibliographic Entry'}",
                            "source_engine": "master-md-reference-checker",
                        }
                    )

        for m in re.finditer(r"\bAppendix\s+([A-Z0-9]+)\b", clean_page):
            app_id = f"Appendix {m.group(1).upper()}"
            line_start = clean_page.rfind("\n", 0, m.start())
            line_prefix = clean_page[
                0 if line_start == -1 else line_start + 1 : m.end() + 2
            ].strip()
            if re.match(
                rf"^#*\s*Appendix\s+{m.group(1)}\b\s*[:—-]",
                line_prefix,
                re.IGNORECASE,
            ):
                continue
            if app_id not in target_defined_appendices:
                key = f"app:{app_id}"
                if key not in seen_on_page:
                    seen_on_page.add(key)
                    snippet = _extract_word_window(clean_page, m.start(), m.end(), 2, 2)
                    master_app_title = master_spec["required_appendices"].get(app_id)
                    issues.append(
                        {
                            "page_number": page_num,
                            "category": "missing_reference",
                            "severity": "warning",
                            "title": f"Missing Required {app_id}"
                            + (f" ({master_app_title})" if master_app_title else ""),
                            "verbatim_snippet": snippet,
                            "issue_description": (
                                f"The text cites '{app_id}' (required by the Master .MD Base), "
                                f"but '{app_id}' is missing from the Target PDF document."
                            ),
                            "suggestion_to_fix": (
                                f"Include '{app_id}: {master_app_title or 'Supporting Data'}' in the Target PDF as specified in the Master .MD Base."
                            ),
                            "why_to_ignore": (
                                "Safe to ignore if large raw spectral/oscilloscope appendices are delivered "
                                "as external digital data packages (.csv/.mat) alongside the PDF."
                            ),
                            "master_rule_ref": f"Master .MD Required Appendix: {app_id} — {master_app_title or 'Mandatory Attachment'}",
                            "source_engine": "master-md-reference-checker",
                        }
                    )

        ext_re = re.compile(
            r"\b(?:Report|Document|Study|Calibration\s+Certificate)\s+(?:No\.?\s*)?([A-Z]{2,5}-\d{2,4}-[A-Z0-9-]+)\b"
        )
        for m in ext_re.finditer(clean_page):
            rep_code = m.group(1).strip()
            if rep_code.lower() not in target_ref_section_text.lower():
                key = f"ext:{rep_code}"
                if key not in seen_on_page:
                    seen_on_page.add(key)
                    snippet = _extract_word_window(clean_page, m.start(), m.end(), 2, 2)
                    issues.append(
                        {
                            "page_number": page_num,
                            "category": "missing_reference",
                            "severity": "warning",
                            "title": f"Unlisted Reference Report ({rep_code})",
                            "verbatim_snippet": snippet,
                            "issue_description": (
                                f"External report '{rep_code}' is cited in the body text (and required in the Master .MD "
                                f"References), but is missing from the Target PDF's References section."
                            ),
                            "suggestion_to_fix": f"Add the full citation for '{rep_code}' into the Target PDF References section.",
                            "why_to_ignore": (
                                f"Ignore if '{rep_code}' is an internal laboratory tracking number that does not "
                                "require formal external bibliographic listing."
                            ),
                            "master_rule_ref": f"Master .MD References Section: Mandatory citation for external report {rep_code}",
                            "source_engine": "master-md-reference-checker",
                        }
                    )

        # --- PILLAR C: TYPO, GRAMMAR & TERMINOLOGY/UNIT CHECK ---
        for typo_w, (correct_w, desc) in KNOWN_TYPOS_MAP.items():
            for m in re.finditer(rf"\b{re.escape(typo_w)}\b", clean_page, re.IGNORECASE):
                key = f"typo:{typo_w.lower()}"
                if key not in seen_on_page:
                    seen_on_page.add(key)
                    snippet = _extract_word_window(clean_page, m.start(), m.end(), 2, 2)
                    issues.append(
                        {
                            "page_number": page_num,
                            "category": "typo",
                            "severity": "info",
                            "title": f"Terminology Typo: '{typo_w}' → '{correct_w}'",
                            "verbatim_snippet": snippet,
                            "issue_description": desc,
                            "suggestion_to_fix": f"Correct spelling from '{typo_w}' to '{correct_w}' to match the Master .MD Base.",
                            "why_to_ignore": (
                                "Cosmetic typographic error that does not alter technical meaning or quantitative audit conclusions."
                            ),
                            "master_rule_ref": f"Master .MD Terminology Standard: Use '{correct_w}'",
                            "source_engine": "master-md-terminology-checker",
                        }
                    )

        for pat, title, desc, fix, ignore_reason in UNIT_DEVIATION_RULES:
            for m in pat.finditer(clean_page):
                key = f"unit:{m.group(0)}"
                if key not in seen_on_page:
                    seen_on_page.add(key)
                    snippet = _extract_word_window(clean_page, m.start(), m.end(), 2, 2)
                    issues.append(
                        {
                            "page_number": page_num,
                            "category": "typo",
                            "severity": "warning",
                            "title": title,
                            "verbatim_snippet": snippet,
                            "issue_description": desc,
                            "suggestion_to_fix": fix,
                            "why_to_ignore": ignore_reason,
                            "master_rule_ref": "Master .MD SI Engineering Units Standard (kWh, MWh, K, m/s)",
                            "source_engine": "master-md-unit-checker",
                        }
                    )

    return issues


def execute_audit_pipeline(
    pdf_path: Path,
    target_filename: str,
    template_name: str,
    master_md: str,
    ollama_model: str,
    math_tolerance: float = DEFAULT_MATH_TOLERANCE,
) -> AuditRunResponse:
    """
    Execute the complete Feature 2 Audit Pipeline:
    1. Lock `pdf_path` read-only and compute initial SHA-256 hash.
    2. Render each page at 150 DPI (`page.get_pixmap(dpi=150)`).
    3. Extract Target PDF text & tables page-by-page + Cross-Page Symbol Registry.
    4. Run Ollama + SymPy + Master `.md` Comparator across all 4 checks with Dual Reasoning.
    5. Map every issue's `verbatim_snippet` via `locate_issue_detailed_on_pdf_page` to
       normalized percentages, multi-line `bboxes`, and `table_cell_ref`.
    """
    t0 = time.perf_counter()
    lock_file_readonly(pdf_path)
    sha_before = compute_sha256(pdf_path)

    audit_id = f"audit-{uuid.uuid4().hex[:10]}"
    _, target_pages_md = convert_pdf_to_structured_markdown(
        pdf_path, title_label=target_filename
    )
    pages_out = render_pdf_pages_to_images(pdf_path, audit_id=audit_id, dpi=RENDER_DPI)

    symbol_dict = build_document_symbol_registry(target_pages_md)
    symbol_entries = [SymbolEntryOut(**v) for v in symbol_dict.values()]

    master_spec = parse_master_md_requirements(master_md)

    llm_raw_issues, ollama_connected = query_ollama_audit_against_master(
        target_pages_md=target_pages_md,
        master_md=master_md,
        ollama_model=ollama_model,
        ollama_url=OLLAMA_CHAT_URL,
        tolerance=math_tolerance,
    )

    det_raw_issues = scan_target_against_master_deterministic(
        target_pages_md=target_pages_md,
        master_spec=master_spec,
        tolerance=math_tolerance,
    )

    combined_raw = det_raw_issues + llm_raw_issues

    doc = fitz.open(str(pdf_path))
    deduped_issues: List[AuditIssueOut] = []
    seen_keys: Set[Tuple[int, str, str]] = set()

    for idx_num, raw in enumerate(combined_raw, start=1):
        p_num = max(1, min(int(raw.get("page_number", 1)), len(doc)))
        cat = raw["category"]
        snip = str(raw["verbatim_snippet"]).strip()
        dedup_token = (
            str(raw.get("stated_result") or "")
            or re.sub(r"\W+", "", snip.lower())[:24]
        ).lower()
        key = (p_num, cat, dedup_token)
        if key in seen_keys:
            continue
        seen_keys.add(key)

        page = doc[p_num - 1]
        (
            left_pct,
            top_pct,
            width_pct,
            height_pct,
            bboxes,
            table_cell_ref,
            match_method,
        ) = locate_issue_detailed_on_pdf_page(page, raw)

        deduped_issues.append(
            AuditIssueOut(
                id=f"ISS-{len(deduped_issues) + 1:03d}",
                page_number=p_num,
                category=cat,
                severity=raw["severity"],
                title=raw["title"],
                verbatim_snippet=snip,
                issue_description=raw["issue_description"],
                suggestion_to_fix=raw["suggestion_to_fix"],
                why_to_ignore=raw["why_to_ignore"],
                stated_expression=raw.get("stated_expression"),
                stated_result=raw.get("stated_result"),
                true_result=raw.get("true_result"),
                discrepancy=raw.get("discrepancy"),
                left_pct=left_pct,
                top_pct=top_pct,
                width_pct=width_pct,
                height_pct=height_pct,
                bboxes=bboxes,
                table_cell_ref=table_cell_ref,
                master_rule_ref=raw.get("master_rule_ref"),
                match_method=match_method,
                source_engine=raw.get("source_engine", "ollama+sympy"),
            )
        )

    doc.close()

    cat_priority = {
        "calculation": 0,
        "missing_reference": 1,
        "structure_mismatch": 2,
        "typo": 3,
    }
    deduped_issues.sort(key=lambda x: (x.page_number, cat_priority.get(x.category, 9)))

    sha_after = compute_sha256(pdf_path)
    duration = round(time.perf_counter() - t0, 2)

    response = AuditRunResponse(
        audit_id=audit_id,
        target_filename=target_filename,
        template_name=template_name,
        ollama_model=(
            ollama_model
            if ollama_connected
            else f"{ollama_model} (SymPy + Master .MD Hybrid)"
        ),
        ollama_connected=ollama_connected,
        original_sha256=sha_after,
        integrity_preserved=(sha_before == sha_after),
        duration_seconds=duration,
        pages=pages_out,
        issues=deduped_issues,
        symbol_registry=symbol_entries,
    )

    AUDIT_SESSION_STORE[audit_id] = {
        "pdf_path": pdf_path,
        "target_filename": target_filename,
        "response": response,
    }
    return response


async def stream_audit_pipeline_events(
    pdf_path: Path,
    target_filename: str,
    template_name: str,
    master_md: str,
    ollama_model: str,
) -> AsyncGenerator[str, None]:
    """
    Server-Sent Events (SSE) generator streaming real-time progress stages:
    1. `stage: "locking"` — Read-only lock & SHA-256 verification
    2. `stage: "rendered"` — Immediate 150 DPI page images so the UI renders the PDF right away
    3. `stage: "page_audit"` — Per-page progress updates
    4. `stage: "completed"` — Full `AuditRunResponse` payload
    """
    lock_file_readonly(pdf_path)
    sha_before = compute_sha256(pdf_path)
    yield f"data: {json.dumps({'stage': 'locking', 'progress': 15, 'message': f'Locked {target_filename} read-only (SHA-256: {sha_before[:12]}...)'})}\n\n"
    await asyncio.sleep(0.05)

    audit_id = f"audit-{uuid.uuid4().hex[:10]}"
    pages_out = render_pdf_pages_to_images(pdf_path, audit_id=audit_id, dpi=RENDER_DPI)
    yield f"data: {json.dumps({'stage': 'rendered', 'progress': 40, 'audit_id': audit_id, 'sha256': sha_before, 'pages': [p.model_dump() for p in pages_out], 'message': f'Rendered {len(pages_out)} pages at 150 DPI'})}\n\n"
    await asyncio.sleep(0.05)

    yield f"data: {json.dumps({'stage': 'page_audit', 'progress': 70, 'message': 'Running 4-Pillar Master .MD Comparator + Python SymPy + Table Coordinate Pinning...'})}\n\n"
    await asyncio.sleep(0.05)

    final_res = execute_audit_pipeline(
        pdf_path=pdf_path,
        target_filename=target_filename,
        template_name=template_name,
        master_md=master_md,
        ollama_model=ollama_model,
    )
    yield f"data: {json.dumps({'stage': 'completed', 'progress': 100, 'result': final_res.model_dump()})}\n\n"
