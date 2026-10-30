# Inspecting the telemetry database

The MQTT telemetry consumer creates the SQLite schema and stores incoming messages in a shared Docker volume. Start the stack first:

    docker compose up --build -d

Open a SQLite shell in the telemetry API container using Python's SQLite driver:

    docker compose exec telemetry-api python - <<'PY'
    import os, sqlite3
    conn = sqlite3.connect(os.getenv("DB_PATH", "/data/local_robot.db"))
    for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
        print(row[0])
    conn.close()
    PY

Examples for recent records:

    docker compose exec telemetry-api python - <<'PY'
    import os, sqlite3
    conn = sqlite3.connect(os.getenv("DB_PATH", "/data/local_robot.db"))
    conn.row_factory = sqlite3.Row
    for table in ("telemetry_gps", "telemetry_odom", "diagnostics_log", "system_logs"):
        print("\n" + table)
        for row in conn.execute(f"SELECT * FROM {table} ORDER BY id DESC LIMIT 5"):
            print(dict(row))
    conn.close()
    PY

Read-only HTTP endpoints are also available at http://localhost:8000/docs:

- GET /health
- GET /telemetry/gps?device_id=device-test&limit=20
- GET /telemetry/odometry?device_id=device-test&limit=20
- GET /diagnostics?device_id=device-test&limit=20
- GET /logs?device_id=device-test&limit=20

The database uses a named Docker volume (telemetry-data) and persists across container restarts. To remove the stored data intentionally, use docker compose down -v.
