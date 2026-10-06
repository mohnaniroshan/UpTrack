"""
src/extract_april_data.py

Thin wrapper: extracts Annexure XVIII from the MoSPI April Part-II PDF.
All logic lives in extract_annexure.py — this file only supplies April's
parameters.  Output is data/april_projects.csv.

STRUCTURAL NOTE:
    Serial numbers restart within each sector.  sl_no is NOT globally
    unique.  The only globally unique key is project_row_id.

Run from project root:
    python src/extract_april_data.py
"""

from pathlib import Path

from extract_annexure import ExtractionConfig, run

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ── April parameters ───────────────────────────────────────────────────────
# Annexure XVIII begins at PDF page 462 (pages 460-461 are the previous
# annexure, "North East Projects", whose serials would otherwise collide).
# The table ends on page 571.  Requested range: PDF pages 462–571 inclusive.
APRIL = ExtractionConfig(
    label      = "April",
    pdf_path   = PROJECT_ROOT / "data" / "raw" / "April_Part-II_List_of_tables.pdf",
    out_path   = PROJECT_ROOT / "data" / "april_projects.csv",
    start_page = 461,   # 0-indexed → PDF page 462
    end_page   = 570,   # 0-indexed → PDF page 571 (inclusive)
    # No month-specific diagnostics: rely on the standard section /
    # repeated-slno / grand-total diagnostics and the row_splitter repair log.
    diagnose_serials = [],
    diagnose_pages   = [],
)


if __name__ == "__main__":
    run(APRIL)
