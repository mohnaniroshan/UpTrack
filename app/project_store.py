"""Small SQLite persistence layer for user-managed UpTrack projects."""

import json
import sqlite3
from pathlib import Path

from flask import current_app


def connect():
    connection = sqlite3.connect(current_app.config["DATABASE"])
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db(database):
    Path(database).parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL COLLATE NOCASE UNIQUE,
                name TEXT NOT NULL,
                project_type TEXT NOT NULL DEFAULT '',
                location TEXT NOT NULL DEFAULT '',
                start_date TEXT,
                original_completion_date TEXT,
                expected_completion_date TEXT,
                budget REAL,
                expenditure REAL,
                progress REAL NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'Planned',
                milestones TEXT NOT NULL DEFAULT '[]',
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS import_batches (
                token TEXT PRIMARY KEY,
                rows_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.commit()


def _project_dict(row):
    if row is None:
        return None
    project = dict(row)
    try:
        project["milestones"] = json.loads(project.get("milestones") or "[]")
    except (TypeError, ValueError):
        project["milestones"] = []
    return project


def get_projects():
    with connect() as connection:
        rows = connection.execute(
            "SELECT * FROM projects ORDER BY updated_at DESC, name COLLATE NOCASE"
        ).fetchall()
    return [_project_dict(row) for row in rows]


def get_project(project_id):
    with connect() as connection:
        row = connection.execute(
            "SELECT * FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
    return _project_dict(row)


def save_project(project, record_id=None):
    fields = (
        "project_id", "name", "project_type", "location", "start_date",
        "original_completion_date", "expected_completion_date", "budget",
        "expenditure", "progress", "status", "milestones", "notes",
    )
    values = [project[key] for key in fields]
    values[11] = json.dumps(values[11], ensure_ascii=False)
    with connect() as connection:
        if record_id is None:
            placeholders = ", ".join("?" for _ in fields)
            connection.execute(
                f"INSERT INTO projects ({', '.join(fields)}) VALUES ({placeholders})",
                values,
            )
        else:
            assignments = ", ".join(f"{field} = ?" for field in fields)
            connection.execute(
                f"UPDATE projects SET {assignments}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                values + [record_id],
            )
        connection.commit()


def delete_project(record_id):
    with connect() as connection:
        connection.execute("DELETE FROM projects WHERE id = ?", (record_id,))
        connection.commit()
