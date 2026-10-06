from flask import Flask, render_template, request
import pandas as pd
import numpy as np
import pickle
import re
from pathlib import Path

app = Flask(__name__)

# ============================================================
# FILE PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent

APRIL_FILE = BASE_DIR / "data" / "april_projects.csv"
MAY_FILE = BASE_DIR / "data" / "may_projects.csv"
JUNE_FILE = BASE_DIR / "data" / "june_projects.csv"
ML_DATASET_FILE = BASE_DIR / "data" / "uptrack_ml_dataset.csv"

MODEL_FILE = BASE_DIR / "models" / "uptrack_model_balanced.pkl"
SCALER_FILE = BASE_DIR / "models" / "uptrack_scaler.pkl"


# ============================================================
# LOAD DATA
# ============================================================

df = pd.read_csv(APRIL_FILE)
may_df = pd.read_csv(MAY_FILE)
june_df = pd.read_csv(JUNE_FILE)
ml_dataset_df = pd.read_csv(ML_DATASET_FILE)


# ============================================================
# LOAD MODEL
# ============================================================

with open(MODEL_FILE, "rb") as file:
    model = pickle.load(file)

with open(SCALER_FILE, "rb") as file:
    scaler = pickle.load(file)


# ============================================================
# MODEL FEATURES
# ============================================================

FEATURE_COLUMNS = [
    "april_anticipated_month",
    "april_original_commissioning_month",
    "april_revised_commissioning_month",
    "april_original_cost_cr",
    "april_revised_cost_cr",
    "april_anticipated_cost_cr",
    "april_cumulative_expenditure_cr",
    "april_cost_overrun_cr",
    "april_time_overrun_months"
]

REFERENCE = pd.Period("2000-01", freq="M")


# ============================================================
# PROJECT NAME NORMALIZATION
# ============================================================

def normalize_project_name(value):

    if pd.isna(value):
        return ""

    value = str(value).upper().strip()

    value = re.sub(r"[^A-Z0-9]+", " ", value)

    value = re.sub(r"\s+", " ", value)

    return value.strip()


df["_normalized_project_name"] = df["project_name"].apply(
    normalize_project_name
)

may_df["_normalized_project_name"] = may_df["project_name"].apply(
    normalize_project_name
)

june_df["_normalized_project_name"] = june_df["project_name"].apply(
    normalize_project_name
)


# ============================================================
# FIND PROJECT IN MONTHLY DATA
# ============================================================

def find_month_project(normalized_name, monthly_df):

    if not normalized_name:
        return None

    matches = monthly_df[
        monthly_df["_normalized_project_name"] == normalized_name
    ]

    if len(matches) == 1:

        row = matches.iloc[0].copy()

        row = row.astype(object).where(
            pd.notna(row),
            None
        )

        return row

    return None


# ============================================================
# CLEAN VALUE
# ============================================================

def clean_value(value):

    if value is None:
        return None

    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass

    if str(value).strip().lower() in [
        "",
        "nan",
        "none"
    ]:
        return None

    return value


# ============================================================
# MONTH NUMBER
# ============================================================

def month_number(value):

    value = clean_value(value)

    if value is None:
        return None

    try:

        parsed = pd.to_datetime(
            str(value),
            errors="coerce"
        )

        if pd.isna(parsed):
            return None

        period = parsed.to_period("M")

        return (
            (period.year - REFERENCE.year) * 12
            + (period.month - REFERENCE.month)
        )

    except Exception:

        return None


# ============================================================
# NUMERIC VALUE
# ============================================================

def numeric_value(value):

    value = clean_value(value)

    if value is None:
        return None

    try:

        return float(
            str(value).replace(",", "").strip()
        )

    except (ValueError, TypeError):

        return None


# ============================================================
# FEATURE MEDIANS
# ============================================================

feature_medians = {}

for column in FEATURE_COLUMNS:

    if column in ml_dataset_df.columns:

        numeric_column = pd.to_numeric(
            ml_dataset_df[column],
            errors="coerce"
        )

        feature_medians[column] = numeric_column.median()

    else:

        feature_medians[column] = 0


# ============================================================
# CREATE MODEL FEATURES
# ============================================================

def make_features(project):

    features = {}

    features["april_anticipated_month"] = month_number(
        project.get("anticipated_date_of_commissioning")
    )

    features["april_original_commissioning_month"] = month_number(
        project.get("original_date_of_commissioning")
    )

    features["april_revised_commissioning_month"] = month_number(
        project.get("revised_date_of_commissioning")
    )

    features["april_original_cost_cr"] = numeric_value(
        project.get("original_cost_cr")
    )

    features["april_revised_cost_cr"] = numeric_value(
        project.get("revised_cost_cr")
    )

    features["april_anticipated_cost_cr"] = numeric_value(
        project.get("anticipated_cost_cr")
    )

    features["april_cumulative_expenditure_cr"] = numeric_value(
        project.get("cumulative_expenditure_cr")
    )

    features["april_cost_overrun_cr"] = numeric_value(
        project.get("cost_overrun_cr")
    )

    features["april_time_overrun_months"] = numeric_value(
        project.get("time_overrun_months")
    )

    values = []

    for column in FEATURE_COLUMNS:

        value = features.get(column)

        if value is None or pd.isna(value):
            value = feature_medians[column]

        values.append(float(value))

    return np.array(values).reshape(1, -1)


# ============================================================
# PREDICTION
# ============================================================

def predict_delay(project):

    features = make_features(project)

    scaled_features = scaler.transform(features)

    prediction = int(
        model.predict(scaled_features)[0]
    )

    probability = float(
        model.predict_proba(
            scaled_features
        )[0][1]
    )

    return prediction, probability


# ============================================================
# NUMERIC CHANGE COMPARISON
# ============================================================

def compare_numeric(
    april_value,
    may_value,
    june_value,
    label,
    unit=""
):

    values = [
        ("April", clean_value(april_value)),
        ("May", clean_value(may_value)),
        ("June", clean_value(june_value))
    ]

    available = []

    for month, value in values:

        if value is not None:

            try:

                numeric = float(
                    str(value).replace(",", "")
                )

                available.append(
                    (month, numeric)
                )

            except (ValueError, TypeError):
                pass

    if len(available) < 2:
        return None

    first_month, first_value = available[0]
    last_month, last_value = available[-1]

    if first_value == last_value:

        return (
            f"✓ {label} remained unchanged: "
            f"{first_value:g}{unit}"
        )

    if last_value > first_value:

        return (
            f"⚠ {label} increased: "
            f"{first_value:g}{unit} → "
            f"{last_value:g}{unit}"
        )

    return (
        f"✓ {label} decreased: "
        f"{first_value:g}{unit} → "
        f"{last_value:g}{unit}"
    )


# ============================================================
# COMPLETION DATE COMPARISON
# ============================================================

def compare_completion_date(
    april_value,
    may_value,
    june_value
):

    def parse_project_month(value):

        value = clean_value(value)

        if value is None:
            return None

        text = str(value).strip()

        match = re.fullmatch(
            r"(\d{1,2})/(\d{4})",
            text
        )

        if match:

            month = int(match.group(1))
            year = int(match.group(2))

            if 1 <= month <= 12:

                return pd.Period(
                    year=year,
                    month=month,
                    freq="M"
                )

            return None

        match = re.fullmatch(
            r"([A-Za-z]{3})-(\d{2,4})",
            text
        )

        if match:

            month_text = match.group(1).title()
            year_text = match.group(2)

            month_map = {
                "Jan": 1,
                "Feb": 2,
                "Mar": 3,
                "Apr": 4,
                "May": 5,
                "Jun": 6,
                "Jul": 7,
                "Aug": 8,
                "Sep": 9,
                "Oct": 10,
                "Nov": 11,
                "Dec": 12
            }

            month = month_map.get(month_text)

            if month is None:
                return None

            year = int(year_text)

            if len(year_text) == 2:
                year += 2000

            return pd.Period(
                year=year,
                month=month,
                freq="M"
            )

        parsed = pd.to_datetime(
            text,
            errors="coerce"
        )

        if pd.isna(parsed):
            return None

        return pd.Period(
            year=parsed.year,
            month=parsed.month,
            freq="M"
        )

    values = [
        ("April", april_value),
        ("May", may_value),
        ("June", june_value)
    ]

    available = []

    for month_name, value in values:

        parsed = parse_project_month(value)

        if parsed is not None:

            available.append(
                (month_name, parsed)
            )

    if len(available) < 2:
        return None

    first_month, first_date = available[0]
    last_month, last_date = available[-1]

    first_text = first_date.strftime("%b-%y")
    last_text = last_date.strftime("%b-%y")

    if first_date == last_date:

        return (
            f"✓ Completion date remained unchanged: "
            f"{first_text}"
        )

    if last_date > first_date:

        return (
            f"⚠ Completion date moved later: "
            f"{first_text} → {last_text}"
        )

    return (
        f"✓ Completion date moved earlier: "
        f"{first_text} → {last_text}"
    )


# ============================================================
# BUILD WHAT CHANGED
# ============================================================

def build_changes(
    project,
    may_project,
    june_project
):

    changes = []

    if project is None:
        return changes

    april_completion = project.get(
        "anticipated_date_of_commissioning"
    )

    april_revised_cost = project.get(
        "revised_cost_cr"
    )

    april_expenditure = project.get(
        "cumulative_expenditure_cr"
    )

    april_time_overrun = project.get(
        "time_overrun_months"
    )

    may_completion = None
    may_revised_cost = None
    may_expenditure = None
    may_time_overrun = None

    if may_project is not None:

        may_completion = may_project.get(
            "anticipated_date_of_commissioning"
        )

        may_revised_cost = may_project.get(
            "revised_cost_cr"
        )

        may_expenditure = may_project.get(
            "cumulative_expenditure_cr"
        )

        may_time_overrun = may_project.get(
            "time_overrun_months"
        )

    june_completion = None
    june_revised_cost = None
    june_expenditure = None
    june_time_overrun = None

    if june_project is not None:

        june_completion = june_project.get(
            "anticipated_date_of_commissioning"
        )

        june_revised_cost = june_project.get(
            "revised_cost_cr"
        )

        june_expenditure = june_project.get(
            "cumulative_expenditure_cr"
        )

        june_time_overrun = june_project.get(
            "time_overrun_months"
        )

    completion_change = compare_completion_date(
        april_completion,
        may_completion,
        june_completion
    )

    if completion_change:
        changes.append(completion_change)

    revised_cost_change = compare_numeric(
        april_revised_cost,
        may_revised_cost,
        june_revised_cost,
        "Revised cost",
        " Cr"
    )

    if revised_cost_change:
        changes.append(revised_cost_change)

    expenditure_change = compare_numeric(
        april_expenditure,
        may_expenditure,
        june_expenditure,
        "Cumulative expenditure",
        " Cr"
    )

    if expenditure_change:
        changes.append(expenditure_change)

    time_overrun_change = compare_numeric(
        april_time_overrun,
        may_time_overrun,
        june_time_overrun,
        "Time overrun",
        " months"
    )

    if time_overrun_change:
        changes.append(time_overrun_change)

    return changes


# ============================================================
# MAIN PAGE
# ============================================================

@app.route("/", methods=["GET", "POST"])
def index():

    project_names = (
        df["project_name"]
        .dropna()
        .astype(str)
        .tolist()
    )

    total_april_projects = len(df)

    ml_dataset_projects = len(ml_dataset_df)

    delay_projects = int(
        (ml_dataset_df["delay"] == 1).sum()
    )

    no_delay_projects = int(
        (ml_dataset_df["delay"] == 0).sum()
    )

    selected_name = ""

    project = None
    may_project = None
    june_project = None

    prediction = None
    probability = None

    changes = []

    # False unless Predict Delay is clicked
    show_prediction = False

    # ========================================================
    # WHAT-IF VARIABLES
    # ========================================================

    simulation_prediction = None
    simulation_probability = None
    simulation_date = ""

    if request.method == "POST":

        selected_name = request.form.get(
            "project_name",
            ""
        )

        action = request.form.get(
            "action",
            "view"
        )

        if selected_name:

            selected_rows = df[
                df["project_name"].astype(str)
                == selected_name
            ]

            if not selected_rows.empty:

                project = selected_rows.iloc[0]

                normalized_name = normalize_project_name(
                    selected_name
                )

                may_project = find_month_project(
                    normalized_name,
                    may_df
                )

                june_project = find_month_project(
                    normalized_name,
                    june_df
                )

                changes = build_changes(
                    project,
                    may_project,
                    june_project
                )

                # ====================================================
                # SHOW PROJECT
                # ====================================================

                if action == "view":

                    prediction = None
                    probability = None
                    show_prediction = False

                # ====================================================
                # PREDICT DELAY
                # ====================================================

                elif action == "predict":

                    show_prediction = True

                    try:

                        prediction, probability = predict_delay(
                            project
                        )

                    except Exception as error:

                        print(
                            "Prediction error:",
                            error
                        )

                        prediction = None
                        probability = None

                # ====================================================
                # WHAT-IF SIMULATION
                # ====================================================

                elif action == "simulate":

                    simulation_date = request.form.get(
                        "simulation_date",
                        ""
                    )

                    if simulation_date:

                        try:

                            # Make a temporary copy.
                            # Original project data is NOT changed.
                            simulated_project = project.copy()

                            # Change only the expected
                            # completion date.
                            simulated_project[
                                "anticipated_date_of_commissioning"
                            ] = simulation_date

                            (
                                simulation_prediction,
                                simulation_probability
                            ) = predict_delay(
                                simulated_project
                            )

                        except Exception as error:

                            print(
                                "Simulation error:",
                                error
                            )

                            simulation_prediction = None
                            simulation_probability = None

    return render_template(
        "index.html",

        total_april_projects=total_april_projects,

        ml_dataset_projects=ml_dataset_projects,

        delay_projects=delay_projects,

        no_delay_projects=no_delay_projects,

        project_names=project_names,

        selected_name=selected_name,

        project=project,

        may_project=may_project,

        june_project=june_project,

        prediction=prediction,

        probability=probability,

        show_prediction=show_prediction,

        changes=changes,

        # What-If values
        simulation_prediction=simulation_prediction,

        simulation_probability=simulation_probability,

        simulation_date=simulation_date
    )


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    app.run(
        debug=True
    )