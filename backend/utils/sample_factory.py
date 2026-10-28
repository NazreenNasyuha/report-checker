"""Sample PDF generators and Master .MD Base seeder for instant out-of-the-box testing."""

from __future__ import annotations

from pathlib import Path
import pymupdf as fitz  # PyMuPDF

from backend.config import SAMPLES_DIR, TEMPLATES_DIR
from backend.services.pdf_service import convert_pdf_to_structured_markdown


def generate_perfect_turbine_reference_pdf(output_path: Path) -> Path:
    """
    Generate a 100% mathematically and structurally accurate 'Perfect/Reference PDF Report'
    for Combined-Cycle Turbine Unit #4. Used in Feature 1 (Master .MD Base Builder)
    to create the gold-standard Master .MD Base template.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        try:
            output_path.chmod(0o666)
        except OSError:
            pass

    doc = fitz.open()

    # PAGE 1: Perfect Executive Summary, Correct Math & Complete Energy Table
    page1 = doc.new_page(width=595, height=842)
    page1.draw_rect(fitz.Rect(40, 36, 555, 82), color=(0.06, 0.24, 0.20), fill=(0.06, 0.24, 0.20))
    page1.insert_text(
        fitz.Point(52, 58),
        "MASTER REFERENCE STANDARD: COMBINED-CYCLE TURBINE UNIT #4",
        fontsize=12.5,
        fontname="helv",
        color=(1, 1, 1),
    )
    page1.insert_text(
        fitz.Point(52, 74),
        "Doc Ref: STD-2026-CCGT4  |  Prepared by: Thermal Systems Division  |  Status: Gold Standard Template",
        fontsize=8.5,
        fontname="helv",
        color=(0.75, 0.94, 0.88),
    )

    y = 110
    page1.insert_text(fitz.Point(45, y), "1. Executive Summary & Heat Balance Analysis", fontsize=12, fontname="hebo")
    y += 22

    p1_lines = [
        "This report documents the quarterly performance verification of Combined-Cycle Gas Turbine",
        "Unit #4 in accordance with international turbine testing standards [1] and plant baseline specs [2].",
        "During full-load steady-state operation, the primary thermodynamic cycle exhibited stable",
        "combustor dynamics across all three monitoring zones.",
        "",
        "The combined auxiliary thermal load across the three heat recovery loops is calculated as:",
        "Total Thermal Load = Loop A + Loop B + Loop C: 1250.0 + 840.0 + 310.0 = 2400.0 kW.",
        "",
        "Parasitic electrical consumption over the 6-hour baseline window reached 420.5 kWh,",
        "while the exhaust manifold sensor recorded an average plenum temperature of 315 K.",
        "Detailed harmonic distortion plots are provided in Appendix A, and the rotor dynamic",
        "vibration spectrum is documented in Appendix C and validated against citation [4].",
    ]
    for line in p1_lines:
        if line:
            page1.insert_text(fitz.Point(45, y), line, fontsize=9.8, fontname="helv")
        y += 16

    y += 14
    page1.insert_text(fitz.Point(45, y), "2. Subsystem Power & Energy Allocation Table", fontsize=12, fontname="hebo")
    y += 14

    table_top = y
    col_x = [45, 225, 330, 440, 555]
    row_h = 24
    table_rows = [
        ["Subsystem Module", "Rated Power (kW)", "Operating Hours", "Total Energy (kWh)"],
        ["HP Feedwater Pump", "25.0", "24.0", "600.0"],
        ["Lube Oil Circulator", "12.5", "24.0", "300.0"],
        ["Condenser Vacuum Unit", "15.0", "20.0", "300.0"],
        ["Cooling Tower Fan Bank", "11.25", "20.0", "225.0"],
        ["Total", "63.75", "88.0", "1425.0"],
    ]

    for r_idx, row in enumerate(table_rows):
        ry0 = table_top + r_idx * row_h
        ry1 = ry0 + row_h
        if r_idx == 0:
            page1.draw_rect(fitz.Rect(col_x[0], ry0, col_x[-1], ry1), color=(0.15, 0.30, 0.25), fill=(0.88, 0.95, 0.92))
        elif r_idx == len(table_rows) - 1:
            page1.draw_rect(fitz.Rect(col_x[0], ry0, col_x[-1], ry1), color=(0.15, 0.30, 0.25), fill=(0.94, 0.98, 0.96))
        else:
            page1.draw_rect(fitz.Rect(col_x[0], ry0, col_x[-1], ry1), color=(0.6, 0.65, 0.72))

        for c_idx, cell_text in enumerate(row):
            cx0 = col_x[c_idx]
            cx1 = col_x[c_idx + 1]
            page1.draw_line(fitz.Point(cx0, ry0), fitz.Point(cx0, ry1), color=(0.6, 0.65, 0.72))
            font = "hebo" if (r_idx == 0 or r_idx == len(table_rows) - 1) else "helv"
            page1.insert_text(fitz.Point(cx0 + 8, ry0 + 16), cell_text, fontsize=9.5, fontname=font)
        page1.draw_line(fitz.Point(col_x[-1], ry0), fitz.Point(col_x[-1], ry1), color=(0.6, 0.65, 0.72))

    y = table_top + len(table_rows) * row_h + 28
    page1.insert_text(
        fitz.Point(45, y),
        "Note: Subsystem telemetry was cross-checked against historical baseline dataset [3].",
        fontsize=9.2,
        fontname="helv",
    )
    page1.insert_text(fitz.Point(270, 815), "Page 1 of 2", fontsize=8.5, fontname="helv", color=(0.4, 0.4, 0.4))

    # PAGE 2: Complete Calibration, Section 4 Safety Interlocks, All Appendices & All References
    page2 = doc.new_page(width=595, height=842)
    y = 55
    page2.insert_text(fitz.Point(45, y), "3. Generator Excitation & Sensor Calibration", fontsize=12, fontname="hebo")
    y += 22

    p2_lines = [
        "Field winding insulation resistance was verified prior to synchronization using a 5 kV megohmmeter.",
        "Following transducer calibration, the nominal bus voltage under 85% power factor load was",
        "evaluated using the linear tap scaling formula: 480.0 * 0.85 = 408.0 V across the secondary bus.",
        "Acoustic emission thresholds complied with baseline limits defined in Report TR-2025-88B [4].",
        "Thermal expansion clearances for the low-pressure casing are summarized in Appendix B.",
    ]
    for line in p2_lines:
        page2.insert_text(fitz.Point(45, y), line, fontsize=9.8, fontname="helv")
        y += 16

    y += 14
    page2.insert_text(fitz.Point(45, y), "4. Overspeed Trip & Safety Interlock Verification", fontsize=12, fontname="hebo")
    y += 18
    page2.insert_text(
        fitz.Point(45, y),
        "Redundant electro-hydraulic trip solenoids actuated within 18 ms at 110% rated rotor speed (3300 RPM).",
        fontsize=9.5,
        fontname="helv",
    )

    y += 24
    page2.insert_text(fitz.Point(45, y), "Appendix A: Harmonic Distortion Summary", fontsize=11, fontname="hebo")
    y += 16
    page2.insert_text(
        fitz.Point(45, y),
        "Total Harmonic Distortion (THD) remained below 1.8% across all three phases during full-load testing.",
        fontsize=9.5,
        fontname="helv",
    )

    y += 24
    page2.insert_text(fitz.Point(45, y), "Appendix B: Casing Thermal Clearance Log", fontsize=11, fontname="hebo")
    y += 16
    page2.insert_text(
        fitz.Point(45, y),
        "Axial rotor-to-stator clearance measured 4.2 mm (minimum allowable threshold: 3.0 mm).",
        fontsize=9.5,
        fontname="helv",
    )

    y += 24
    page2.insert_text(fitz.Point(45, y), "Appendix C: Rotor Dynamic Vibration Spectrum", fontsize=11, fontname="hebo")
    y += 16
    page2.insert_text(
        fitz.Point(45, y),
        "Peak bearing housing vibration amplitude was 1.4 mm/s RMS, well below the ISO 10816 limit of 2.8 mm/s.",
        fontsize=9.5,
        fontname="helv",
    )

    y += 28
    page2.insert_text(fitz.Point(45, y), "References", fontsize=12, fontname="hebo")
    y += 18

    refs = [
        "[1] ASME PTC 46-2015, Performance Test Code on Overall Plant Performance, American Society of Mechanical Engineers.",
        "[2] ISO 2314:2009, Gas turbines - Acceptance tests, International Organization for Standardization.",
        "[3] Plant Engineering Archive, Unit #4 Commissioning & Baseline Heat Rate Log (Document ID: BL-2024-01).",
        "[4] Acoustic & Vibration Laboratory Report TR-2025-88B, Rotor Dynamic & Acoustic Baseline Qualification.",
    ]
    for ref in refs:
        page2.insert_text(fitz.Point(45, y), ref, fontsize=9.0, fontname="helv")
        y += 16

    page2.insert_text(fitz.Point(270, 815), "Page 2 of 2", fontsize=8.5, fontname="helv", color=(0.4, 0.4, 0.4))

    doc.save(str(output_path), garbage=4, deflate=True)
    doc.close()
    return output_path


def generate_target_turbine_report_with_errors(output_path: Path) -> Path:
    """
    Generate the 2-page Target PDF Report (`Target_Turbine_Report_With_Errors_2026.pdf`)
    containing deliberate calculation errors, missing references, missing Section 4,
    and terminology/unit errors when audited against `Turbine_Thermal_Standard_v1.md`.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        try:
            output_path.chmod(0o666)
        except OSError:
            pass

    doc = fitz.open()

    # PAGE 1
    page1 = doc.new_page(width=595, height=842)
    page1.draw_rect(fitz.Rect(40, 36, 555, 82), color=(0.12, 0.16, 0.23), fill=(0.12, 0.16, 0.23))
    page1.insert_text(
        fitz.Point(52, 58),
        "TECHNICAL AUDIT REPORT: COMBINED-CYCLE TURBINE UNIT #4",
        fontsize=13,
        fontname="helv",
        color=(1, 1, 1),
    )
    page1.insert_text(
        fitz.Point(52, 74),
        "Doc Ref: ENG-2026-CCGT4  |  Prepared by: Thermal Systems Division  |  Status: Final Review",
        fontsize=8.5,
        fontname="helv",
        color=(0.75, 0.82, 0.92),
    )

    y = 110
    page1.insert_text(fitz.Point(45, y), "1. Executive Summary & Heat Balance Analysis", fontsize=12, fontname="hebo")
    y += 22

    p1_lines = [
        "This report documents the quarterly performance verification of Combined-Cycle Gas Turbine",
        "Unit #4 in accordance with international turbine testing standards [1] and plant baseline specs [2].",
        "During full-load steady-state operation, the primary thermodinamic cycle exhibited stable",
        "combustor dynamics across all three monitoring zones.",
        "",
        "The combined auxiliary thermal load across the three heat recovery loops was calculated as:",
        "1250.0 + 840.0 + 310.0 = 2450.0 kW during peak ambient conditions.",
        "",
        "Parasitic electrical consumption over the 6-hour baseline window reached 420.5 kW/h,",
        "while the exhaust manifold sensor recorded an average plenum temperature of 315 degrees Kelvin.",
        "Detailed harmonic distortion plots are provided in Appendix A, whereas the rotor dynamic",
        "vibration spectrum is documented in Appendix C and validated against citation [4].",
    ]
    for line in p1_lines:
        if line:
            page1.insert_text(fitz.Point(45, y), line, fontsize=9.8, fontname="helv")
        y += 16

    y += 14
    page1.insert_text(fitz.Point(45, y), "2. Subsystem Power & Energy Allocation Table", fontsize=12, fontname="hebo")
    y += 14

    table_top = y
    col_x = [45, 225, 330, 440, 555]
    row_h = 24
    table_rows = [
        ["Subsystem Module", "Rated Power (kW)", "Operating Hours", "Total Energy (kWh)"],
        ["HP Feedwater Pump", "25.0", "24.0", "600.0"],
        ["Lube Oil Circulator", "12.5", "24.0", "315.0"],
        ["Condenser Vacuum Unit", "15.0", "20.0", "300.0"],
        ["Cooling Tower Fan Bank", "11.25", "20.0", "225.0"],
        ["Total", "63.75", "88.0", "1495.0"],
    ]

    for r_idx, row in enumerate(table_rows):
        ry0 = table_top + r_idx * row_h
        ry1 = ry0 + row_h
        if r_idx == 0:
            page1.draw_rect(fitz.Rect(col_x[0], ry0, col_x[-1], ry1), color=(0.2, 0.25, 0.35), fill=(0.88, 0.91, 0.96))
        elif r_idx == len(table_rows) - 1:
            page1.draw_rect(fitz.Rect(col_x[0], ry0, col_x[-1], ry1), color=(0.2, 0.25, 0.35), fill=(0.94, 0.95, 0.98))
        else:
            page1.draw_rect(fitz.Rect(col_x[0], ry0, col_x[-1], ry1), color=(0.6, 0.65, 0.72))

        for c_idx, cell_text in enumerate(row):
            cx0 = col_x[c_idx]
            cx1 = col_x[c_idx + 1]
            page1.draw_line(fitz.Point(cx0, ry0), fitz.Point(cx0, ry1), color=(0.6, 0.65, 0.72))
            font = "hebo" if (r_idx == 0 or r_idx == len(table_rows) - 1) else "helv"
            page1.insert_text(fitz.Point(cx0 + 8, ry0 + 16), cell_text, fontsize=9.5, fontname=font)
        page1.draw_line(fitz.Point(col_x[-1], ry0), fitz.Point(col_x[-1], ry1), color=(0.6, 0.65, 0.72))

    y = table_top + len(table_rows) * row_h + 28
    page1.insert_text(
        fitz.Point(45, y),
        "Note: Subsystem telemetry was cross-checked against historical baseline dataset [3].",
        fontsize=9.2,
        fontname="helv",
    )
    page1.insert_text(fitz.Point(270, 815), "Page 1 of 2", fontsize=8.5, fontname="helv", color=(0.4, 0.4, 0.4))

    # PAGE 2 (Deliberately omits Section 4 and Appendix C and Reference [4])
    page2 = doc.new_page(width=595, height=842)
    y = 55
    page2.insert_text(fitz.Point(45, y), "3. Generator Excitation & Sensor Calibration", fontsize=12, fontname="hebo")
    y += 22

    p2_lines = [
        "Field winding insulation resistence was verified prior to synchronization using a 5 kV megohmmeter.",
        "Following transducer calibraton, the nominal bus voltage under 85% power factor load was",
        "evaluated using the linear tap scaling formula: 480.0 * 0.85 = 428.0 V across the secondary bus.",
        "",
        "Acoustic emission thresholds complied with baseline limits defined in Report TR-2025-88B",
        "and supplementary metallurgical inspection findings in citation [6].",
        "Thermal expansion clearances for the low-pressure casing are summarized in Appendix B.",
    ]
    for line in p2_lines:
        if line:
            page2.insert_text(fitz.Point(45, y), line, fontsize=9.8, fontname="helv")
        y += 16

    y += 18
    page2.insert_text(fitz.Point(45, y), "Appendix A: Harmonic Distortion Summary", fontsize=11, fontname="hebo")
    y += 18
    page2.insert_text(
        fitz.Point(45, y),
        "Total Harmonic Distortion (THD) remained below 1.8% across all three phases during full-load testing.",
        fontsize=9.5,
        fontname="helv",
    )

    y += 26
    page2.insert_text(fitz.Point(45, y), "Appendix B: Casing Thermal Clearance Log", fontsize=11, fontname="hebo")
    y += 18
    page2.insert_text(
        fitz.Point(45, y),
        "Axial rotor-to-stator clearance measured 4.2 mm (minimum allowable threshold: 3.0 mm).",
        fontsize=9.5,
        fontname="helv",
    )

    y += 32
    page2.insert_text(fitz.Point(45, y), "References", fontsize=12, fontname="hebo")
    y += 20

    refs = [
        "[1] ASME PTC 46-2015, Performance Test Code on Overall Plant Performance, American Society of Mechanical Engineers.",
        "[2] ISO 2314:2009, Gas turbines - Acceptance tests, International Organization for Standardization.",
        "[3] Plant Engineering Archive, Unit #4 Commissioning & Baseline Heat Rate Log (Document ID: BL-2024-01).",
    ]
    for ref in refs:
        page2.insert_text(fitz.Point(45, y), ref, fontsize=9.2, fontname="helv")
        y += 18

    page2.insert_text(fitz.Point(270, 815), "Page 2 of 2", fontsize=8.5, fontname="helv", color=(0.4, 0.4, 0.4))

    doc.save(str(output_path), garbage=4, deflate=True)
    doc.close()
    return output_path


def ensure_seed_templates_and_samples() -> None:
    """Ensure sample PDFs and default Master .MD templates exist on disk."""
    perfect_turbine_pdf = SAMPLES_DIR / "Perfect_Reference_Turbine_Report_2026.pdf"
    target_turbine_pdf = SAMPLES_DIR / "Target_Turbine_Report_With_Errors_2026.pdf"

    if not perfect_turbine_pdf.exists():
        generate_perfect_turbine_reference_pdf(perfect_turbine_pdf)
    if not target_turbine_pdf.exists():
        generate_target_turbine_report_with_errors(target_turbine_pdf)

    master_turbine_md_path = TEMPLATES_DIR / "Turbine_Thermal_Standard_v1.md"
    if not master_turbine_md_path.exists():
        md_text, _ = convert_pdf_to_structured_markdown(
            perfect_turbine_pdf,
            title_label="Combined-Cycle Turbine Unit #4 (Gold Standard)",
        )
        master_turbine_md_path.write_text(md_text, encoding="utf-8")
