"""
Local Ollama LLM integration for AI-Assisted .MD rule editing (with YAML Frontmatter
contract sync and GitHub-style line diffing) and Target PDF auditing.
"""

from __future__ import annotations

import difflib
import json
import re
from typing import Any, Dict, List, Tuple

import requests

from backend.config import (
    DEFAULT_MATH_TOLERANCE,
    DEFAULT_OLLAMA_MODEL,
    OLLAMA_CHAT_URL,
    OLLAMA_TIMEOUT_SECONDS,
)
from backend.schemas import DiffLineItem
from backend.services.math_service import evaluate_with_sympy


def check_ollama_available(
    ollama_url: str = OLLAMA_CHAT_URL,
    model: str = DEFAULT_OLLAMA_MODEL,
) -> Dict[str, Any]:
    """Check if local Ollama server is reachable and return installed models."""
    base_url = ollama_url.split("/api/")[0].rstrip("/")
    try:
        resp = requests.get(f"{base_url}/api/tags", timeout=2.5)
        if resp.status_code == 200:
            models = [m.get("name", "") for m in resp.json().get("models", []) if m.get("name")]
            return {
                "connected": True,
                "available_models": models,
                "recommended_model": model,
            }
    except Exception as exc:
        return {
            "connected": False,
            "available_models": [],
            "recommended_model": model,
            "error": str(exc),
        }
    return {"connected": False, "available_models": [], "recommended_model": model}


def extract_json_from_llm_text(raw_text: str) -> Dict[str, Any]:
    """
    Robustly parse JSON from Ollama response text, recovering cleanly if the LLM
    wraps JSON in ```json ... ``` fences or includes leading/trailing commentary.
    """
    if not raw_text:
        return {}
    cleaned = raw_text.strip()
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
        if isinstance(parsed, list):
            return {"issues": parsed}
    except json.JSONDecodeError:
        pass

    fence_match = re.search(r"```(?:json)?\s*(\{.*\}|\[.*\])\s*```", cleaned, flags=re.DOTALL)
    if fence_match:
        try:
            parsed = json.loads(fence_match.group(1))
            return parsed if isinstance(parsed, dict) else {"issues": parsed}
        except json.JSONDecodeError:
            pass

    start_brace = cleaned.find("{")
    end_brace = cleaned.rfind("}")
    if start_brace != -1 and end_brace > start_brace:
        try:
            parsed = json.loads(cleaned[start_brace : end_brace + 1])
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    return {}


def compute_markdown_diff_lines(before_md: str, after_md: str) -> List[DiffLineItem]:
    """
    Compute a compact GitHub-style line diff between `before_md` and `after_md`,
    returning all added/removed lines plus 2 lines of surrounding context.
    """
    before_lines = before_md.splitlines()
    after_lines = after_md.splitlines()
    matcher = difflib.SequenceMatcher(None, before_lines, after_lines)
    diff_items: List[DiffLineItem] = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            lines = after_lines[j1:j2]
            if len(lines) > 4:
                for offset, ln in enumerate(lines[:2]):
                    diff_items.append(
                        DiffLineItem(type="unchanged", content=ln, line_num=j1 + offset + 1)
                    )
                diff_items.append(
                    DiffLineItem(
                        type="unchanged",
                        content=f"... ({len(lines) - 4} unchanged lines) ...",
                        line_num=None,
                    )
                )
                for offset, ln in enumerate(lines[-2:]):
                    diff_items.append(
                        DiffLineItem(
                            type="unchanged",
                            content=ln,
                            line_num=j2 - 1 + offset,
                        )
                    )
            else:
                for offset, ln in enumerate(lines):
                    diff_items.append(
                        DiffLineItem(type="unchanged", content=ln, line_num=j1 + offset + 1)
                    )
        elif tag in ("replace", "delete"):
            for ln in before_lines[i1:i2]:
                diff_items.append(DiffLineItem(type="removed", content=ln, line_num=None))
            if tag == "replace":
                for offset, ln in enumerate(after_lines[j1:j2]):
                    diff_items.append(
                        DiffLineItem(type="added", content=ln, line_num=j1 + offset + 1)
                    )
        elif tag == "insert":
            for offset, ln in enumerate(after_lines[j1:j2]):
                diff_items.append(
                    DiffLineItem(type="added", content=ln, line_num=j1 + offset + 1)
                )

    return diff_items


def _sync_yaml_frontmatter_contract(markdown_text: str, instruction: str) -> str:
    """
    Ensure or update a structured YAML Frontmatter Rule Block at the top of the Master `.md`
    when new references, appendices, or governing formulas are injected via AI Assist.
    """
    ref_codes = re.findall(
        r"\b(?:TR-\d{4}-[A-Z0-9]+|ISO-\d+(?:-\d+)?|ASME\s+PTC\s+[\d.-]+|IEEE\s+[\d.-]+)\b",
        instruction,
    )
    formulas = re.findall(
        r"([A-Za-z][A-Za-z0-9\s]{2,28}=\s*[A-Za-z][A-Za-z0-9\s+\-*/()]{3,50})",
        instruction,
    )
    appendices = re.findall(r"\bAppendix\s+[A-Z0-9]+\b", instruction, re.IGNORECASE)

    fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", markdown_text, flags=re.DOTALL)
    if fm_match:
        fm_body = fm_match.group(1)
        rest_md = markdown_text[fm_match.end() :]
        for rc in ref_codes:
            if rc not in fm_body:
                fm_body += f'\nmandatory_reference_rule: "{rc}"'
        for eq in formulas:
            clean_eq = eq.strip()
            if clean_eq not in fm_body:
                fm_body += f'\ngoverning_equation_rule: "{clean_eq}"'
        for app in appendices:
            if app not in fm_body:
                fm_body += f'\nmandatory_appendix_rule: "{app}"'
        return f"---\n{fm_body.strip()}\n---\n{rest_md}"

    # If no YAML frontmatter existed yet and rules were found, prepend a compact contract block
    if ref_codes or formulas or appendices:
        fm_lines = ["---", "schema: template_audit_master_v2"]
        for rc in ref_codes:
            fm_lines.append(f'mandatory_reference_rule: "{rc}"')
        for eq in formulas:
            fm_lines.append(f'governing_equation_rule: "{eq.strip()}"')
        for app in appendices:
            fm_lines.append(f'mandatory_appendix_rule: "{app}"')
        fm_lines.append("---\n")
        return "\n".join(fm_lines) + markdown_text

    return markdown_text


def apply_ai_assist_to_markdown(
    current_md: str,
    instruction: str,
    ollama_model: str = DEFAULT_OLLAMA_MODEL,
    ollama_url: str = OLLAMA_CHAT_URL,
) -> Tuple[str, str, str]:
    """
    Use local Ollama (`http://localhost:11434/api/chat`) to update/inject user-specified
    audit rules, required citations, or formula standards into the Master `.md` Base.
    Falls back to deterministic rule injection when Ollama is offline.
    Also synchronizes the structured YAML frontmatter rule contract.
    Returns `(updated_markdown, engine_used, change_summary)`.
    """
    status = check_ollama_available(ollama_url, ollama_model)
    if status.get("connected"):
        system_prompt = (
            "You are TemplateAudit AI's Master Markdown Standard Architect. "
            "The user will provide a Master Markdown (.md) document and an instruction describing "
            "audit rules, required citations, section requirements, or mathematical formulas to add or modify. "
            "Update the Markdown document to cleanly incorporate the user's instruction while preserving all "
            "existing sections, YAML frontmatter, tables, and references. Return ONLY the complete updated "
            "Markdown text without wrapping it in outer triple-backtick code fences."
        )
        user_prompt = (
            f"=== USER INSTRUCTION ===\n{instruction.strip()}\n\n"
            f"=== CURRENT MASTER MARKDOWN (.MD) ===\n{current_md}"
        )
        try:
            resp = requests.post(
                ollama_url,
                json={
                    "model": ollama_model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "stream": False,
                    "options": {"temperature": 0.15},
                },
                timeout=OLLAMA_TIMEOUT_SECONDS,
            )
            if resp.status_code == 200:
                content = resp.json().get("message", {}).get("content", "").strip()
                content = re.sub(r"^```(?:markdown|md)?\s*\n", "", content)
                content = re.sub(r"\n```\s*$", "", content)
                if len(content) > 50:
                    synced = _sync_yaml_frontmatter_contract(content, instruction)
                    return (
                        synced,
                        f"ollama ({ollama_model})",
                        f"Injected rule via Ollama ({ollama_model}) & synced YAML schema: {instruction.strip()}",
                    )
        except Exception:
            pass

    # Deterministic Rule Injector Fallback
    rule_line = f"- [x] **ENFORCED AUDIT RULE**: {instruction.strip()}"
    sec_match = re.search(r"\bSection\s+(\d+)\b", instruction, re.IGNORECASE)
    updated_md = current_md

    if sec_match:
        sec_num = sec_match.group(1)
        sec_pattern = re.compile(
            rf"(^#+\s*(?:\*\*\s*)?{re.escape(sec_num)}\.\s+[^\n]+)",
            re.IGNORECASE | re.MULTILINE,
        )
        if sec_pattern.search(updated_md):
            updated_md = sec_pattern.sub(
                rf"\1\n\n> **Enforced Section {sec_num} Audit Rule**: {instruction.strip()}",
                updated_md,
                count=1,
            )
            updated_md = _sync_yaml_frontmatter_contract(updated_md, instruction)
            return (
                updated_md,
                "deterministic-rule-injector",
                f"Injected rule under Section {sec_num} & updated YAML contract in Master .MD standard.",
            )

    checklist_hdr = re.search(
        r"(##\s+Audit Checklist & Enforcement Rules[^\n]*\n)",
        updated_md,
        re.IGNORECASE,
    )
    if checklist_hdr:
        insert_pos = checklist_hdr.end()
        updated_md = updated_md[:insert_pos] + f"{rule_line}\n" + updated_md[insert_pos:]
    else:
        updated_md = (
            f"## Audit Checklist & Enforcement Rules\n{rule_line}\n\n---\n\n" + updated_md
        )

    updated_md = _sync_yaml_frontmatter_contract(updated_md, instruction)
    return (
        updated_md,
        "deterministic-rule-injector",
        f"Injected enforcement rule into Audit Checklist & YAML contract: \"{instruction.strip()}\"",
    )


def query_ollama_audit_against_master(
    target_pages_md: List[str],
    master_md: str,
    ollama_model: str = DEFAULT_OLLAMA_MODEL,
    ollama_url: str = OLLAMA_CHAT_URL,
    tolerance: float = DEFAULT_MATH_TOLERANCE,
) -> Tuple[List[Dict[str, Any]], bool]:
    """
    Query local Ollama (`http://localhost:11434/api/chat`, `format: "json"`) page-by-page
    to compare the Target PDF against the Master `.md` Base and generate issues with Dual Reasoning
    (`suggestion_to_fix` and `why_to_ignore`). Also runs SymPy on any LLM-extracted formulas.
    """
    status = check_ollama_available(ollama_url, ollama_model)
    if not status.get("connected"):
        return [], False

    llm_issues: List[Dict[str, Any]] = []
    system_prompt = (
        "You are TemplateAudit AI. Compare the Target PDF Page against the Master .MD Base standard. "
        "Identify deviations across 4 categories: 'calculation', 'missing_reference', 'structure_mismatch', 'typo'. "
        "Return ONLY valid JSON with key 'issues' containing a list of objects matching this exact schema:\n"
        "{\n"
        '  "issues": [\n'
        "    {\n"
        '      "page_number": 1,\n'
        '      "category": "calculation" | "missing_reference" | "structure_mismatch" | "typo",\n'
        '      "severity": "critical" | "warning" | "info",\n'
        '      "title": "Short issue title",\n'
        '      "verbatim_snippet": "Exact 3-to-8 word phrase or number from the Target PDF",\n'
        '      "stated_expression": "Optional math formula e.g. 1250 + 840 + 310",\n'
        '      "stated_result": "Optional stated math result e.g. 2450",\n'
        '      "issue_description": "How it deviates from the Master .MD Base or why the calculation is wrong",\n'
        '      "suggestion_to_fix": "Actionable recommendation on how to fix the error",\n'
        '      "why_to_ignore": "Thoughtful explanation of why the user might safely ignore this warning"\n'
        "    }\n"
        "  ]\n"
        "}"
    )

    for idx, page_md in enumerate(target_pages_md):
        page_num = idx + 1
        user_prompt = (
            f"=== MASTER .MD BASE STANDARD ===\n{master_md[:3500]}\n\n"
            f"=== TARGET PDF PAGE {page_num} ===\n{page_md}"
        )
        try:
            resp = requests.post(
                ollama_url,
                json={
                    "model": ollama_model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "format": "json",
                    "stream": False,
                    "options": {"temperature": 0.1},
                },
                timeout=OLLAMA_TIMEOUT_SECONDS,
            )
            if resp.status_code != 200:
                continue
            raw_content = resp.json().get("message", {}).get("content", "{}")
            parsed = extract_json_from_llm_text(raw_content)
            for item in parsed.get("issues", []) or []:
                if not isinstance(item, dict):
                    continue
                cat = str(item.get("category") or "typo").lower()
                if cat not in ("calculation", "missing_reference", "structure_mismatch", "typo"):
                    cat = "structure_mismatch"
                sev = str(item.get("severity") or "warning").lower()
                if sev not in ("critical", "warning", "info"):
                    sev = "warning"

                snippet = str(item.get("verbatim_snippet") or "").strip()
                if not snippet:
                    continue

                expr = item.get("stated_expression")
                stated_res = item.get("stated_result")
                true_res = None
                discrepancy = None

                if cat == "calculation" and expr and stated_res is not None:
                    sym = evaluate_with_sympy(str(expr), stated_res, tolerance)
                    if sym is not None:
                        if not sym["is_error"]:
                            continue
                        true_res = sym["true_formatted"]
                        stated_res = sym["stated_formatted"]
                        discrepancy = sym["discrepancy"]
                        sev = "critical"

                llm_issues.append(
                    {
                        "page_number": page_num,
                        "category": cat,
                        "severity": sev,
                        "title": str(item.get("title") or "Master .MD Deviation"),
                        "verbatim_snippet": snippet,
                        "issue_description": str(
                            item.get("issue_description")
                            or "Deviates from Master .MD Base standard."
                        ),
                        "suggestion_to_fix": str(
                            item.get("suggestion_to_fix")
                            or "Update text to align with Master .MD Base."
                        ),
                        "why_to_ignore": str(
                            item.get("why_to_ignore")
                            or "May be ignored if project-specific scope supersedes standard."
                        ),
                        "stated_expression": str(expr) if expr else None,
                        "stated_result": str(stated_res) if stated_res is not None else None,
                        "true_result": true_res,
                        "discrepancy": discrepancy,
                        "source_engine": f"ollama:{ollama_model}",
                    }
                )
        except Exception:
            continue

    return llm_issues, True
