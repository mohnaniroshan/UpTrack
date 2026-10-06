"""
src/diagnose_may_pdf.py

Diagnostic: prints raw pdfplumber output from several Annexure XVIII pages
so you can see exactly how pdfplumber interprets the PDF before trusting
any extraction logic.

Run from project root:
    python src/diagnose_may_pdf.py
"""

import sys
from pathlib import Path

import pdfplumber

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PDF_PATH     = PROJECT_ROOT / "data" / "raw" / "May_Part-2.pdf"

# ── Adjust these to sample different pages ──────────────────────────────────
SAMPLE_PAGES = [458, 459, 460, 461, 462]   # 0-indexed (PDF page = value + 1)
ROWS_PER_PAGE = 30                          # how many raw rows to print per page
# ────────────────────────────────────────────────────────────────────────────

TABLE_SETTINGS = {
    "vertical_strategy":   "lines",
    "horizontal_strategy": "lines",
    "snap_tolerance":      5,
    "join_tolerance":      3,
    "edge_min_length":     10,
}


def divider(char="─", width=80):
    print(char * width)


def inspect_page(pdf, page_num: int):
    if page_num >= len(pdf.pages):
        print(f"  Page {page_num} does not exist in this PDF.")
        return

    page = pdf.pages[page_num]
    divider("═")
    print(f"PAGE {page_num + 1} (0-indexed: {page_num})  "
          f"| width={page.width:.0f}  height={page.height:.0f}")
    divider("═")

    # ── 1. Raw text ─────────────────────────────────────────────────────────
    print("\n[1] RAW PAGE TEXT (first 2000 chars):")
    divider()
    text = page.extract_text() or ""
    print(text[:2000])
    if len(text) > 2000:
        print("... (truncated)")

    # ── 2. Structured table extraction ──────────────────────────────────────
    print(f"\n[2] STRUCTURED TABLE EXTRACTION (strategy: lines):")
    divider()
    tables = page.extract_tables(TABLE_SETTINGS)
    if not tables:
        print("  !! No tables detected with 'lines' strategy.")
        print("  Trying 'text' strategy as fallback …")
        tables = page.extract_tables({
            "vertical_strategy":   "text",
            "horizontal_strategy": "text",
            "snap_tolerance":      3,
        })
        if not tables:
            print("  !! No tables detected with 'text' strategy either.")

    for t_idx, table in enumerate(tables):
        print(f"\n  Table {t_idx + 1} — {len(table)} rows × "
              f"{max(len(r) for r in table) if table else 0} cols")
        divider("-", 60)
        for r_idx, row in enumerate(table[:ROWS_PER_PAGE]):
            print(f"  Row {r_idx:>3}: {row}")
        if len(table) > ROWS_PER_PAGE:
            print(f"  ... ({len(table) - ROWS_PER_PAGE} more rows not shown)")

    # ── 3. Word-level extraction with positions ──────────────────────────────
    print(f"\n[3] WORD-LEVEL EXTRACTION (first {ROWS_PER_PAGE} words with x/y):")
    divider()
    words = page.extract_words(x_tolerance=3, y_tolerance=3)
    for w in words[:ROWS_PER_PAGE]:
        print(f"  x0={w['x0']:>6.1f}  top={w['top']:>6.1f}  "
              f"text={w['text']!r}")
    if len(words) > ROWS_PER_PAGE:
        print(f"  ... ({len(words) - ROWS_PER_PAGE} more words not shown)")

    # ── 4. Chars (shows font sizes — useful for heading detection) ───────────
    print(f"\n[4] UNIQUE FONT SIZES on this page:")
    divider()
    chars = page.chars
    sizes = sorted(set(round(c["size"], 1) for c in chars))
    print(f"  {sizes}")

    bold_chars = [c for c in chars if "Bold" in (c.get("fontname") or "")]
    if bold_chars:
        bold_texts = []
        current = ""
        prev_top = None
        for c in sorted(bold_chars, key=lambda x: (round(x["top"]), x["x0"])):
            if prev_top is None or abs(c["top"] - prev_top) < 3:
                current += c["text"]
            else:
                if current.strip():
                    bold_texts.append(current.strip())
                current = c["text"]
            prev_top = c["top"]
        if current.strip():
            bold_texts.append(current.strip())
        print(f"\n[5] BOLD TEXT on this page (likely headings):")
        divider()
        for bt in bold_texts[:20]:
            print(f"  {bt!r}")


def main():
    if not PDF_PATH.exists():
        print(f"ERROR: PDF not found at {PDF_PATH}", file=sys.stderr)
        sys.exit(1)

    print(f"PDF: {PDF_PATH}")
    print(f"Total pages: ", end="")
    with pdfplumber.open(str(PDF_PATH)) as pdf:
        print(len(pdf.pages))
        for page_num in SAMPLE_PAGES:
            inspect_page(pdf, page_num)

    print("\n" + "═" * 80)
    print("DIAGNOSTIC COMPLETE")
    print("Review the output above, then run src/extract_may_data.py")
    print("═" * 80)


if __name__ == "__main__":
    main()