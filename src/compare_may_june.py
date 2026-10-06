"""
src/compare_may_june.py

Match May 2024 and June 2024 project records using normalized project names.

We deliberately do NOT use serial numbers as project identity.

Run from the UpTrack project root:
    python src/compare_may_june.py
"""

import re
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MAY_FILE = PROJECT_ROOT / "data" / "may_projects.csv"
JUNE_FILE = PROJECT_ROOT / "data" / "june_projects.csv"
OUT_FILE = PROJECT_ROOT / "data" / "comparison_may_june.csv"


def normalize_name(value):
    """Normalize a project name for exact cross-month matching."""
    if pd.isna(value):
        return ""

    text = str(value).upper()

    # Remove common PDF punctuation/noise.
    text = text.replace("–", "-").replace("—", "-")
    text = re.sub(r"[^A-Z0-9]+", " ", text)

    # Collapse whitespace.
    text = re.sub(r"\s+", " ", text).strip()

    return text


def parse_month(value):
    """
    Convert common MM/YYYY or Mon-YY values to YYYY-MM.
    Returns None for missing/unreadable values.
    """
    if pd.isna(value):
        return None

    text = str(value).strip()
    if not text or text.upper() in {"N.A.", "NA", "NAN", "-"}:
        return None

    # MM/YYYY
    m = re.fullmatch(r"(\d{1,2})/(\d{4})", text)
    if m:
        month = int(m.group(1))
        year = int(m.group(2))
        if 1 <= month <= 12:
            return f"{year:04d}-{month:02d}"

    # Mon-YY / Mon-YYYY
    m = re.fullmatch(
        r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[- ](\d{2,4})",
        text,
        flags=re.IGNORECASE,
    )
    if m:
        month_name = m.group(1).title()[:3]
        year = int(m.group(2))
        if year < 100:
            year += 2000
        month_number = {
            "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4,
            "May": 5, "Jun": 6, "Jul": 7, "Aug": 8,
            "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
        }[month_name]
        return f"{year:04d}-{month_number:02d}"

    return None


def main():
    if not MAY_FILE.exists():
        print(f"ERROR: Missing {MAY_FILE}", file=sys.stderr)
        sys.exit(1)

    if not JUNE_FILE.exists():
        print(f"ERROR: Missing {JUNE_FILE}", file=sys.stderr)
        sys.exit(1)

    may = pd.read_csv(MAY_FILE)
    june = pd.read_csv(JUNE_FILE)

    required_may = {"project_name", "anticipated_date_of_commissioning"}
    required_june = {"project_name", "anticipated_date_of_commissioning"}

    if not required_may.issubset(may.columns):
        print("ERROR: May CSV is missing required columns.", file=sys.stderr)
        sys.exit(1)

    if not required_june.issubset(june.columns):
        print("ERROR: June CSV is missing required columns.", file=sys.stderr)
        sys.exit(1)

    may = may.copy()
    june = june.copy()

    may["match_name"] = may["project_name"].map(normalize_name)
    june["match_name"] = june["project_name"].map(normalize_name)

    # Empty names cannot be matched.
    may = may[may["match_name"] != ""].copy()
    june = june[june["match_name"] != ""].copy()

    # Only use exact normalized names for this first pass.
    # Ambiguous duplicate normalized names are not forced.
    may_counts = may["match_name"].value_counts()
    june_counts = june["match_name"].value_counts()

    may_unique = may[may["match_name"].map(may_counts) == 1].copy()
    june_unique = june[june["match_name"].map(june_counts) == 1].copy()

    june_lookup = june_unique.set_index("match_name")

    rows = []

    for _, m in may_unique.iterrows():
        key = m["match_name"]

        if key not in june_lookup.index:
            continue

        j = june_lookup.loc[key]

        may_date = parse_month(m["anticipated_date_of_commissioning"])
        june_date = parse_month(j["anticipated_date_of_commissioning"])

        if may_date is None or june_date is None:
            delay = None
        else:
            delay = int(june_date > may_date)

        rows.append({
            "project_name": m["project_name"],
            "may_anticipated_date": m["anticipated_date_of_commissioning"],
            "june_anticipated_date": j["anticipated_date_of_commissioning"],
            "delay_may_to_june": delay,
        })

    result = pd.DataFrame(rows)

    if result.empty:
        print("ERROR: No exact normalized-name matches found.", file=sys.stderr)
        sys.exit(1)

    result.to_csv(OUT_FILE, index=False)

    matched = len(result)
    usable = int(result["delay_may_to_june"].notna().sum())
    missing_dates = matched - usable

    print(f"May projects: {len(pd.read_csv(MAY_FILE))}")
    print(f"June projects: {len(pd.read_csv(JUNE_FILE))}")
    print(f"Exact normalized-name matches: {matched}")
    print(f"Usable May-June date pairs: {usable}")
    print(f"Missing/invalid date pairs: {missing_dates}")

    if usable:
        counts = result.loc[
            result["delay_may_to_june"].notna(),
            "delay_may_to_june"
        ].value_counts().sort_index()

        print(f"Delay = 0: {int(counts.get(0, 0))}")
        print(f"Delay = 1: {int(counts.get(1, 0))}")

    print(f"Saved: {OUT_FILE}")


if __name__ == "__main__":
    main()
