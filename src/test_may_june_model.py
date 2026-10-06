"""
src/test_may_june_model.py

Temporal test:
- Use May 2024 project information as model inputs.
- Use June 2024 anticipated commissioning changes as the actual target.
- Load the EXISTING balanced Logistic Regression model and scaler.
- Do not retrain the model.

Run from the UpTrack project root:
    python src/test_may_june_model.py
"""

import re
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, confusion_matrix

PROJECT_ROOT = Path(__file__).resolve().parent.parent

MAY_FILE = PROJECT_ROOT / "data" / "may_projects.csv"
COMPARISON_FILE = PROJECT_ROOT / "data" / "comparison_may_june.csv"
TRAIN_FILE = PROJECT_ROOT / "data" / "uptrack_ml_dataset.csv"

MODEL_FILE = PROJECT_ROOT / "models" / "uptrack_model_balanced.pkl"
SCALER_FILE = PROJECT_ROOT / "models" / "uptrack_scaler.pkl"

OUT_FILE = PROJECT_ROOT / "data" / "may_june_ml_test.csv"

FEATURES = [
    "april_anticipated_month",
    "april_original_commissioning_month",
    "april_revised_commissioning_month",
    "april_original_cost_cr",
    "april_revised_cost_cr",
    "april_anticipated_cost_cr",
    "april_cumulative_expenditure_cr",
    "april_cost_overrun_cr",
    "april_time_overrun_months",
]

# Same meaning/order as the trained model, but using May data.
MAY_FEATURE_SOURCE = {
    "april_anticipated_month": "anticipated_date_of_commissioning",
    "april_original_commissioning_month": "original_date_of_commissioning",
    "april_revised_commissioning_month": "revised_date_of_commissioning",
    "april_original_cost_cr": "original_cost_cr",
    "april_revised_cost_cr": "revised_cost_cr",
    "april_anticipated_cost_cr": "anticipated_cost_cr",
    "april_cumulative_expenditure_cr": "cumulative_expenditure_cr",
    "april_cost_overrun_cr": "cost_overrun_cr",
    "april_time_overrun_months": "time_overrun_months",
}


def normalize_name(value):
    if pd.isna(value):
        return ""
    text = str(value).upper()
    text = text.replace("–", "-").replace("—", "-")
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def month_number(value):
    """
    Convert a month/year value to months since January 2000.
    Returns NaN when the value cannot be parsed.
    """
    if pd.isna(value):
        return np.nan

    text = str(value).strip()
    if not text or text.upper() in {"N.A.", "NA", "NAN", "-"}:
        return np.nan

    m = re.fullmatch(r"(\d{1,2})/(\d{4})", text)
    if m:
        month = int(m.group(1))
        year = int(m.group(2))
        if 1 <= month <= 12:
            return (year - 2000) * 12 + (month - 1)

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
        month_no = {
            "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4,
            "May": 5, "Jun": 6, "Jul": 7, "Aug": 8,
            "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
        }[month_name]
        return (year - 2000) * 12 + (month_no - 1)

    return np.nan


def numeric_value(value):
    if pd.isna(value):
        return np.nan

    text = str(value).strip()
    if not text or text.upper() in {"N.A.", "NA", "NAN", "-"}:
        return np.nan

    # Remove commas and keep the first signed number.
    text = text.replace(",", "")
    m = re.search(r"-?\d+(?:\.\d+)?", text)
    return float(m.group(0)) if m else np.nan


def main():
    required = [MAY_FILE, COMPARISON_FILE, TRAIN_FILE, MODEL_FILE, SCALER_FILE]
    missing = [str(p) for p in required if not p.exists()]
    if missing:
        print("ERROR: Missing required files:")
        for p in missing:
            print(" -", p)
        sys.exit(1)

    may = pd.read_csv(MAY_FILE)
    comparison = pd.read_csv(COMPARISON_FILE)
    train = pd.read_csv(TRAIN_FILE)

    # The comparison file contains only usable May-June pairs.
    comparison = comparison[
        comparison["delay_may_to_june"].notna()
    ].copy()

    may["match_name"] = may["project_name"].map(normalize_name)
    comparison["match_name"] = comparison["project_name"].map(normalize_name)

    # Avoid ambiguous duplicate names in the May source.
    counts = may["match_name"].value_counts()
    may = may[may["match_name"].map(counts) == 1].copy()

    comparison = comparison[
        comparison["match_name"] != ""
    ].copy()

    may_lookup = may.set_index("match_name")

    rows = []
    for _, target_row in comparison.iterrows():
        key = target_row["match_name"]

        if key not in may_lookup.index:
            continue

        source = may_lookup.loc[key]

        record = {
            "project_name": target_row["project_name"],
            "delay_may_to_june": int(target_row["delay_may_to_june"]),
        }

        for feature, source_col in MAY_FEATURE_SOURCE.items():
            value = source.get(source_col, np.nan)

            if feature.endswith("_month"):
                record[feature] = month_number(value)
            else:
                record[feature] = numeric_value(value)

        rows.append(record)

    test = pd.DataFrame(rows)

    if test.empty:
        print("ERROR: No May feature rows could be aligned with the comparison data.")
        sys.exit(1)

    # Training medians are calculated ONLY from the original ML training dataset.
    # We do not calculate medians from May/June test data.
    for feature in FEATURES:
        train_values = pd.to_numeric(train[feature], errors="coerce")
        median = train_values.median()
        test[feature] = pd.to_numeric(test[feature], errors="coerce").fillna(median)

    # Keep exact trained feature order.
    X_test = test[FEATURES].astype(float)
    y_test = test["delay_may_to_june"].astype(int)

    model = joblib.load(MODEL_FILE)
    scaler = joblib.load(SCALER_FILE)

    X_scaled = scaler.transform(X_test)
    predictions = model.predict(X_scaled)
    probabilities = model.predict_proba(X_scaled)[:, 1]

    test["predicted_delay"] = predictions.astype(int)
    test["predicted_delay_probability"] = probabilities

    accuracy = accuracy_score(y_test, predictions)
    precision = precision_score(y_test, predictions, zero_division=0)
    recall = recall_score(y_test, predictions, zero_division=0)
    f1 = f1_score(y_test, predictions, zero_division=0)
    cm = confusion_matrix(y_test, predictions, labels=[0, 1])

    test.to_csv(OUT_FILE, index=False)

    print(f"May-June test rows: {len(test)}")
    print(f"Actual delay = 0: {int((y_test == 0).sum())}")
    print(f"Actual delay = 1: {int((y_test == 1).sum())}")
    print()
    print("TEMPORAL TEST RESULTS")
    print(f"Accuracy : {accuracy * 100:.2f}%")
    print(f"Precision: {precision * 100:.2f}%")
    print(f"Recall   : {recall * 100:.2f}%")
    print(f"F1-score : {f1 * 100:.2f}%")
    print()
    print("Confusion Matrix:")
    print(cm)
    print()
    print(f"Saved: {OUT_FILE}")


if __name__ == "__main__":
    main()
