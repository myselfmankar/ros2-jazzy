"""Command-line wrapper to initialize the telemetry SQLite schema."""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "telemetry_backend"))
from telemetry_backend.database import DEFAULT_DB_PATH, init_db  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize the ROS 2 telemetry SQLite database")
    parser.add_argument("db_path", nargs="?", default=DEFAULT_DB_PATH)
    args = parser.parse_args()
    init_db(args.db_path)
    print(f"Initialized telemetry database: {args.db_path}")


if __name__ == "__main__":
    main()
