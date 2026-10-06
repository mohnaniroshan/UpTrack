"""
src/row_splitter.py

Recovers project rows that pdfplumber's TABLE extraction mangled in the
May Part-II Annexure XVIII.  Draft for review — NOT yet wired into the
main extractor.

Three anomaly patterns were found by direct inspection of the PDF:

  PATTERN 1 — GLUED SERIAL+NAME  (e.g. sl_no 1785)
      The serial number and project name were extracted into ONE cell:
          cell[0] = '1785 NEW WORK FOR CONSTRUCTION\nOF METRO RAILWAY ...'
          cell[1] = ''
      Fix: peel the leading integer off cell[0] into its own serial,
      move the remaining text into the name cell.  Pure string surgery,
      completely safe — all data is present and in the right columns.

  PATTERN 2 — DOUBLE-SERIAL MERGE  (e.g. sl_no 919 + 920)
      Two consecutive projects were merged into one table row, and part
      of the second project's data spilled into the FOLLOWING physical
      row.  The merged strings cannot be un-interleaved reliably.
      Fix: re-read the two projects directly from WORD COORDINATES on
      the page (proven to separate them cleanly), replacing the bad
      row(s).

  PATTERN 3 — ORPHAN DATA ROW  (e.g. sl_no 175, 1353)
      A project's data row exists, but its serial number AND project
      name are ABSENT from the PDF's text layer entirely (verified at
      char level — no words exist in the left columns at that y-band).
      Fix: keep the data, infer the serial from position (it sits
      between N and N+2, so it is N+1), and leave project_name EMPTY.
      We do NOT fabricate a name.

Design choice
-------------
Patterns 2 and 3 are handled by re-extracting the affected page region
from word coordinates rather than by string-splitting pdfplumber's merged
cells, because the merged strings are lossy/interleaved.  This is a
targeted reconstruction of a handful of known-bad regions, not a rewrite
of the extraction pipeline.
"""

import re
from pathlib import Path

import pdfplumber

# Column x-boundaries for Annexure XVIII, read off the verified word
# coordinates.  A word's x0 decides which of the 6 logical columns it
# belongs to.  (Left edge of each column.)
#   serial : x0 ~ 31
#   name   : x0 ~ 59 .. ~205
#   approval(date): x0 ~ 215
#   commissioning : x0 ~ 300..340
#   cost          : x0 ~ 405..430
#   cumulative    : x0 ~ 514..527
COL_BOUNDS = [
    (0,   50,  "serial"),
    (50,  210, "name"),
    (210, 295, "approval"),
    (295, 400, "commissioning"),
    (400, 505, "cost"),
    (505, 999, "cumulative"),
]

RE_LEADING_SERIAL = re.compile(r"^\s*(\d{1,4})\s+(\S.*)$", re.DOTALL)


def col_of(x0: float) -> str | None:
    for lo, hi, name in COL_BOUNDS:
        if lo <= x0 < hi:
            return name
    return None


# ─────────────────────────────────────────────────────────────────────────
# PATTERN 1 — glued serial + name (safe string surgery)
# ─────────────────────────────────────────────────────────────────────────

def split_glued_serial(cells: list[str]) -> list[str] | None:
    """
    If cell[0] is like '1785 NEW WORK...\\nMORE NAME' and cell[1] is empty,
    peel the leading integer into cell[0] and move the text into cell[1].
    Returns a NEW cell list, or None if the row doesn't match.
    """
    if not cells or not cells[0]:
        return None
    first_line = cells[0].split("\n")[0]
    m = RE_LEADING_SERIAL.match(first_line)
    if not m:
        return None
    # Only treat as glued if the name column is empty (otherwise it's a
    # normal row that merely starts with its serial).
    if len(cells) > 1 and cells[1].strip():
        return None
    serial = m.group(1)
    # Rebuild name: remainder of first line + any further lines in cell[0]
    rest_lines = cells[0].split("\n")
    rest_lines[0] = m.group(2)
    name = "\n".join(rest_lines)
    new = list(cells)
    new[0] = serial
    # ensure a name slot exists
    while len(new) < 2:
        new.append("")
    new[1] = name
    return new


# ─────────────────────────────────────────────────────────────────────────
# PATTERNS 2 & 3 — coordinate-based reconstruction of a page band
# ─────────────────────────────────────────────────────────────────────────

def reconstruct_rows_by_words(
    pdf_path: Path,
    page_1idx: int,
    top_lo: float,
    top_hi: float,
    y_tol: float = 6.0,
) -> list[dict]:
    """
    Re-read a vertical band of one page directly from word coordinates and
    group words into logical projects.

    A NEW project starts on any text-line that has a word in the 'serial'
    column.  Lines with no serial word are either:
        - continuations of the current project's name/data, OR
        - (PATTERN 3) an orphan data line with no serial in the text layer.
    We return one dict per detected line-group with its column contents;
    the caller decides how to stitch them into projects.

    Returns a list of dicts:
        {'top': float, 'serial': str|None, 'cols': {colname: [words...]}}
    """
    out: list[dict] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        page = pdf.pages[page_1idx - 1]
        words = [
            w for w in page.extract_words(x_tolerance=2, y_tolerance=2)
            if top_lo <= w["top"] < top_hi
        ]

    # Group words into text-lines by y (top) proximity.
    words.sort(key=lambda w: (w["top"], w["x0"]))
    lines: list[list[dict]] = []
    for w in words:
        if lines and abs(w["top"] - lines[-1][0]["top"]) <= y_tol:
            lines[-1].append(w)
        else:
            lines.append([w])

    for line in lines:
        cols: dict[str, list[str]] = {}
        serial = None
        for w in sorted(line, key=lambda x: x["x0"]):
            c = col_of(w["x0"])
            if c is None:
                continue
            cols.setdefault(c, []).append(w["text"])
            if c == "serial":
                serial = w["text"]
        out.append({
            "top": line[0]["top"],
            "serial": serial,
            "cols": {k: " ".join(v) for k, v in cols.items()},
        })
    return out


# ─────────────────────────────────────────────────────────────────────────
# Stitching line-groups into 6-column cells
# ─────────────────────────────────────────────────────────────────────────

# The 6 output columns, in order, mapped from the coordinate reader's
# column names.
_CELL_ORDER = ["serial", "name", "approval", "commissioning", "cost", "cumulative"]


def _groups_to_projects(groups: list[dict]) -> list[list[str]]:
    """
    Turn a list of line-groups (from reconstruct_rows_by_words) into a list
    of 6-cell project rows.

    A new project begins at each group that has a 'serial'.  Groups WITHOUT
    a serial are continuation lines: their column values are appended (with
    a newline) to the current project's matching cell.

    If the first group(s) have no serial (an orphan data block that appears
    before any serial in the band), they still start a project with an empty
    serial — the caller assigns the position-inferred serial afterwards.
    """
    projects: list[dict[str, list[str]]] = []

    def _new_project() -> dict[str, list[str]]:
        p = {c: [] for c in _CELL_ORDER}
        projects.append(p)
        return p

    cur: dict[str, list[str]] | None = None
    for g in groups:
        starts_project = g["serial"] is not None or cur is None
        if starts_project:
            cur = _new_project()
            if g["serial"] is not None:
                cur["serial"].append(g["serial"])
        for col in ("name", "approval", "commissioning", "cost", "cumulative"):
            v = g["cols"].get(col, "")
            if v:
                cur[col].append(v)

    rows: list[list[str]] = []
    for p in projects:
        rows.append(["\n".join(p[c]) for c in _CELL_ORDER])
    return rows


# ─────────────────────────────────────────────────────────────────────────
# Orchestrator — detect anomalies and repair raw_rows
# ─────────────────────────────────────────────────────────────────────────

RE_INT_ONLY   = re.compile(r"^\d{1,4}$")
RE_BARE_DATE  = re.compile(r"^\d{1,2}/\d{4}$")   # plain month/year, no brackets


def _is_double_serial(cells: list[str]) -> bool:
    """cell[0] is two-plus integers stacked, e.g. '919\\n920'."""
    if not cells or not cells[0]:
        return False
    lines = [l.strip() for l in cells[0].split("\n") if l.strip()]
    return len(lines) >= 2 and all(RE_INT_ONLY.match(l) for l in lines)


def _is_glued(cells: list[str]) -> bool:
    """cell[0] starts with a serial glued to text, and name cell is empty."""
    if not cells or not cells[0]:
        return False
    if not RE_LEADING_SERIAL.match(cells[0].split("\n")[0]):
        return False
    return not (len(cells) > 1 and cells[1].strip())


def _is_orphan(cells: list[str]) -> bool:
    """
    Blank serial AND blank name, but a BARE approval date present.
    The bare-date test is what separates the 2 real orphan projects
    (175, 1353) from ordinary bracketed continuation lines.
    """
    c0 = cells[0].strip() if len(cells) > 0 else ""
    c1 = cells[1].strip() if len(cells) > 1 else ""
    appr = cells[2].split("\n")[0].strip() if len(cells) > 2 else ""
    return c0 == "" and c1 == "" and bool(RE_BARE_DATE.match(appr))


def repair_raw_rows(
    raw_rows: list[tuple[int, list[str]]],
    pdf_path: Path,
) -> tuple[list[tuple[int, list[str]]], list[str]]:
    """
    Return (repaired_rows, log).  Pattern-based; does not depend on hard-coded
    page numbers.  Only the three verified signatures are touched; everything
    else is passed through unchanged.
    """
    log: list[str] = []
    out: list[tuple[int, list[str]]] = []
    i = 0
    n = len(raw_rows)

    while i < n:
        pg, cells = raw_rows[i]

        # ── PATTERN 1: glued serial+name ────────────────────────────────
        if _is_glued(cells):
            fixed = split_glued_serial(cells)
            if fixed:
                out.append((pg, fixed))
                log.append(f"GLUED  p{pg}: serial {fixed[0]} split from name")
                i += 1
                continue

        # ── PATTERN 2: double-serial merge ──────────────────────────────
        if _is_double_serial(cells):
            serials = [l.strip() for l in cells[0].split("\n") if l.strip()]
            lo = int(serials[0])
            hi = int(serials[-1])
            # Rebuild the whole band for these serials from word coordinates.
            band = _rebuild_serial_band(pdf_path, pg, lo, hi)
            for row in band:
                out.append((pg, row))
            log.append(f"MERGE  p{pg}: rebuilt serials {lo}..{hi} "
                       f"({len(band)} projects) from coordinates")
            # Skip the spilled continuation row that follows, if present
            # (blank serial+name, no bare date → belongs to the merge).
            j = i + 1
            if j < n:
                _, nxt = raw_rows[j]
                nc0 = nxt[0].strip() if len(nxt) > 0 else ""
                nc1 = nxt[1].strip() if len(nxt) > 1 else ""
                if nc0 == "" and nc1 == "" and not _is_orphan(nxt):
                    log.append(f"MERGE  p{pg}: consumed spilled row "
                               f"raw[{j}] into rebuild")
                    i = j + 1
                    continue
            i += 1
            continue

        # ── PATTERN 3: orphan data row ──────────────────────────────────
        if _is_orphan(cells):
            # Infer serial from surrounding rows: previous project's serial+1.
            prev_serial = _last_serial(out)
            inferred = str(prev_serial + 1) if prev_serial is not None else ""
            new = list(cells)
            new[0] = inferred          # position-inferred serial
            # name stays empty (genuine source gap — no fabrication)
            out.append((pg, new))
            log.append(f"ORPHAN p{pg}: inferred serial {inferred!r}, "
                       f"name left empty (absent in PDF)")
            i += 1
            continue

        out.append((pg, cells))
        i += 1

    return out, log


def _last_serial(rows: list[tuple[int, list[str]]]) -> int | None:
    """Find the serial of the most recent row that has an integer serial."""
    for _, cells in reversed(rows):
        if cells and cells[0]:
            first = cells[0].split("\n")[0].strip()
            if RE_INT_ONLY.match(first):
                return int(first)
    return None


def _rebuild_serial_band(
    pdf_path: Path, page_1idx: int, lo: int, hi: int,
) -> list[list[str]]:
    """
    Rebuild projects with serials lo..hi on a page directly from word
    coordinates.  Finds the y-band spanning serial `lo` down to just above
    serial `hi+1` (or the next serial), so continuation lines are captured.
    """
    with pdfplumber.open(str(pdf_path)) as pdf:
        page = pdf.pages[page_1idx - 1]
        words = page.extract_words(x_tolerance=2, y_tolerance=2)

    # y-position (top) of each serial number in the left column.
    serial_tops: dict[int, float] = {}
    for w in words:
        if col_of(w["x0"]) == "serial" and RE_INT_ONLY.match(w["text"]):
            serial_tops[int(w["text"])] = w["top"]

    if lo not in serial_tops:
        return []   # safety: can't locate — leave to caller
    top_lo = serial_tops[lo] - 2
    # bottom bound: top of the serial AFTER hi, else a generous margin
    after = min((t for s, t in serial_tops.items() if s > hi), default=None)
    top_hi = (after - 2) if after is not None else (top_lo + 200)

    groups = reconstruct_rows_by_words(pdf_path, page_1idx, top_lo, top_hi)
    return _groups_to_projects(groups)


if __name__ == "__main__":
    # Self-test / demonstration on the 3 known regions.
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    PDF = Path(__file__).resolve().parent.parent / "data" / "raw" / "May_Part-2.pdf"

    print("── PATTERN 1 demo: glued serial (sl_no 1785) ──")
    demo = ["1785 NEW WORK FOR CONSTRUCTION\nOF METRO RAILWAY", "", "4/2010"]
    print("  before:", demo)
    print("  after :", split_glued_serial(demo))

    print("\n── PATTERN 2 demo: 919/920 reconstruction (page 516) ──")
    for grp in reconstruct_rows_by_words(PDF, 516, 585, 658):
        print(f"  top={grp['top']:.1f} serial={grp['serial']!r} "
              f"name={grp['cols'].get('name','')!r} "
              f"appr={grp['cols'].get('approval','')!r}")

    print("\n── PATTERN 3 demo: orphan 175 (page 472) ──")
    for grp in reconstruct_rows_by_words(PDF, 472, 598, 662):
        print(f"  top={grp['top']:.1f} serial={grp['serial']!r} "
              f"name={grp['cols'].get('name','')!r} "
              f"appr={grp['cols'].get('approval','')!r} "
              f"cost={grp['cols'].get('cost','')!r}")
