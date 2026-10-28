"""
Deterministic mathematical expression verification, Cross-Page Symbol Registry,
and Dimensional Unit Consistency Engine powered by Python SymPy.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

import sympy
from sympy.parsing.sympy_parser import (
    convert_xor,
    implicit_multiplication_application,
    parse_expr,
    standard_transformations,
)

from backend.config import DEFAULT_MATH_TOLERANCE


SYMPY_TRANSFORMATIONS = standard_transformations + (
    implicit_multiplication_application,
    convert_xor,
)

# Canonical physical dimension families for engineering unit consistency checks
UNIT_DIMENSION_FAMILY: Dict[str, Tuple[str, float]] = {
    "w": ("power", 1e-3),
    "kw": ("power", 1.0),
    "mw": ("power", 1e3),
    "gw": ("power", 1e6),
    "wh": ("energy", 1e-3),
    "kwh": ("energy", 1.0),
    "mwh": ("energy", 1e3),
    "J": ("energy", 2.77778e-7),
    "kj": ("energy", 2.77778e-4),
    "mj": ("energy", 0.277778),
    "n": ("force", 1e-6),
    "kn": ("force", 1e-3),
    "mn": ("force", 1.0),
    "pa": ("pressure", 1e-6),
    "kpa": ("pressure", 1e-3),
    "mpa": ("pressure", 1.0),
    "bar": ("pressure", 0.1),
    "k": ("temperature", 1.0),
    "c": ("temperature", 1.0),
    "v": ("voltage", 1.0),
    "kv": ("voltage", 1e3),
    "a": ("current", 1.0),
    "hz": ("frequency", 1.0),
    "rpm": ("rotational_speed", 1.0),
    "m/s": ("velocity", 1.0),
    "mm/s": ("velocity", 1e-3),
}


def parse_numeric_value(raw: Any) -> Optional[float]:
    """Extract a floating-point number from a formatted string (handles commas, currency, units)."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    text = str(raw).strip()
    if not text:
        return None
    cleaned = re.sub(r"(?<=\d),(?=\d{3}\b)", "", text)
    cleaned = cleaned.replace("$", "").replace("€", "").replace("£", "")
    matches = re.findall(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", cleaned)
    if not matches:
        return None
    try:
        return float(matches[0])
    except ValueError:
        return None


def build_document_symbol_registry(pages_md: List[str]) -> Dict[str, Dict[str, Any]]:
    """
    Scan all pages of a document to build a Cross-Page Symbol Registry of named engineering
    parameters (`symbol`, `label`, `value`, `unit`, `page_number`).
    Supports patterns such as:
      - `Loop A = 1250.0 kW` or `Dead Load = 18.40 MN`
      - `Live Load = 4.85 MN`
    """
    registry: Dict[str, Dict[str, Any]] = {}
    assign_pattern = re.compile(
        r"\b([A-Za-z][A-Za-z0-9_]*(?:\s+[A-Za-z0-9_]+){0,3})\s*(?:=|:)\s*([-+]?\d+(?:,\d{3})*(?:\.\d+)?)\s*"
        r"(kW|MW|GW|kWh|MWh|MN|kN|MPa|kPa|bar|K|V|A|Hz|mm/s|m/s)\b"
    )
    leading_stopwords = {
        "page",
        "defines",
        "where",
        "and",
        "with",
        "is",
        "of",
        "for",
        "the",
        "at",
        "in",
        "recorded",
        "states",
    }

    for idx, page_md in enumerate(pages_md):
        page_num = idx + 1
        clean_text = re.sub(r"\*\*|[`_]", "", page_md)
        for m in assign_pattern.finditer(clean_text):
            words = m.group(1).strip().split()
            while words and (words[0].lower() in leading_stopwords or words[0].isdigit()):
                words.pop(0)
            raw_label = " ".join(words).strip()
            if not raw_label:
                continue
            if any(
                skip in raw_label.lower()
                for skip in ("total", "sum", "net", "combined", "section", "table")
            ):
                continue
            # Skip if preceded immediately by '+' or '-' (part of a multi-term LHS formula)
            prefix_char = clean_text[max(0, m.start() - 3) : m.start()].strip()
            if prefix_char.endswith(("+", "-", "*", "/")):
                continue
            val = parse_numeric_value(m.group(2))
            unit = m.group(3).strip()
            if val is None:
                continue
            norm_sym = re.sub(r"\s+", "_", raw_label.strip())
            registry[norm_sym] = {
                "symbol": norm_sym,
                "label": raw_label,
                "value": val,
                "unit": unit,
                "page_number": page_num,
            }

    return registry


def substitute_known_symbols(
    expr_str: str,
    symbol_registry: Optional[Dict[str, Dict[str, Any]]] = None,
) -> str:
    """Substitute known cross-page symbolic parameters into `expr_str` before SymPy parsing."""
    if not symbol_registry:
        return expr_str
    updated = expr_str
    # Sort longest symbol names first so "Loop_A" matches before "A"
    for sym_key, meta in sorted(symbol_registry.items(), key=lambda x: len(x[0]), reverse=True):
        label = meta["label"]
        val_str = str(meta["value"])
        updated = re.sub(rf"\b{re.escape(label)}\b", val_str, updated, flags=re.IGNORECASE)
        updated = re.sub(rf"\b{re.escape(sym_key)}\b", val_str, updated, flags=re.IGNORECASE)
    return updated


def check_dimensional_unit_consistency(
    raw_expression_with_units: str,
    raw_result_with_units: str,
) -> Optional[Dict[str, str]]:
    """
    Inspect an equation containing physical units to verify dimensional homogeneity:
    - Detects adding/subtracting incompatible dimensions (e.g., `kW + kWh`)
    - Detects unit scale mismatches between homogenous operands and stated result (e.g., `kW + kW = MW` without `/1000`)
    """
    unit_regex = re.compile(
        r"([-+]?\d+(?:,\d{3})*(?:\.\d+)?)\s*(kW|MW|GW|W|kWh|MWh|Wh|MN|kN|N|MPa|kPa|Pa|bar|K|V|kV|A|Hz|m/s|mm/s)\b"
    )
    lhs_units = [m.group(2) for m in unit_regex.finditer(raw_expression_with_units)]
    rhs_m = unit_regex.search(raw_result_with_units)
    rhs_unit = rhs_m.group(2) if rhs_m else None

    if not lhs_units or not rhs_unit:
        return None

    # Only check pure additive/subtractive expressions when comparing LHS operand units
    if not any(op in raw_expression_with_units for op in ("*", "/")):
        families = {
            UNIT_DIMENSION_FAMILY.get(u.lower(), (u.lower(), 1.0))[0] for u in lhs_units
        }
        rhs_family = UNIT_DIMENSION_FAMILY.get(rhs_unit.lower(), (rhs_unit.lower(), 1.0))[0]
        if len(families) > 1 or (families and rhs_family not in families):
            return {
                "issue": f"Dimensional mismatch: LHS uses {lhs_units} ({', '.join(families)}) while result uses '{rhs_unit}' ({rhs_family}).",
                "lhs_units": ", ".join(lhs_units),
                "rhs_unit": rhs_unit,
            }

    return None


def clean_math_expression(
    expr_str: str,
    symbol_registry: Optional[Dict[str, Dict[str, Any]]] = None,
) -> str:
    """Normalize mathematical operators and strip formatting so SymPy can parse safely."""
    s = substitute_known_symbols(str(expr_str).strip(), symbol_registry)
    s = re.sub(r"(?<=\d),(?=\d{3}\b)", "", s)
    s = (
        s.replace("×", "*")
        .replace("÷", "/")
        .replace("−", "-")
        .replace("–", "-")
        .replace("^", "**")
        .replace("$", "")
    )
    s = re.sub(r"(\d+(?:\.\d+)?)\s*%", r"(\1/100)", s)
    if "=" in s:
        s = s.split("=")[0].strip()
    # Strip trailing or inline physical unit tokens attached to numbers
    s = re.sub(
        r"(?<=\d)\s*(?:kWh|MWh|kW|MW|GW|MN|kN|MPa|kPa|bar|Hz|rpm|mm/s|m/s|K|V|A)\b",
        "",
        s,
        flags=re.IGNORECASE,
    )
    s = re.sub(r"[^0-9a-zA-Z_+\-*/().\s]", "", s)
    return s.strip()


def evaluate_with_sympy(
    stated_expression: str,
    stated_result: Any,
    tolerance: float = DEFAULT_MATH_TOLERANCE,
    symbol_registry: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Evaluate `stated_expression` deterministically using Python `sympy`
    (with optional cross-page `symbol_registry` substitution) and compare against `stated_result`.
    """
    clean_expr = clean_math_expression(stated_expression, symbol_registry=symbol_registry)
    stated_val = parse_numeric_value(stated_result)
    if not clean_expr or stated_val is None:
        return None
    if not any(op in clean_expr for op in ("+", "-", "*", "/", "**", "sqrt")):
        return None

    try:
        sym_expr = parse_expr(
            clean_expr,
            transformations=SYMPY_TRANSFORMATIONS,
            evaluate=True,
        )
        true_val = float(sympy.N(sym_expr))
    except Exception:
        return None

    abs_diff = abs(true_val - stated_val)
    rel_diff = abs_diff / max(abs(true_val), 1e-9)

    stated_str = str(stated_result).strip()
    dec_m = re.search(r"\.(\d+)", stated_str)
    dec_places = len(dec_m.group(1)) if dec_m else 0
    rounding_allowance = 0.5 * (10 ** (-dec_places)) if dec_places > 0 else 0.05
    effective_tol = max(tolerance, rounding_allowance)

    is_error = abs_diff > effective_tol and rel_diff > 0.001

    def _fmt(v: float) -> str:
        if abs(v - round(v)) < 1e-6:
            return f"{int(round(v)):,}"
        return f"{v:,.{max(2, min(4, dec_places or 2))}f}"

    diff_val = stated_val - true_val
    sign = "+" if diff_val > 0 else ""
    pct_err = rel_diff * 100.0

    return {
        "clean_expression": clean_expr,
        "stated_val": stated_val,
        "true_val": true_val,
        "stated_formatted": _fmt(true_val if not is_error else stated_val),
        "true_formatted": _fmt(true_val),
        "abs_diff": abs_diff,
        "rel_diff": rel_diff,
        "discrepancy": f"{sign}{diff_val:,.2f} ({sign}{pct_err:.2f}%)",
        "is_error": is_error,
    }
