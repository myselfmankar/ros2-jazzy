import sqlite3
import tempfile
import unittest
from pathlib import Path

from telemetry_backend.database import (
    get_records,
    init_db,
    insert_diagnostic,
    insert_gps,
    insert_odometry,
    insert_system_log,
)
from telemetry_backend.mqtt_consumer import handle_message


class TelemetryDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tmp.name) / "data" / "robot.db")
        init_db(self.db_path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_all_telemetry_types_are_persisted(self):
        insert_gps(self.db_path, "robot-a", {
            "latitude": 18.5, "longitude": 73.8, "altitude": 215,
            "status": 0, "timestamp": "2026-01-01T00:00:00Z",
        })
        insert_odometry(self.db_path, "robot-a", {
            "linear_speed": 0.4, "angular_speed": 0.1, "direction": 90,
            "x": 1, "y": 2, "z": 0, "timestamp": "2026-01-01T00:00:01Z",
        })
        insert_diagnostic(self.db_path, "robot-a", {
            "level": "WARN", "message": "Battery low", "hardware_id": "battery",
        })
        insert_system_log(self.db_path, "robot-a", {
            "level": "INFO", "logger_name": "simulator", "message": "Started",
        })
        self.assertEqual(len(get_records("telemetry_gps", self.db_path)), 1)
        self.assertEqual(get_records("telemetry_odom", self.db_path)[0]["linear_speed"], 0.4)
        self.assertEqual(get_records("diagnostics_log", self.db_path)[0]["level"], "WARN")
        self.assertEqual(get_records("system_logs", self.db_path)[0]["device_id"], "robot-a")

    def test_mqtt_topic_routes_payload_to_correct_table(self):
        row_id = handle_message("omega/robot-b/telemetry/gps", {
            "latitude": 18.5, "longitude": 73.8, "altitude": 215, "status": 0,
        }, self.db_path)
        self.assertGreater(row_id, 0)
        self.assertEqual(get_records("telemetry_gps", self.db_path)[0]["device_id"], "robot-b")

    def test_invalid_numeric_payload_is_rejected(self):
        with self.assertRaises(ValueError):
            insert_gps(self.db_path, "robot-a", {
                "latitude": "north", "longitude": 73.8, "altitude": 215, "status": 0,
            })

    def test_unsupported_topic_is_rejected(self):
        with self.assertRaises(ValueError):
            handle_message("omega/robot-a/commands", {"action": "STOP"}, self.db_path)

    def test_legacy_schema_is_migrated_without_losing_rows(self):
        legacy_path = str(Path(self.tmp.name) / "legacy.db")
        with sqlite3.connect(legacy_path) as conn:
            conn.execute("""
                CREATE TABLE telemetry_gps (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    inspection_id TEXT,
                    operator_id TEXT,
                    latitude REAL NOT NULL,
                    longitude REAL NOT NULL,
                    altitude REAL NOT NULL,
                    status INTEGER NOT NULL,
                    timestamp TEXT NOT NULL
                )
            """)
            conn.execute(
                "INSERT INTO telemetry_gps "
                "(latitude, longitude, altitude, status, timestamp) "
                "VALUES (18.5, 73.8, 215, 0, '2026-01-01T00:00:00Z')"
            )

        init_db(legacy_path)
        rows = get_records("telemetry_gps", legacy_path)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["device_id"], "unknown")
        self.assertEqual(rows[0]["latitude"], 18.5)


if __name__ == "__main__":
    unittest.main()
