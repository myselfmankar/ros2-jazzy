"""Consume ROS 2 bridge MQTT telemetry and persist it to SQLite."""
from __future__ import annotations

import json
import logging
import os
import signal

import paho.mqtt.client as mqtt

from telemetry_backend.database import (
    DEFAULT_DB_PATH,
    init_db,
    insert_diagnostic,
    insert_gps,
    insert_odometry,
    insert_system_log,
)

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
LOGGER = logging.getLogger("telemetry-consumer")
DB_PATH = os.getenv("DB_PATH", DEFAULT_DB_PATH)
MQTT_HOST = os.getenv("MQTT_HOST", "mqtt-broker")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
TOPIC_ROOT = os.getenv("MQTT_TOPIC_ROOT", "omega").strip("/")


def handle_message(topic: str, payload: dict, db_path: str = DB_PATH) -> int:
    """Validate and persist one telemetry message; return its SQLite row id."""
    parts = topic.split("/")
    if len(parts) < 3 or parts[0] != TOPIC_ROOT:
        raise ValueError(f"Unexpected telemetry topic: {topic}")
    device_id = parts[1]
    if not device_id:
        raise ValueError("MQTT telemetry topic is missing a device id")
    if len(parts) == 4 and parts[2] == "telemetry" and parts[3] == "gps":
        return insert_gps(db_path, device_id, payload)
    if len(parts) == 4 and parts[2] == "telemetry" and parts[3] == "odom":
        return insert_odometry(db_path, device_id, payload)
    if len(parts) == 3 and parts[2] == "diagnostics":
        return insert_diagnostic(db_path, device_id, payload)
    if len(parts) == 3 and parts[2] == "logs":
        return insert_system_log(db_path, device_id, payload)
    raise ValueError(f"Unsupported telemetry topic: {topic}")


def on_connect(client: mqtt.Client, userdata, flags, rc) -> None:
    if rc != 0:
        LOGGER.error("MQTT connection rejected with result code %s", rc)
        return
    root = userdata["topic_root"]
    subscriptions = [
        (f"{root}/+/telemetry/gps", 1),
        (f"{root}/+/telemetry/odom", 1),
        (f"{root}/+/diagnostics", 1),
        (f"{root}/+/logs", 1),
    ]
    client.subscribe(subscriptions)
    LOGGER.info("Connected to MQTT at %s; subscribed to %s/# telemetry topics", MQTT_HOST, root)


def on_message(client: mqtt.Client, userdata, msg) -> None:
    try:
        decoded = json.loads(msg.payload.decode("utf-8"))
        if not isinstance(decoded, dict):
            raise ValueError("Telemetry payload must be a JSON object")
        row_id = handle_message(msg.topic, decoded, userdata["db_path"])
        LOGGER.debug("Stored %s as row %s", msg.topic, row_id)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError) as exc:
        LOGGER.warning("Discarding invalid message on %s: %s", msg.topic, exc)
    except Exception:
        LOGGER.exception("Failed to persist MQTT message on %s", msg.topic)


def main() -> None:
    init_db(DB_PATH)
    client = mqtt.Client(client_id=os.getenv("MQTT_CLIENT_ID", "ros2-telemetry-consumer"), userdata={
        "db_path": DB_PATH,
        "topic_root": TOPIC_ROOT,
    })
    client.on_connect = on_connect
    client.on_message = on_message
    client.reconnect_delay_set(min_delay=1, max_delay=30)
    LOGGER.info("Starting telemetry consumer; database=%s", DB_PATH)
    client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
    client.loop_forever()


if __name__ == "__main__":
    main()
