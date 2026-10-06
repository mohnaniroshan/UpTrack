"""
src/extract_annexure.py

Shared, month-agnostic core for extracting "Annexure XVIII: Details of
Ongoing Projects" from the MoSPI Part-II Flash Report PDFs.

This module contains ALL the extraction logic.  It is parameterised by an
`ExtractionConfig` and driven through `run(config)`.  Month-specific entry
points (extract_may_data.py, extract_april_data.py) are thin wrappers that
build a config and call `run`.  There are NO month-specific values here.

STRUCTURAL NOTE:
    Annexure XVIII is divided by sector/ministry.  Serial numbers restart
    within each sector.  sl_no is NOT globally unique.  The only globally
    unique key is project_row_id (P000001, P000002, ...).
"""

import re
import sys
from pathlib import Path
from collections import defaultdict
from dataclasses import dataclass, field

import pandas as pd
import pdfplumber

from row_splitter import repair_raw_rows


# ─────────────────────────────────────────────────────────────────────────
# Per-month configuration (the ONLY thing that differs between months)
# ─────────────────────────────────────────────────────────────────────────

@dataclass
class ExtractionConfig:
    label:      str            # e.g. "May", "April" — used in printed headers only
    pdf_path:   Path
    out_path:   Path
    start_page: int            # 0-indexed, inclusive
    end_page:   int            # 0-indexed, inclusive (clamped to real PDF length)

    # Optional, month-specific diagnostics.  These only PRINT — they never
    # affect the CSV.  Leave empty to skip.  (May uses these to inspect the
    # anomalies it was investigating; April defaults to none.)
    diagnose_serials: list[str] = field(default_factory=list)   # e.g. ["483"]
    diagnose_pages:   list[int] = field(default_factory=list)   # 1-indexed, e.g. [571]


# ── Output columns ────────────────────────────────────────────────────────
COLUMNS = [
    "project_row_id",
    "sl_no",
    "project_name",
    "date_of_approval",
    "original_date_of_commissioning",
    "revised_date_of_commissioning",
    "anticipated_date_of_commissioning",
    "original_cost_cr",
    "revised_cost_cr",
    "anticipated_cost_cr",
    "cumulative_expenditure_cr",
    "cost_overrun_cr",
    "time_overrun_months",
]

# ─────────────────────────────────────────────────────────────────────────
# Regex constants
# ─────────────────────────────────────────────────────────────────────────

RE_SLNO        = re.compile(r"^\s*(\d{1,4})\.?\s*$")
RE_NUM         = re.compile(r"^-?[\d,]+(?:\.\d+)?$")
RE_DASH        = re.compile(r"^\s*-\s*$")
RE_DATE        = re.compile(
    r"\b(?:\d{1,2}[/\-]\d{2,4}|"
    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*"
    r"[\s'\-\.]*\d{2,4})\b",
    re.IGNORECASE,
)
RE_ROUND       = re.compile(r"\(\s*(-?[\d,]+(?:\.\d+)?|-)\s*\)")
RE_SQUARE      = re.compile(r"\[\s*(-?[\d,]+(?:\.\d+)?|-)\s*\]")
RE_ROUND_DATE  = re.compile(r"\(\s*([^)]+?)\s*\)")
RE_SQUARE_DATE = re.compile(r"\[\s*([^\]]+?)\s*\]")
RE_TOTAL_CELL  = re.compile(
    r"^\s*(sub[\s\-]?total|total|grand\s+total)\s*$", re.IGNORECASE
)
RE_HEADER = re.compile(
    r"sl\.?\s*no\.?\s*$|^\s*project\s+name\s*$|"
    r"date\s+of\s+(?:approval|commission)|"
    r"original\s+cost|revised\s+cost|cumulative\s+exp|"
    r"cost\s+over(?:run)?|time\s+over(?:run)?|"
    r"rs\.?\s*(?:crore|cr\.?)|anticipat",
    re.IGNORECASE,
)
RE_PAGE_NUM       = re.compile(r"^\s*\d{1,4}\s*$")
RE_GRAND_TOTAL    = re.compile(r"grand\s+total", re.IGNORECASE)
RE_SUBTOTAL_LABEL = re.compile(r"sub[\s\-]?total|total", re.IGNORECASE)

STATES = {
    "andhra pradesh","arunachal pradesh","assam","bihar","chhattisgarh",
    "goa","gujarat","haryana","himachal pradesh","jharkhand","karnataka",
    "kerala","madhya pradesh","maharashtra","manipur","meghalaya","mizoram",
    "nagaland","odisha","punjab","rajasthan","sikkim","tamil nadu",
    "telangana","tripura","uttar pradesh","uttarakhand","west bengal",
    "andaman and nicobar","chandigarh","dadra and nagar haveli",
    "daman and diu","delhi","jammu and kashmir","ladakh","lakshadweep",
    "puducherry","multiple states","all india","pan india","various states",
}

RE_SECTOR = re.compile(
    r"^\s*(?:ministry\b|department\b|(?:sub[\s\-]?)?sector\b|railways\b|"
    r"roads?\b|highways?\b|power\b|petroleum\b|steel\b|fertilizers?\b|"
    r"coal\b|telecom\b|shipping\b|civil aviation\b|atomic energy\b|"
    r"space\b|water resources?\b|urban development\b|defence\b|"
    r"implementing\s+agency\b|executing\s+agency\b|nodal\s+agency\b|"
    r"nuclear\b|irrigation\b)",
    re.IGNORECASE,
)

KNOWN_HEADINGS = {
    "a. projects which have been commissioned",
    "b. projects under implementation",
    "projects under implementation",
    "projects which have been commissioned",
    "ongoing projects",
    "details of ongoing projects",
    "annexure xviii",
    "annexure - xviii",
}


# ─────────────────────────────────────────────────────────────────────────
# Section tracker
# ─────────────────────────────────────────────────────────────────────────

@dataclass
class Section:
    name:       str
    start_page: int
    first_sn:   str | None    = None
    last_sn:    str | None    = None
    row_count:  int           = 0
    subtotals:  list[str]     = field(default_factory=list)   # subtotal row texts


# ─────────────────────────────────────────────────────────────────────────
# Cell helpers
# ─────────────────────────────────────────────────────────────────────────

def norm(raw) -> str:
    if raw is None:
        return ""
    return re.sub(r"[ \t]+", " ", str(raw)).strip()


def clean_val(v: str | None) -> str | None:
    if v is None:
        return None
    v = v.strip()
    if not v:
        return None
    if RE_DASH.match(v):
        return None
    if v.upper() in {"NA", "N.A.", "N/A", "NIL", "--", "---", "N.A"}:
        return None
    return v


def parse_numeric_triple(cell: str) -> tuple:
    rm          = RE_ROUND.search(cell)
    revised     = clean_val(rm.group(1)) if rm else None
    sm          = RE_SQUARE.search(cell)
    anticipated = clean_val(sm.group(1)) if sm else None
    remainder   = cell
    if rm:
        remainder = remainder[:rm.start()] + remainder[rm.end():]
    if sm:
        remainder = remainder[:sm.start()] + remainder[sm.end():]
    original = None
    for part in re.split(r"[\n\r]+", remainder):
        part = part.strip()
        if not part:
            continue
        if RE_DASH.match(part):
            break
        if RE_NUM.match(part.replace(",", "")):
            original = clean_val(part)
            break
    if original is None:
        for part in re.split(r"[\n\r\s]+", remainder):
            part = part.strip()
            if part and not RE_DASH.match(part):
                original = clean_val(part)
                break
    return original, revised, anticipated


def parse_date_triple(cell: str) -> tuple:
    rm          = RE_ROUND_DATE.search(cell)
    revised     = clean_val(rm.group(1)) if rm else None
    sm          = RE_SQUARE_DATE.search(cell)
    anticipated = clean_val(sm.group(1)) if sm else None
    remainder   = cell
    if rm:
        remainder = remainder[:rm.start()] + remainder[rm.end():]
    if sm:
        remainder = remainder[:sm.start()] + remainder[sm.end():]
    original = None
    for part in re.split(r"[\n\r]+", remainder):
        part = part.strip()
        if part:
            original = clean_val(part)
            break
    return original, revised, anticipated


# ─────────────────────────────────────────────────────────────────────────
# Row classification
# ─────────────────────────────────────────────────────────────────────────

def slno_in_row(cells: list[str]) -> tuple:
    for i, cell in enumerate(cells):
        first = cell.split("\n")[0].strip()
        if len(first) <= 6:
            m = RE_SLNO.match(first)
            if m:
                return i, m.group(1)
    return None, None


def is_total_row(cells: list[str]) -> bool:
    for cell in cells:
        first = cell.split("\n")[0].strip()
        if first:
            return bool(RE_TOTAL_CELL.match(first))
    return False


def is_grand_total_row(cells: list[str]) -> bool:
    return any(RE_GRAND_TOTAL.search(c) for c in cells)


def is_header_row(cells: list[str]) -> bool:
    non_empty = [c for c in cells if c.strip()]
    if not non_empty:
        return False
    hits = sum(1 for c in non_empty if RE_HEADER.search(c.split("\n")[0]))
    return hits / len(non_empty) >= 0.4


def is_page_number_row(cells: list[str]) -> bool:
    non_empty = [c.strip() for c in cells if c.strip()]
    return len(non_empty) == 1 and bool(RE_PAGE_NUM.match(non_empty[0]))


def is_structural_heading(text: str) -> bool:
    t  = text.strip()
    tl = t.lower()
    if tl in STATES:
        return True
    if RE_SECTOR.match(t):
        return True
    if tl in KNOWN_HEADINGS:
        return True
    return False


# ─────────────────────────────────────────────────────────────────────────
# PDF extraction
# ─────────────────────────────────────────────────────────────────────────

TABLE_CFG_LINES = {
    "vertical_strategy":   "lines",
    "horizontal_strategy": "lines",
    "snap_tolerance":      5,
    "join_tolerance":      3,
    "edge_min_length":     10,
}
TABLE_CFG_TEXT = {
    "vertical_strategy":   "text",
    "horizontal_strategy": "lines",
    "snap_tolerance":      3,
    "join_tolerance":      3,
    "edge_min_length":     10,
}


def extract_raw_rows(
    pdf_path: Path,
    start_page: int,
    end_page: int,
) -> tuple[list[tuple[int, list[str]]], dict]:
    rows:      list[tuple[int, list[str]]] = []
    strat_log: dict[int, str]              = {}

    with pdfplumber.open(str(pdf_path)) as pdf:
        ep = min(end_page, len(pdf.pages) - 1)
        for pn in range(start_page, ep + 1):
            page   = pdf.pages[pn]
            p1     = pn + 1
            tables = page.extract_tables(TABLE_CFG_LINES)
            strat  = "lines"
            if not tables:
                tables = page.extract_tables(TABLE_CFG_TEXT)
                strat  = "text"
            strat_log[p1] = strat
            if tables:
                for table in tables:
                    for row in table:
                        rows.append((p1, [norm(c) for c in row]))
            else:
                # Word-band fallback
                strat_log[p1] = "word-band"
                words = page.extract_words(x_tolerance=3, y_tolerance=3)
                if not words:
                    continue
                bands: dict[int, list] = {}
                for w in words:
                    band = round(w["top"] / 4) * 4
                    bands.setdefault(band, []).append(w["text"])
                for band in sorted(bands):
                    rows.append((p1, [" ".join(bands[band])]))
    return rows, strat_log


def inspect_page_direct(pdf_path: Path, page_num_0idx: int) -> dict:
    """
    Directly inspect one page and return a summary dict.
    Used by the parameterised page diagnostic.
    """
    result = {
        "page_1idx":    page_num_0idx + 1,
        "has_text":     False,
        "text_sample":  "",
        "word_count":   0,
        "table_lines":  [],
        "table_text":   [],
        "words":        [],
        "char_count":   0,
        "font_sizes":   [],
    }
    with pdfplumber.open(str(pdf_path)) as pdf:
        if page_num_0idx >= len(pdf.pages):
            result["text_sample"] = "PAGE DOES NOT EXIST"
            return result
        page = pdf.pages[page_num_0idx]

        raw_text = page.extract_text() or ""
        result["has_text"]    = bool(raw_text.strip())
        result["text_sample"] = raw_text[:1500]
        result["char_count"]  = len(raw_text)

        words = page.extract_words(x_tolerance=3, y_tolerance=3)
        result["word_count"] = len(words)
        result["words"]      = words[:40]

        chars = page.chars
        result["font_sizes"] = sorted(set(round(c["size"], 1) for c in chars))

        for cfg_name, cfg in [("lines", TABLE_CFG_LINES), ("text", TABLE_CFG_TEXT)]:
            tables = page.extract_tables(cfg)
            if tables:
                for t in tables:
                    for row in t:
                        result["table_lines"].append(
                            f"[{cfg_name}] " + str([norm(c) for c in row])
                        )
    return result


# ─────────────────────────────────────────────────────────────────────────
# Grand-total scraper
# ─────────────────────────────────────────────────────────────────────────

def scrape_grand_total(
    raw_rows: list[tuple[int, list[str]]],
) -> tuple[int | None, list[tuple[int, list[str]]]]:
    """
    Scan raw rows for grand-total rows.
    Returns (count_if_found, list_of_gt_rows).
    """
    last_slno: str | None = None
    gt_rows: list = []
    found_count: int | None = None

    for _, cells in raw_rows:
        _, sn = slno_in_row(cells)
        if sn:
            last_slno = sn
        if is_grand_total_row(cells) and not slno_in_row(cells)[0]:
            gt_rows.append(cells)
            # Try to find a printed count in the row
            for cell in cells:
                for line in cell.split("\n"):
                    line = line.strip().replace(",", "")
                    if line.isdigit() and 1000 < int(line) < 5000:
                        found_count = int(line)

    if found_count is None and last_slno and last_slno.isdigit():
        found_count = int(last_slno)

    return found_count, gt_rows


# ─────────────────────────────────────────────────────────────────────────
# Logical row assembly + section tracking
# ─────────────────────────────────────────────────────────────────────────

def assemble_logical_rows(
    raw_rows: list[tuple[int, list[str]]],
    start_page: int,
) -> tuple[list[tuple[int, list[str], str]], list, list[Section]]:
    """
    Returns:
        logical   – list of (page, cells, current_section_name)
        skip_log  – list of (reason, page, cells)
        sections  – list of Section objects in encounter order

    `start_page` (0-indexed) is used only to label the display-only
    "(preamble)" section's start page; it does not affect the CSV.
    """
    logical:       list[tuple[int, list[str], str]] = []
    current_cells: list[str] | None = None
    current_page:  int              = 0
    skip_log:      list             = []

    # Section tracking
    sections: list[Section]   = []
    cur_section: Section      = Section(name="(preamble)", start_page=start_page + 1)

    def _close_section_row(sn: str):
        """Update last_sn on the current section."""
        if sn:
            if cur_section.first_sn is None:
                cur_section.first_sn = sn
            cur_section.last_sn = sn
            cur_section.row_count += 1

    def _new_section(name: str, page: int):
        nonlocal cur_section
        if cur_section.row_count > 0 or cur_section.name != "(preamble)":
            sections.append(cur_section)
        cur_section = Section(name=name, start_page=page)

    for page, phys in raw_rows:
        # ── Grand-total rows ───────────────────────────────────────────────
        if is_grand_total_row(phys) and not slno_in_row(phys)[0]:
            skip_log.append(("grand_total", page, phys))
            full = " ".join(c for c in phys if c)
            cur_section.subtotals.append(f"GRAND TOTAL [p{page}]: {full[:80]}")
            continue

        # ── Noise ──────────────────────────────────────────────────────────
        if is_page_number_row(phys):
            skip_log.append(("page_number", page, phys))
            continue
        if is_header_row(phys):
            skip_log.append(("header", page, phys))
            continue

        # ── Subtotal / total rows (NOT grand total) ────────────────────────
        if is_total_row(phys):
            skip_log.append(("total", page, phys))
            full = " ".join(c for c in phys if c)
            cur_section.subtotals.append(f"[p{page}]: {full[:80]}")
            continue

        idx, slno = slno_in_row(phys)

        if slno is not None:
            # ── New project record ─────────────────────────────────────────
            if current_cells is not None:
                logical.append((current_page, current_cells, cur_section.name))
                _close_section_row(slno_in_row(current_cells)[1] or "")
            current_cells = list(phys)
            current_page  = page
            # We'll close this row when the NEXT row starts; track sn now
            # for section first_sn
            if cur_section.first_sn is None:
                cur_section.first_sn = slno

        else:
            full_text = " ".join(c for c in phys if c).strip()
            if not full_text:
                continue

            non_empty = [c for c in phys if c.strip()]

            # ── Structural heading → new section ───────────────────────────
            if len(non_empty) == 1 and is_structural_heading(non_empty[0]):
                skip_log.append(("heading", page, phys))
                heading_text = non_empty[0].strip()
                # Flush current logical row before opening new section
                if current_cells is not None:
                    logical.append((current_page, current_cells, cur_section.name))
                    _, sn2 = slno_in_row(current_cells)
                    _close_section_row(sn2 or "")
                    current_cells = None
                _new_section(heading_text, page)
                continue

            if current_cells is None:
                skip_log.append(("pre_first_record", page, phys))
                continue

            # ── Continuation row ───────────────────────────────────────────
            for i, cell in enumerate(phys):
                if not cell.strip():
                    continue
                while len(current_cells) <= i:
                    current_cells.append("")
                if current_cells[i]:
                    current_cells[i] = current_cells[i] + "\n" + cell
                else:
                    current_cells[i] = cell

    # Flush last record
    if current_cells is not None:
        logical.append((current_page, current_cells, cur_section.name))
        _, sn2 = slno_in_row(current_cells)
        _close_section_row(sn2 or "")

    # Close final section
    if cur_section.row_count > 0:
        sections.append(cur_section)

    return logical, skip_log, sections


# ─────────────────────────────────────────────────────────────────────────
# Field extraction
# ─────────────────────────────────────────────────────────────────────────

def extract_fields(
    page:     int,
    row:      list[str],
    section:  str,
    row_num:  int,
    skip_log: list,
) -> dict | None:
    idx, sl_no = slno_in_row(row)
    if sl_no is None:
        skip_log.append(("no_slno", page, row))
        return None

    def get(i: int) -> str:
        return row[i].strip() if i < len(row) else ""

    base = idx

    name_raw     = get(base + 1)
    project_name = re.sub(r"\s*\n\s*", " ", name_raw).strip() if name_raw else None
    if not project_name:
        project_name = None

    has_data = any(get(base + k).strip() for k in range(2, 6))
    if project_name and is_structural_heading(project_name) and not has_data:
        skip_log.append(("heading_name_no_data", page, row))
        return None

    approval_raw                   = get(base + 2)
    comm_raw                       = get(base + 3)
    cost_raw                       = get(base + 4)
    cumul_raw                      = get(base + 5)

    approval_val                   = clean_val(approval_raw.split("\n")[0]) if approval_raw else None
    orig_comm, rev_comm, ant_comm  = parse_date_triple(comm_raw)
    orig_cost, rev_cost, ant_cost  = parse_numeric_triple(cost_raw)
    cum_exp,   cost_ovr, time_ovr  = parse_numeric_triple(cumul_raw)

    return {
        "project_row_id":                     f"P{row_num:06d}",
        "sl_no":                              sl_no,
        "project_name":                       project_name,
        "date_of_approval":                   approval_val,
        "original_date_of_commissioning":     orig_comm,
        "revised_date_of_commissioning":      rev_comm,
        "anticipated_date_of_commissioning":  ant_comm,
        "original_cost_cr":                   orig_cost,
        "revised_cost_cr":                    rev_cost,
        "anticipated_cost_cr":                ant_cost,
        "cumulative_expenditure_cr":          cum_exp,
        "cost_overrun_cr":                    cost_ovr,
        "time_overrun_months":                time_ovr,
    }


# ─────────────────────────────────────────────────────────────────────────
# Diagnostics  (print-only — never affect the CSV)
# ─────────────────────────────────────────────────────────────────────────

def print_section_table(sections: list[Section]) -> None:
    W = 90
    print(f"\n{'─'*W}")
    print(f"  SECTION STRUCTURE OF ANNEXURE XVIII")
    print(f"{'─'*W}")
    header = (
        f"  {'#':>3}  {'Section':<45}  {'Pg':>4}  "
        f"{'First SN':>8}  {'Last SN':>7}  {'Rows':>5}"
    )
    print(header)
    print(f"  {'─'*3}  {'─'*45}  {'─'*4}  {'─'*8}  {'─'*7}  {'─'*5}")
    total_rows = 0
    for i, s in enumerate(sections, 1):
        name_trunc = s.name[:45]
        print(
            f"  {i:>3}  {name_trunc:<45}  {s.start_page:>4}  "
            f"{s.first_sn or '':>8}  {s.last_sn or '':>7}  {s.row_count:>5}"
        )
        total_rows += s.row_count
    print(f"  {'─'*3}  {'─'*45}  {'─'*4}  {'─'*8}  {'─'*7}  {'─'*5}")
    print(f"  {'TOTAL':<51}  {'':>8}  {'':>7}  {total_rows:>5}")
    print(f"\n  Sum of section row counts: {total_rows}")


def diagnose_serial(
    raw_rows: list[tuple[int, list[str]]],
    logical:  list[tuple[int, list[str], str]],
    target:   str,
) -> None:
    W = 90
    print(f"\n{'─'*W}")
    print(f"  DIAGNOSTIC: sl_no = {target}")
    print(f"{'─'*W}")

    phys_hits = [
        (i, pg, cells) for i, (pg, cells) in enumerate(raw_rows)
        if any(
            RE_SLNO.match(c.split("\n")[0].strip()) and
            RE_SLNO.match(c.split("\n")[0].strip()).group(1) == target
            for c in cells
        )
    ]
    print(f"  Physical rows with sl_no={target}: {len(phys_hits)}")
    for ridx, pg, cells in phys_hits:
        print(f"\n  row[{ridx}] page={pg}")
        for ci, c in enumerate(cells):
            print(f"    cell[{ci}]: {c!r}")
        # Context
        lo = max(0, ridx - 3)
        hi = min(len(raw_rows) - 1, ridx + 4)
        print(f"\n  Context (raw_rows[{lo}..{hi}]):")
        for j in range(lo, hi + 1):
            pg2, c2 = raw_rows[j]
            m = " >>>" if j == ridx else "    "
            print(f"  {m} [{j}] p={pg2}  {[c[:55] for c in c2]}")

    log_hits = [
        (pg, cells, sec) for pg, cells, sec in logical
        if slno_in_row(cells)[1] == target
    ]
    print(f"\n  Logical rows with sl_no={target}: {len(log_hits)}")
    for pg, cells, sec in log_hits:
        print(f"  section={sec!r}  page={pg}")
        for ci, c in enumerate(cells):
            print(f"    cell[{ci}]: {c!r}")


def diagnose_page(
    pdf_path: Path, raw_rows: list, strat_log: dict, page_1idx: int
) -> None:
    W = 90
    P1 = page_1idx
    P0 = P1 - 1   # 0-indexed
    print(f"\n{'─'*W}")
    print(f"  DIAGNOSTIC: page {P1}  (strategy={strat_log.get(P1,'?')})")
    print(f"{'─'*W}")

    result = inspect_page_direct(pdf_path, P0)
    print(f"  has_text   : {result['has_text']}")
    print(f"  char_count : {result['char_count']}")
    print(f"  word_count : {result['word_count']}")
    print(f"  font_sizes : {result['font_sizes']}")

    print(f"\n  Raw text (first 1500 chars):")
    print(f"  {result['text_sample'][:1500]}")

    print(f"\n  Table rows found by both strategies:")
    if result["table_lines"]:
        for tl in result["table_lines"]:
            print(f"    {tl}")
    else:
        print(f"    (none)")

    print(f"\n  First 40 words with positions:")
    for w in result["words"]:
        print(f"    x0={w['x0']:>6.1f}  top={w['top']:>6.1f}  text={w['text']!r}")

    page_raw = [(i, pg, c) for i, (pg, c) in enumerate(raw_rows) if pg == P1]
    print(f"\n  Physical rows from page {P1} in raw_rows: {len(page_raw)}")
    for i, pg, cells in page_raw:
        print(f"    row[{i}]  {[c[:60] for c in cells]}")

    # Check pages around the target for context
    for neighbour in [P1 - 1, P1 + 1]:
        n_rows = [(i, pg, c) for i, (pg, c) in enumerate(raw_rows) if pg == neighbour]
        print(f"\n  Page {neighbour}: {len(n_rows)} physical rows (first 5):")
        for i, pg, cells in n_rows[:5]:
            print(f"    row[{i}]  {[c[:60] for c in cells]}")


def diagnose_repeated_slnos(
    logical: list[tuple[int, list[str], str]],
) -> None:
    W = 90
    seen: dict[str, list] = defaultdict(list)
    for pg, cells, sec in logical:
        _, sn = slno_in_row(cells)
        if sn:
            name = cells[1].split("\n")[0][:50] if len(cells) > 1 else ""
            seen[sn].append((pg, sec, name))

    repeated = {sn: v for sn, v in seen.items() if len(v) > 1}
    print(f"\n{'─'*W}")
    print(f"  DIAGNOSTIC: sl_no values appearing more than once")
    print(f"  Total repeated sl_nos: {len(repeated)}")
    print(f"  (Expected: sector-level serial numbering restarts)")
    print(f"{'─'*W}")

    for sn in sorted(repeated, key=lambda x: int(x) if x.isdigit() else 0)[:40]:
        entries = repeated[sn]
        print(f"\n  sl_no={sn}  ({len(entries)} occurrences):")
        for pg, sec, name in entries:
            print(f"    page={pg:>4}  section={sec[:40]!r:<42}  name={name!r}")

    if len(repeated) > 40:
        print(f"\n  ... {len(repeated)-40} more repeated sl_nos not shown.")

    # Check: do ALL repeats occur in different sections?
    all_in_diff_sections = True
    cross_section_same = []
    for sn, entries in repeated.items():
        secs = [e[1] for e in entries]
        if len(set(secs)) < len(secs):
            all_in_diff_sections = False
            cross_section_same.append((sn, entries))

    if all_in_diff_sections:
        print(f"\n  ✓ ALL repeated sl_nos occur in DIFFERENT sections.")
        print(f"    This confirms serial numbering restarts per sector.")
    else:
        print(f"\n  !! {len(cross_section_same)} sl_nos repeat within the SAME section:")
        for sn, entries in cross_section_same[:10]:
            print(f"    sl_no={sn}: {entries}")


def diagnose_grand_totals(gt_rows: list, raw_rows: list) -> None:
    W = 90
    print(f"\n{'─'*W}")
    print(f"  DIAGNOSTIC: Grand-total rows ({len(gt_rows)})")
    print(f"{'─'*W}")
    for cells in gt_rows:
        print(f"  cells: {[c[:70] for c in cells]}")


# ─────────────────────────────────────────────────────────────────────────
# Validation
# ─────────────────────────────────────────────────────────────────────────

def validate_and_report(
    df:              pd.DataFrame,
    all_skip_log:    list,
    strat_log:       dict,
    source_total:    int | None,
    sections:        list[Section],
    pages_with_rows: dict[int, int],
) -> bool:

    ok = True
    n  = len(df)
    W  = 70

    print("\n" + "=" * W)
    print("EXTRACTION VALIDATION REPORT")
    print("=" * W)

    # ── Row count ──────────────────────────────────────────────────────────
    section_sum = sum(s.row_count for s in sections)
    print(f"\n  Logical rows extracted              : {n}")
    print(f"  Sum of section row counts           : {section_sum}")
    if n == section_sum:
        print(f"  Row count matches section sum  ✓")
    else:
        print(f"  !! Row count ({n}) != section sum ({section_sum})")
        ok = False

    if source_total is not None:
        print(f"  Source grand-total figure           : {source_total}")
        diff = n - source_total
        if diff == 0:
            print(f"  Row count matches source total  ✓")
        else:
            sign = "+" if diff > 0 else ""
            print(f"  !! Differs from source total by {sign}{diff}")
            # Not marking ok=False here: source total may refer to
            # a different count (e.g., only commissioned projects)

    # ── project_row_id uniqueness ──────────────────────────────────────────
    dup_ids = df["project_row_id"].duplicated().sum()
    if dup_ids:
        print(f"\n  !! Duplicate project_row_id: {dup_ids}")
        ok = False
    else:
        print(f"\n  project_row_id: all {n} unique  ✓")

    # ── sl_no stats ────────────────────────────────────────────────────────
    slno_vc      = df["sl_no"].value_counts()
    n_unique_sl  = df["sl_no"].nunique()
    n_repeated   = int((slno_vc > 1).sum())
    print(f"\n  Unique sl_no values                 : {n_unique_sl}")
    print(f"  sl_no values appearing >1 time      : {n_repeated}")
    print(f"  (Repeats are expected: sector restarts)")

    if n_repeated > 0:
        print(f"\n  Top repeated sl_nos:")
        for sn, cnt in slno_vc[slno_vc > 1].head(8).items():
            names = df[df["sl_no"] == sn]["project_name"].tolist()
            print(f"    sl_no={sn:>5}  count={cnt}  "
                  f"names={[str(nm)[:35] for nm in names]}")

    # ── Missing project names ──────────────────────────────────────────────
    no_name = df[df["project_name"].isna()]
    print(f"\n  Rows with missing project_name      : {len(no_name)}")
    if len(no_name):
        print(f"  (Kept as-is — name absent in source PDF)")
        print(no_name[["project_row_id", "sl_no",
                        "date_of_approval", "original_cost_cr"]].to_string(index=False))

    # ── Column count ───────────────────────────────────────────────────────
    if len(df.columns) == 13:
        print(f"\n  Column count: 13  ✓")
    else:
        print(f"\n  !! Column count: {len(df.columns)}  (expected 13)")
        ok = False

    # ── Skip-reason breakdown ──────────────────────────────────────────────
    rc: dict[str, int] = defaultdict(int)
    for e in all_skip_log:
        rc[e[0]] += 1
    print(f"\n  Skip reasons (total {len(all_skip_log)}):")
    for reason, count in sorted(rc.items(), key=lambda x: -x[1]):
        print(f"    {reason:<35} {count:>5}")

    # ── Strategies ────────────────────────────────────────────────────────
    wb = [p for p, s in strat_log.items() if s == "word-band"]
    # A word-band page only matters if it actually produced physical rows.
    # A blank page (0 words) triggers the fallback harmlessly and yields
    # nothing — that is not a data risk.
    wb_with_rows = [p for p in wb if pages_with_rows.get(p, 0) > 0]
    wb_empty     = [p for p in wb if pages_with_rows.get(p, 0) == 0]
    if wb_with_rows:
        print(f"\n  !! Word-band fallback pages WITH rows: {wb_with_rows}")
        ok = False
    else:
        if wb_empty:
            print(f"\n  Word-band fallback on blank page(s) {wb_empty} "
                  f"(0 rows — harmless)  ✓")
        else:
            print(f"\n  All pages: structured extraction  ✓")

    # ── Missing values ────────────────────────────────────────────────────
    SPARSE_OK = {
        "revised_cost_cr", "anticipated_cost_cr",
        "cost_overrun_cr", "time_overrun_months",
        "revised_date_of_commissioning",
        "anticipated_date_of_commissioning",
    }
    print(f"\n  Missing value % per column:")
    for col in COLUMNS[1:]:
        mv  = df[col].isna().sum()
        pct = mv / n * 100 if n else 0
        bar = "█" * int(pct / 5)
        flag = ""
        if pct > 90 and col not in SPARSE_OK:
            flag = "  ← CHECK"
            ok   = False
        print(f"    {col:<45} {pct:5.1f}%  {bar}{flag}")

    # ── Revised / anticipated dates ───────────────────────────────────────
    has_rev = df["revised_date_of_commissioning"].notna()
    has_ant = df["anticipated_date_of_commissioning"].notna()
    print(f"\n  Rows with revised commissioning date    : {has_rev.sum()}")
    print(f"  Rows with anticipated commissioning date: {has_ant.sum()}")
    if has_rev.sum() == 0:
        print("  !! revised_date_of_commissioning 100% empty"); ok = False
    if has_ant.sum() == 0:
        print("  !! anticipated_date_of_commissioning 100% empty"); ok = False

    sample = df[has_rev | has_ant][
        ["project_row_id", "sl_no", "project_name",
         "original_date_of_commissioning",
         "revised_date_of_commissioning",
         "anticipated_date_of_commissioning"]
    ].head(5)
    if not sample.empty:
        pd.set_option("display.max_colwidth", 25)
        print(f"\n  Sample rows with revised/anticipated dates:")
        print(sample.to_string(index=False))

    # ── Leakage check ─────────────────────────────────────────────────────
    leaked = df[df["project_name"].str.fullmatch(
        r"\s*(sub[\s\-]?total|total|grand\s+total)\s*",
        case=False, na=False,
    )]
    if len(leaked):
        print(f"\n  !! {len(leaked)} total rows leaked:")
        print(leaked[["project_row_id","sl_no","project_name"]].to_string(index=False))
        ok = False
    else:
        print(f"\n  No total/subtotal rows leaked  ✓")

    # ── Representative rows ───────────────────────────────────────────────
    pd.set_option("display.width", 240)
    pd.set_option("display.max_columns", None)
    pd.set_option("display.max_colwidth", 35)

    print(f"\n  First 5 rows:")
    print(df.head(5).to_string(index=False))
    mid = n // 2
    print(f"\n  Middle 3 rows (index {mid}):")
    print(df.iloc[mid:mid+3].to_string(index=False))
    print(f"\n  Last 3 rows:")
    print(df.tail(3).to_string(index=False))

    print("\n" + "=" * W)
    return ok


# ─────────────────────────────────────────────────────────────────────────
# Entry point — parameterised by ExtractionConfig
# ─────────────────────────────────────────────────────────────────────────

def run(config: ExtractionConfig) -> None:
    # Force UTF-8 output so the box-drawing characters in the diagnostic
    # tables do not crash on the Windows console (cp1252 default).
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

    if not config.pdf_path.exists():
        print(f"ERROR: PDF not found at {config.pdf_path}", file=sys.stderr)
        sys.exit(1)

    config.out_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"MONTH  : {config.label}")
    print(f"PDF    : {config.pdf_path}")
    print(f"Pages  : {config.start_page + 1}–{config.end_page + 1} (1-indexed)")

    # ── 1. Raw extraction ──────────────────────────────────────────────────
    print("\n[1/5] Extracting raw rows …")
    raw_rows, strat_log = extract_raw_rows(
        config.pdf_path, config.start_page, config.end_page
    )
    print(f"      Physical rows        : {len(raw_rows)}")
    wb = [p for p, s in strat_log.items() if s == "word-band"]
    if wb:
        print(f"      Word-band pages      : {wb}")

    # ── 1b. Repair mangled rows (pattern-based) ────────────────────────────
    # pdfplumber's table extraction merges/glues/drops a few rows.  Repair
    # them from word coordinates BEFORE logical assembly.  See row_splitter.py.
    print("\n[1b/5] Repairing mangled physical rows …")
    raw_rows, repair_log = repair_raw_rows(raw_rows, config.pdf_path)
    print(f"      Physical rows (repaired): {len(raw_rows)}")
    for entry in repair_log:
        print(f"        • {entry}")

    # How many physical rows each page contributed (used to tell a harmless
    # word-band fallback on a blank page from a risky one on a real page).
    pages_with_rows: dict[int, int] = defaultdict(int)
    for pg, _ in raw_rows:
        pages_with_rows[pg] += 1

    # ── 2. Grand-total scrape ──────────────────────────────────────────────
    print("\n[2/5] Scanning for source grand total …")
    source_total, gt_rows = scrape_grand_total(raw_rows)
    print(f"      Source grand total   : "
          f"{source_total if source_total else 'not found'}")

    # ── 3. Assemble logical rows ───────────────────────────────────────────
    print("\n[3/5] Assembling logical rows …")
    logical, assemble_skip, sections = assemble_logical_rows(
        raw_rows, config.start_page
    )
    print(f"      Logical rows         : {len(logical)}")
    print(f"      Sections identified  : {len(sections)}")

    # ── 4. Diagnostics ────────────────────────────────────────────────────
    print("\n[4/5] Running diagnostics …")

    print_section_table(sections)
    diagnose_grand_totals(gt_rows, raw_rows)
    diagnose_repeated_slnos(logical)
    for tgt in config.diagnose_serials:
        diagnose_serial(raw_rows, logical, tgt)
    for pg in config.diagnose_pages:
        diagnose_page(config.pdf_path, raw_rows, strat_log, pg)

    # ── 5. Parse, validate, write ──────────────────────────────────────────
    print("\n[5/5] Parsing fields, validating, writing …")
    parse_skip: list = []
    records:    list = []
    row_counter = 1

    for page, row, section in logical:
        result = extract_fields(page, row, section, row_counter, parse_skip)
        if result:
            records.append(result)
            row_counter += 1

    all_skip = assemble_skip + parse_skip
    print(f"      Records parsed       : {len(records)}")
    print(f"      Skipped (assembly)   : {len(assemble_skip)}")
    print(f"      Skipped (parse)      : {len(parse_skip)}")

    if not records:
        print("FATAL: Zero records extracted.", file=sys.stderr)
        sys.exit(1)

    df = pd.DataFrame(records, columns=COLUMNS)
    df.replace("", pd.NA, inplace=True)

    extraction_ok = validate_and_report(
        df, all_skip, strat_log, source_total, sections, pages_with_rows
    )

    df.to_csv(config.out_path, index=False)
    print(f"\nCSV written → {config.out_path}  ({len(df)} rows × {len(df.columns)} cols)")

    if not extraction_ok:
        print(
            "\nWARNING: One or more validation checks failed — review above.",
            file=sys.stderr,
        )
        sys.exit(1)

    print("\nExtraction complete — all validation checks passed.")


if __name__ == "__main__":
    print(
        "extract_annexure.py is a shared module — run a month wrapper instead:\n"
        "    python src/extract_may_data.py\n"
        "    python src/extract_april_data.py",
        file=sys.stderr,
    )
    sys.exit(2)
