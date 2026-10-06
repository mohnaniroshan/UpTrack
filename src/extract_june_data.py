"""
src/extract_june_data.py

Extract Table 7: Project List: Ongoing Projects as of 30th June 2024
from the MoSPI June 2024 report.

This extractor uses the PDF's stable x-coordinate layout rather than
assuming the table has the same column structure as April/May.

Run from the UpTrack project root:
    python src/extract_june_data.py
"""

import re
import sys
from pathlib import Path

import pandas as pd
import pdfplumber

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PDF_PATH = PROJECT_ROOT / "data" / "raw" / "June.pdf"
OUT_PATH = PROJECT_ROOT / "data" / "june_projects.csv"

# Table 7 starts on report page 33 and ends on report page 302.
# pdfplumber uses 0-based page indexes.
START_PAGE = 34
END_PAGE = 301

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
    "physical_progress_pct",
    "project_code",
]

DATE_RE = re.compile(
    r"(?<!\d)(?:\d{1,2}/\d{4}|"
    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
    r"[a-z]*[- ]\d{2,4})",
    re.IGNORECASE,
)

NUM_RE = re.compile(r"-?[\d,]+(?:\.\d+)?")

SERIAL_RE = re.compile(r"^\d{1,4}$")
CODE_RE = re.compile(r"\((?:N)?\d{8,9}\)")

# Approximate x-coordinate ranges from the June Table 7 layout.
# These remain stable across the report pages.
X_RANGES = {
    "serial": (140, 175),
    "name": (170, 275),
    "approval": (270, 335),
    "commissioning": (335, 410),
    "cost": (410, 485),
    "cumulative": (485, 535),
    "physical": (535, 590),
}


def words_in_column(words, x0, x1, start_y, end_y):
    selected = [
        w for w in words
        if x0 <= w["x0"] < x1
        and start_y - 1 <= w["top"] < end_y - 1
    ]
    selected.sort(key=lambda w: (w["top"], w["x0"]))

    lines = []
    for w in selected:
        if not lines or abs(lines[-1][0] - w["top"]) > 2:
            lines.append([w["top"], w["text"]])
        else:
            lines[-1][1] += " " + w["text"]

    return "\n".join(line[1] for line in lines).strip()


def clean_project_name(raw):
    if not raw:
        return ""

    # Remove the trailing agency and project-code lines.
    lines = [x.strip() for x in raw.splitlines() if x.strip()]

    while lines and CODE_RE.fullmatch(lines[-1]):
        lines.pop()

    if lines and re.fullmatch(r"\([^()\n]{1,100}\)", lines[-1]):
        lines.pop()

    # The PDF sometimes clips a word at the right edge. Keep the
    # extracted text as-is rather than inventing missing text.
    return " ".join(lines).strip()


def first_date(value):
    if not value:
        return None
    m = DATE_RE.search(value)
    return m.group(0) if m else None


def bracket_value(value, bracket):
    if not value:
        return None

    if bracket == "round":
        m = re.search(r"\(([^)]*)\)", value)
    else:
        m = re.search(r"\{([^}]*)\}", value)

    if not m:
        return None

    inner = m.group(1).strip()

    # N.A. means missing.
    if inner.upper() in {"N.A.", "N/A", "-"}:
        return None

    if bracket == "round":
        d = DATE_RE.search(inner)
        if d:
            return d.group(0)
    else:
        d = DATE_RE.search(inner)
        if d:
            return d.group(0)

    n = NUM_RE.search(inner)
    return n.group(0) if n else None


def plain_numeric(value):
    if not value:
        return None

    # Ignore page-footer text accidentally captured in the last row.
    first = value.splitlines()[0].strip()
    m = NUM_RE.search(first)
    return m.group(0) if m else None


def parse_page(page):
    words = page.extract_words(x_tolerance=2, y_tolerance=3)

    serial_words = []
    for w in words:
        x0 = w["x0"]
        if (
            X_RANGES["serial"][0] <= x0 <= X_RANGES["serial"][1]
            and w["top"] > 80
            and SERIAL_RE.fullmatch(w["text"])
        ):
            serial_words.append(w)

    serial_words.sort(key=lambda w: w["top"])

    page_records = []

    for i, serial_word in enumerate(serial_words):
        start_y = serial_word["top"]
        end_y = (
            serial_words[i + 1]["top"]
            if i + 1 < len(serial_words)
            else page.height
        )

        raw_name = words_in_column(
            words, *X_RANGES["name"], start_y, end_y
        )
        approval = words_in_column(
            words, *X_RANGES["approval"], start_y, end_y
        )
        commissioning = words_in_column(
            words, *X_RANGES["commissioning"], start_y, end_y
        )
        cost = words_in_column(
            words, *X_RANGES["cost"], start_y, end_y
        )
        cumulative = words_in_column(
            words, *X_RANGES["cumulative"], start_y, end_y
        )
        physical = words_in_column(
            words, *X_RANGES["physical"], start_y, end_y
        )

        name = clean_project_name(raw_name)

        # Extract the project code from the name column.
        code_match = CODE_RE.search(raw_name or "")
        project_code = (
            code_match.group(0).strip("()")
            if code_match
            else None
        )

        # Commissioning:
        # original = first date
        # revised = date inside (...)
        # anticipated = date inside {...}
        original_commissioning = first_date(commissioning)
        revised_commissioning = bracket_value(commissioning, "round")
        anticipated_commissioning = bracket_value(commissioning, "square")

        # Cost:
        # original = first numeric value
        # revised = numeric value inside (...)
        # anticipated = numeric value inside {...}
        original_cost = plain_numeric(cost)
        revised_cost = bracket_value(cost, "round")
        anticipated_cost = bracket_value(cost, "square")

        page_records.append({
            "sl_no": int(serial_word["text"]),
            "project_name": name,
            "date_of_approval": first_date(approval),
            "original_date_of_commissioning": original_commissioning,
            "revised_date_of_commissioning": revised_commissioning,
            "anticipated_date_of_commissioning": anticipated_commissioning,
            "original_cost_cr": original_cost,
            "revised_cost_cr": revised_cost,
            "anticipated_cost_cr": anticipated_cost,
            "cumulative_expenditure_cr": plain_numeric(cumulative),
            "cost_overrun_cr": None,
            "time_overrun_months": None,
            "physical_progress_pct": plain_numeric(physical),
            "project_code": project_code,
        })

    return page_records


def main():
    if not PDF_PATH.exists():
        print(f"ERROR: PDF not found: {PDF_PATH}", file=sys.stderr)
        sys.exit(1)

    records = []

    with pdfplumber.open(str(PDF_PATH)) as pdf:
        print(f"PDF: {PDF_PATH}")
        print(f"Total pages: {len(pdf.pages)}")

        for page_index in range(START_PAGE, END_PAGE + 1):
            page_records = parse_page(pdf.pages[page_index])
            records.extend(page_records)

    df = pd.DataFrame(records)

    if df.empty:
        print("ERROR: No Table 7 project rows were extracted.", file=sys.stderr)
        sys.exit(1)

    # The report serial numbers should be 1..1802.
    df = df.drop_duplicates(subset=["sl_no"], keep="first")
    df = df.sort_values("sl_no").reset_index(drop=True)

    df["project_row_id"] = [
        f"JUN-2024-{n:04d}" for n in df["sl_no"]
    ]

    df = df[COLUMNS]

    # Validation
    expected = set(range(1, 1803))
    actual = set(df["sl_no"].astype(int))

    missing = sorted(expected - actual)
    duplicates = int(df["sl_no"].duplicated().sum())

    print(f"Extracted rows: {len(df)}")
    print(f"Serial range: {df['sl_no'].min()}..{df['sl_no'].max()}")
    print(f"Duplicate serials after cleanup: {duplicates}")
    print(f"Missing serials: {len(missing)}")

    if missing:
        print(f"Missing serial sample: {missing[:20]}")

    if len(df) < 1750:
        print(
            "ERROR: Extraction produced fewer than 1750 rows. "
            "Do not use this CSV for matching yet.",
            file=sys.stderr,
        )
        sys.exit(1)

    df.to_csv(OUT_PATH, index=False)
    print(f"Saved: {OUT_PATH}")


if __name__ == "__main__":
    main()
