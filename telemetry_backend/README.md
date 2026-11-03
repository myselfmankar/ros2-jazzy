# Telemetry backend

The package consumes MQTT telemetry topics and persists them in SQLite. It also exposes a read-only FastAPI application. See the repository README for complete setup, API and command examples.

Environment variables:

- MQTT_HOST / MQTT_PORT: broker connection (defaults: mqtt-broker:1883).
- MQTT_TOPIC_ROOT: root topic name (default: omega).
- DB_PATH: SQLite file path (default: /data/local_robot.db).
- LOG_LEVEL: Python logging level (default: INFO).
