"""Read-only HTTP API for the telemetry SQLite database."""
from __future__ import annotations

import os
from fastapi import FastAPI, HTTPException, Query

from telemetry_backend.database import DEFAULT_DB_PATH, database_health, get_records, init_db

DB_PATH = os.getenv("DB_PATH", DEFAULT_DB_PATH)
app = FastAPI(
    title="ROS 2 Telemetry API",
    description="Read recent GPS, odometry, diagnostics, and log records stored by the MQTT consumer.",
    version="1.0.0",
)


@app.on_event("startup")
def startup() -> None:
    init_db(DB_PATH)


@app.get("/health")
def health() -> dict[str, str]:
    if not database_health(DB_PATH):
        raise HTTPException(status_code=503, detail="SQLite database is unavailable")
    return {"status": "ok", "database": "available"}


def _records(table: str, device_id: str | None, limit: int) -> list[dict]:
    try:
        return get_records(table, DB_PATH, device_id, limit)
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Failed to read telemetry database") from exc


@app.get("/telemetry/gps")
def gps(
    device_id: str | None = None,
    limit: int = Query(default=50, ge=1, le=500),
) -> list[dict]:
    return _records("telemetry_gps", device_id, limit)


@app.get("/telemetry/odometry")
def odometry(
    device_id: str | None = None,
    limit: int = Query(default=50, ge=1, le=500),
) -> list[dict]:
    return _records("telemetry_odom", device_id, limit)


@app.get("/diagnostics")
def diagnostics(
    device_id: str | None = None,
    limit: int = Query(default=50, ge=1, le=500),
) -> list[dict]:
    return _records("diagnostics_log", device_id, limit)


@app.get("/logs")
def logs(
    device_id: str | None = None,
    limit: int = Query(default=50, ge=1, le=500),
) -> list[dict]:
    return _records("system_logs", device_id, limit)
