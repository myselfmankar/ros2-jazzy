import os
import sqlite3
import sys

def init_db(db_path):
    print(f"Initializing database at: {db_path}")
    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Create tables
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS telemetry_gps (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        latitude REAL NOT NULL,
        longitude REAL NOT NULL,
        altitude REAL NOT NULL,
        status INTEGER NOT NULL,
        timestamp TEXT NOT NULL
    )""")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS telemetry_odom (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        linear_speed REAL NOT NULL,
        angular_speed REAL NOT NULL,
        direction REAL NOT NULL,
        x REAL NOT NULL,
        y REAL NOT NULL,
        z REAL NOT NULL,
        timestamp TEXT NOT NULL
    )""")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS diagnostics_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        level TEXT NOT NULL,
        message TEXT NOT NULL,
        hardware_id TEXT NOT NULL,
        timestamp TEXT NOT NULL
    )""")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS system_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        level TEXT NOT NULL,
        logger_name TEXT NOT NULL,
        message TEXT NOT NULL,
        timestamp TEXT NOT NULL
    )""")

    conn.commit()
    conn.close()
    print("Database initialized successfully.")

if __name__ == "__main__":
    path = "/data/local_robot.db"
    if len(sys.argv) > 1:
        path = sys.argv[1]
    init_db(path)
