"""
src/extract_may_data.py

Thin wrapper: extracts Annexure XVIII from the MoSPI May Part-II PDF.
All logic lives in extract_annexure.py — this file only supplies May's
parameters.  Output is data/may_projects.csv.

STRUCTURAL NOTE:
    Serial numbers restart within each sector.  sl_no is NOT globally
    unique.  The only globally unique key is project_row_id.

Run from project root:
    python src/extract_may_data.py
"""

from pathlib import Path

from extract_annexure import ExtractionConfig, run

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ── May parameters ─────────────────────────────────────────────────────────
# Annexure XVIII ("Details of Ongoing Projects") begins at PDF page 462.
# Pages 459-461 are the tail of the PREVIOUS annexure and must be excluded,
# otherwise their serial numbers (170-225) collide with Annexure XVIII's own
# serials.  END_PAGE is clamped to the real PDF length at runtime.
MAY = ExtractionConfig(
    label      = "May",
    pdf_path   = PROJECT_ROOT / "data" / "raw" / "May_Part-2.pdf",
    out_path   = PROJECT_ROOT / "data" / "may_projects.csv",
    start_page = 461,   # 0-indexed → PDF page 462
    end_page   = 575,   # 0-indexed; clamped to PDF length (571 pages)
    # Anomalies investigated during the May build (print-only diagnostics):
    diagnose_serials = ["483"],
    diagnose_pages   = [571],
)


if __name__ == "__main__":
    run(MAY)
