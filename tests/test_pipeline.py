"""
TemplateAudit AI — Automated Unit & Integration Test Suite
==========================================================
Verifies:
1. Deterministic SymPy Math Verifier (`backend.services.math_service`)
2. Cross-Page Symbol Registry & Dimensional Unit Consistency (`backend.services.math_service`)
3. Master .MD Requirement Parser (with YAML Frontmatter Schema) & Comparator (`backend.services.audit_service`)
4. PyMuPDF Coordinate Lookup Bridge & Table-Cell `(row, col)` Disambiguation (`backend.services.coordinate_service`)
5. FastAPI Endpoints including GitHub-Style AI Diffing (`/api/templates/ai-assist`)
   and Real-Time SSE Streaming (`/api/audit/stream-sample`).
"""

from __future__ import annotations

import asyncio
import unittest

import httpx
import pymupdf as fitz

from backend.config import SAMPLES_DIR, TEMPLATES_DIR
from backend.services.audit_service import (
    parse_master_md_requirements,
    scan_target_against_master_deterministic,
)
from backend.services.coordinate_service import (
    locate_issue_detailed_on_pdf_page,
    locate_issue_on_pdf_page,
)
from backend.services.math_service import (
    build_document_symbol_registry,
    check_dimensional_unit_consistency,
    evaluate_with_sympy,
)
from backend.utils.sample_factory import ensure_seed_templates_and_samples
from main import app


class TestTemplateAuditPipeline(unittest.TestCase):
    """Comprehensive unit and ASGI endpoint test suite."""

    @classmethod
    def setUpClass(cls) -> None:
        ensure_seed_templates_and_samples()

    def test_sympy_deterministic_math_verifier(self) -> None:
        """SymPy should accurately flag arithmetic discrepancies and pass valid equations."""
        res_err = evaluate_with_sympy("1250.0 + 840.0 + 310.0", "2510.0")
        self.assertIsNotNone(res_err)
        self.assertTrue(res_err["is_error"])
        self.assertEqual(res_err["true_formatted"], "2,400")

        res_ok = evaluate_with_sympy("1250.0 + 840.0 + 310.0", "2400.0")
        self.assertIsNotNone(res_ok)
        self.assertFalse(res_ok["is_error"])

    def test_cross_page_symbol_registry_and_unit_consistency(self) -> None:
        """Cross-page symbols should substitute into SymPy, and incompatible units should be flagged."""
        pages = [
            "Page 1 defines Dead Load = 18.40 MN and Live Load = 4.85 MN.",
            "Page 2 evaluates Total Load = Dead Load + Live Load = 24.25 MN.",
        ]
        reg = build_document_symbol_registry(pages)
        self.assertIn("Dead_Load", reg)
        self.assertEqual(reg["Dead_Load"]["value"], 18.40)

        sym_res = evaluate_with_sympy(
            "Dead Load + Live Load", "24.25 MN", symbol_registry=reg
        )
        self.assertIsNotNone(sym_res)
        self.assertTrue(sym_res["is_error"])
        self.assertEqual(sym_res["true_formatted"], "23.25")

        # Dimensional check: adding kW (power) and kWh (energy)
        dim_err = check_dimensional_unit_consistency("250 kW + 100 kWh", "350 kWh")
        self.assertIsNotNone(dim_err)
        self.assertIn("Dimensional mismatch", dim_err["issue"])

    def test_markdown_bold_multiplication_preservation(self) -> None:
        """Scanning markdown with bold numbers and '*' multiplication should preserve the operator."""
        master_md = "# Master Standard\n## 1. Executive Summary"
        spec = parse_master_md_requirements(master_md)
        sample_page = "The excitement voltage was recorded at **480.0 * 0.85 = 428.0 V** across the bus."
        findings = scan_target_against_master_deterministic([sample_page], spec)
        calc_findings = [f for f in findings if f["category"] == "calculation"]
        self.assertGreaterEqual(len(calc_findings), 1)
        self.assertEqual(calc_findings[0]["true_result"], "408")

    def test_master_markdown_requirement_parser(self) -> None:
        """Master .MD parser should extract YAML frontmatter rules, sections, references, and appendices."""
        master_path = TEMPLATES_DIR / "Turbine_Thermal_Standard_v1.md"
        content = master_path.read_text(encoding="utf-8")
        reqs = parse_master_md_requirements(content)
        self.assertGreaterEqual(len(reqs["required_sections"]), 3)
        self.assertIn("Appendix A", reqs["required_appendices"])
        self.assertIn("1", reqs["master_refs"])

    def test_coordinate_lookup_bridge_and_table_pinning(self) -> None:
        """PyMuPDF coordinate mapper should return normalized [0..100]% bboxes and multi-line lists."""
        target_pdf = SAMPLES_DIR / "Target_Turbine_Report_With_Errors_2026.pdf"
        raw_issue = {
            "page_number": 1,
            "category": "calculation",
            "severity": "critical",
            "title": "Inline Calculation Error",
            "verbatim_snippet": "1250.0 + 840.0 + 310.0 = 2510.0 kW",
        }
        with fitz.open(str(target_pdf)) as doc:
            l_p, t_p, w_p, h_p, method = locate_issue_on_pdf_page(doc[0], raw_issue)
            self.assertGreater(w_p, 0.0)
            self.assertGreater(h_p, 0.0)
            self.assertIn(method, ("exact", "exact_table_cell", "normalized", "partial_match"))

            # Also verify detailed table cell lookup
            tbl_issue = {
                "page_number": 1,
                "category": "calculation",
                "severity": "critical",
                "title": "Table Column Total Error (Total Energy (kWh))",
                "verbatim_snippet": "1525.0",
                "issue_description": "In row 'Total', column 'Total Energy (kWh)' states 1525.0",
            }
            _, _, _, _, bboxes, tbl_ref, _ = locate_issue_detailed_on_pdf_page(doc[0], tbl_issue)
            self.assertGreaterEqual(len(bboxes), 1)
            self.assertIsNotNone(tbl_ref)
            self.assertIn("Table 1", tbl_ref)

    def test_full_api_and_sse_streaming_workflow(self) -> None:
        """End-to-end ASGI test of Feature 1 (with Diff & YAML sync) and Feature 2 (REST + SSE Stream)."""

        async def _run_async_checks() -> None:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://testserver"
            ) as client:
                # 1. Health check
                r_health = await client.get("/api/health")
                self.assertEqual(r_health.status_code, 200)

                # 2. Extract Sample Perfect PDF (with YAML Frontmatter)
                r_perf = await client.post("/api/templates/load-sample-perfect")
                self.assertEqual(r_perf.status_code, 200)
                perf_data = r_perf.json()
                self.assertIn("schema: template_audit_master_v2", perf_data["markdown"])

                # 3. AI-Assisted rule injection with diff_lines & YAML contract sync
                r_ai = await client.post(
                    "/api/templates/ai-assist",
                    json={
                        "markdown": perf_data["markdown"],
                        "instruction": (
                            "Add a checklist rule under Section 2 that Reference Report "
                            "TR-2025-88B must be cited, and note that Total Load = Dead Load + Live Load"
                        ),
                        "ollama_model": "qwen2.5:7b-instruct",
                    },
                )
                self.assertEqual(r_ai.status_code, 200)
                ai_json = r_ai.json()
                self.assertIn("Total Load = Dead Load + Live Load", ai_json["markdown"])
                self.assertIn('mandatory_reference_rule: "TR-2025-88B"', ai_json["markdown"])
                self.assertGreater(len(ai_json["diff_lines"]), 0)

                # 4. Audit Sample Target PDF via REST
                r_audit = await client.post(
                    "/api/audit/run-sample",
                    data={
                        "template_name": "Turbine_Thermal_Standard_v1",
                        "ollama_model": "qwen2.5:7b-instruct",
                    },
                )
                self.assertEqual(r_audit.status_code, 200)
                audit_data = r_audit.json()
                self.assertTrue(audit_data["integrity_preserved"])
                self.assertGreaterEqual(len(audit_data["issues"]), 6)
                for issue in audit_data["issues"]:
                    self.assertGreaterEqual(len(issue["bboxes"]), 1)
                    self.assertTrue(issue["master_rule_ref"])

                # 5. Audit Sample Target PDF via Real-Time SSE Stream
                r_stream = await client.post(
                    "/api/audit/stream-sample",
                    data={
                        "template_name": "Turbine_Thermal_Standard_v1",
                        "ollama_model": "qwen2.5:7b-instruct",
                    },
                )
                self.assertEqual(r_stream.status_code, 200)
                self.assertIn("stage", r_stream.text)
                self.assertIn("completed", r_stream.text)

        asyncio.run(_run_async_checks())


if __name__ == "__main__":
    unittest.main(verbosity=2)
