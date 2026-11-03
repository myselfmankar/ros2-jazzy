"""Small SQLite storage layer shared by the MQTT consumer and FastAPI."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

DEFAULT_DB_PATH = "/data/local_robot.db"
TABLES = {"telemetry_gps", "telemetry_odom", "diagnostics_log", "system_logs"}

SCHEMA = {
    "telemetry_gps": """CREATE TABLE IF NOT EXISTS telemetry_gps (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        device_id TEXT NOT NULL DEFAULT 'unknown',
        inspection_id TEXT,
        operator_id TEXT,
        latitude REAL NOT NULL,
        longitude REAL NOT NULL,
        altitude REAL NOT NULL,
        status INTEGER NOT NULL,
        timestamp TEXT NOT NULL
    )""",
    "telemetry_odom": """CREATE TABLE IF NOT EXISTS telemetry_odom (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        device_id TEXT NOT NULL DEFAULT 'unknown',
        inspection_id TEXT,
        operator_id TEXT,
        linear_speed REAL NOT NULL,
        angular_speed REAL NOT NULL,
        direction REAL NOT NULL,
        x REAL NOT NULL,
        y REAL NOT NULL,
        z REAL NOT NULL,
        timestamp TEXT NOT NULL
    )""",
    "diagnostics_log": """CREATE TABLE IF NOT EXISTS diagnostics_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        device_id TEXT NOT NULL DEFAULT 'unknown',
        inspection_id TEXT,
        operator_id TEXT,
        level TEXT NOT NULL,
        message TEXT NOT NULL,
        hardware_id TEXT NOT NULL,
        timestamp TEXT NOT NULL
    )""",
    "system_logs": """CREATE TABLE IF NOT EXISTS system_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        device_id TEXT NOT NULL DEFAULT 'unknown',
        inspection_id TEXT,
        operator_id TEXT,
        level TEXT NOT NULL,
        logger_name TEXT NOT NULL,
        message TEXT NOT NULL,
        timestamp TEXT NOT NULL
    )""",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


@contextmanager
def connect(db_path: str = DEFAULT_DB_PATH) -> Iterator[sqlite3.Connection]:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 10000")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path: str = DEFAULT_DB_PATH) -> None:
    with connect(db_path) as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        for statement in SCHEMA.values():
            conn.execute(statement)
        # Migrate databases created by the earlier db_init.py schema.
        for table in TABLES:
            columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
            if "device_id" not in columns:
                conn.execute(
                    f"ALTER TABLE {table} ADD COLUMN device_id TEXT NOT NULL DEFAULT 'unknown'"
                )
            conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_timestamp ON {table}(timestamp)")
            conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_device ON {table}(device_id)")


def _number(payload: dict[str, Any], key: str) -> float:
    try:
        value = float(payload[key])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Missing or invalid numeric field: {key}") from exc
    if value != value or value in (float("inf"), float("-inf")):
        raise ValueError(f"Field {key} must be finite")
    return value


def _timestamp(payload: dict[str, Any]) -> str:
    value = payload.get("timestamp")
    return str(value) if value else utc_now()


def _insert(db_path: str, table: str, values: dict[str, Any]) -> int:
    if table not in TABLES:
        raise ValueError(f"Unsupported table: {table}")
    columns = list(values)
    placeholders = ", ".join("?" for _ in columns)
    column_sql = ", ".join(columns)
    with connect(db_path) as conn:
        cursor = conn.execute(
            f"INSERT INTO {table} ({column_sql}) VALUES ({placeholders})",
            [values[column] for column in columns],
        )
        return int(cursor.lastrowid)


def insert_gps(db_path: str, device_id: str, payload: dict[str, Any]) -> int:
    return _insert(db_path, "telemetry_gps", {
        "device_id": device_id,
        "latitude": _number(payload, "latitude"),
        "longitude": _number(payload, "longitude"),
        "altitude": _number(payload, "altitude"),
        "status": int(_number(payload, "status")),
        "timestamp": _timestamp(payload),
    })


def insert_odometry(db_path: str, device_id: str, payload: dict[str, Any]) -> int:
    fields = ("linear_speed", "angular_speed", "direction", "x", "y", "z")
    values: dict[str, Any] = {"device_id": device_id}
    values.update({field: _number(payload, field) for field in fields})
    values["timestamp"] = _timestamp(payload)
    return _insert(db_path, "telemetry_odom", values)


def insert_diagnostic(db_path: str, device_id: str, payload: dict[str, Any]) -> int:
    return _insert(db_path, "diagnostics_log", {
        "device_id": device_id,
        "level": str(payload.get("level", "UNKNOWN")),
        "message": str(payload.get("message", "")),
        "hardware_id": str(payload.get("hardware_id", "unknown")),
        "timestamp": _timestamp(payload),
    })


def insert_system_log(db_path: str, device_id: str, payload: dict[str, Any]) -> int:
    return _insert(db_path, "system_logs", {
        "device_id": device_id,
        "level": str(payload.get("level", "UNKNOWN")),
        "logger_name": str(payload.get("logger_name", "unknown")),
        "message": str(payload.get("message", "")),
        "timestamp": _timestamp(payload),
    })


def get_records(
    table: str, db_path: str = DEFAULT_DB_PATH, device_id: str | None = None, limit: int = 50
) -> list[dict[str, Any]]:
    if table not in TABLES:
        raise ValueError(f"Unsupported table: {table}")
    limit = max(1, min(int(limit), 500))
    query = f"SELECT * FROM {table}"
    params: list[Any] = []
    if device_id:
        query += " WHERE device_id = ?"
        params.append(device_id)
    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    with connect(db_path) as conn:
        return [dict(row) for row in conn.execute(query, params).fetchall()]


def database_health(db_path: str = DEFAULT_DB_PATH) -> bool:
    try:
        with connect(db_path) as conn:
            conn.execute("SELECT 1").fetchone()
        return True
    except sqlite3.Error:
        return False
