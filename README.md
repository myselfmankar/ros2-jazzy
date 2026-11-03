# ROS 2 Jazzy Robot Telemetry Pipeline

A reproducible ROS 2 demo that simulates a mobile robot, publishes GPS/odometry/diagnostic telemetry through MQTT, stores the messages in SQLite, and exposes recent records through a small FastAPI service. An optional companion package replays camera recordings and publishes one selected camera feed to LiveKit over WebRTC.

> **Scope:** the default demo uses synthetic robot telemetry. The video workflow uses recorded ROS 2 image topics. Neither is a live hardware deployment. The MQTT broker configuration is for local development only and must not be exposed to an untrusted network or connected to a physical robot without authentication and independent safety controls.

## Architecture

~~~text
Mock Robot Simulator (ROS 2 Jazzy)
  ├── /gps/fix
  ├── /odom
  └── /diagnostics
          |
          v
ROS 2 <-> MQTT Bridge ---- MQTT commands back to /cmd_vel and /session/active
          |
          v
       Mosquitto
          | telemetry topics
          v
   MQTT Consumer --------> SQLite (persistent Docker volume)
                                  |
                                  v
                            FastAPI (read-only)

Optional video workflow:
MCAP camera recordings -> ROS 2 image topics -> OpenCV/cv_bridge -> LiveKit WebRTC
~~~

## Components

- ros2_mqtt_bridge: a simulator that publishes synthetic GPS, odometry and diagnostic messages, plus a bidirectional MQTT bridge.
- telemetry_backend: an MQTT consumer that validates and persists telemetry, a shared SQLite access layer, and read-only FastAPI endpoints.
- ros2_video_streamer: an optional ROS 2 camera node that converts selected image topics to LiveKit video tracks.
- Docker Compose: starts Mosquitto, the simulator, MQTT bridge, SQLite consumer, and HTTP API.

## Requirements

- Docker Engine and Docker Compose v2.
- Docker Desktop users: Docker Desktop 4.34+ with host networking enabled under Settings -> Resources -> Network.
- For running ROS 2 nodes outside Docker: ROS 2 Jazzy, Python 3.12, and colcon.
- For the optional video workflow: three compatible ROS 2 bag/MCAP camera recordings and a LiveKit URL/token or a token gateway.

## Start the core telemetry demo

The core services use host networking because ROS 2 DDS discovery relies on multicast and can be unreliable across Docker bridge networks. Host networking is supported directly by Docker Engine on Linux and by Docker Desktop 4.34+ after enabling it in Settings -> Resources -> Network.

~~~bash
docker compose up --build -d
~~~

Check the services:

~~~bash
docker compose ps
docker compose logs -f ros2-bridge telemetry-consumer telemetry-api
~~~

The simulator starts with its session inactive. Activate it by publishing a command to the bridge's MQTT session topic:

~~~bash
docker compose exec mqtt-broker mosquitto_pub \
  -h 127.0.0.1 -t omega/device-test/session/active -m '{"active":true}'
~~~

Use the configured device ID if you set ROBOT_DEVICE_ID in your environment or .env file. The simulator then publishes GPS, odometry and diagnostic messages once per second. The bridge converts them to JSON and publishes them to:

| ROS 2 source | MQTT topic |
| --- | --- |
| /gps/fix | omega/DEVICE_ID/telemetry/gps |
| /odom | omega/DEVICE_ID/telemetry/odom |
| /diagnostics | omega/DEVICE_ID/diagnostics |
| /rosout | omega/DEVICE_ID/logs |

The MQTT consumer stores messages in SQLite. Records include a device_id field so multiple device IDs can share the demo database.

## HTTP API

Open the interactive API documentation at http://localhost:8000/docs. The API binds to loopback only.

| Method and path | Purpose |
| --- | --- |
| GET /health | API and database health |
| GET /telemetry/gps | Recent GPS readings |
| GET /telemetry/odometry | Recent speed, heading and position |
| GET /diagnostics | Recent diagnostic events |
| GET /logs | Recent ROS log messages |

All list endpoints accept optional device_id and limit query parameters. The limit is capped at 500.

Examples:

~~~bash
curl "http://localhost:8000/health"
curl "http://localhost:8000/telemetry/gps?device_id=device-test&limit=10"
curl "http://localhost:8000/telemetry/odometry?limit=10"
curl "http://localhost:8000/diagnostics?limit=10"
~~~

The database lives in the named Docker volume telemetry-data, so it survives container recreation. To inspect it, see read-db.md. To deliberately remove the database and all broker volumes, run docker compose down -v.

## Send simulated robot commands

The bridge subscribes to omega/DEVICE_ID/velocity/control and robot/control/cmd. Commands are JSON objects. Examples:

~~~bash
# Start or pause the simulator's telemetry session
docker compose exec mqtt-broker mosquitto_pub -h 127.0.0.1 -t omega/device-test/session/active -m '{"active":true}'

# Increment forward speed
docker compose exec mqtt-broker mosquitto_pub -h 127.0.0.1 -t omega/device-test/velocity/control -m '{"action":"FORWARD"}'

# Turn left (angular velocity)
docker compose exec mqtt-broker mosquitto_pub -h 127.0.0.1 -t omega/device-test/velocity/control -m '{"action":"LEFT"}'

# Stop linear and angular motion
docker compose exec mqtt-broker mosquitto_pub -h 127.0.0.1 -t omega/device-test/velocity/control -m '{"action":"STOP"}'
~~~

Direct velocity payloads are also supported:

~~~json
{"linear":{"x":0.5},"angular":{"z":0.2}}
~~~

The demo bridge clamps linear and angular commands to ±1.0. These bounds are for the simulator only; they are not a substitute for a hardware safety controller, dead-man switch, watchdog, or emergency stop. Video commands are supported using STREAM_START, STREAM_STOP, and SELECT_CAMERA:front_camera (also down_left and down_right).

## Run tests

The backend tests use Python's standard unittest framework:

~~~bash
python -m pip install -r telemetry_backend/requirements.txt
PYTHONPATH=telemetry_backend python -m unittest discover -s telemetry_backend/tests -v
~~~

To compile-check the Python sources without launching ROS:

~~~bash
python -m compileall -q ros2_mqtt_bridge ros2_video_streamer telemetry_backend db_init.py run_demo.py
~~~

A ROS 2 environment is required to build and run the ROS packages:

~~~bash
source /opt/ros/jazzy/setup.bash
cd ros2-jazzy
colcon build --symlink-install
source install/setup.bash
~~~

## Optional: stream recorded camera topics to LiveKit

The camera streamer is a separate companion workflow; it is not part of the core Compose services. It expects three ROS 2 bag directories or individual MCAP files with image topics. Individual .mcap files are played with the MCAP storage plugin. Build the optional video image or build the package in a ROS 2 Jazzy workspace. The included Dockerfile.video provides the containerized option.

Create a .env file or export the following values:

~~~dotenv
ROS2_RECORDINGS_DIR=./recordings
FRONT_BAG=/recordings/front_cam.mcap
LEFT_BAG=/recordings/left_cam.mcap
RIGHT_BAG=/recordings/right_cam.mcap
LIVEKIT_URL=wss://your-livekit-host
LIVEKIT_TOKEN=your-short-lived-token
# Alternatively use a token gateway:
GATEWAY_URL=http://host.docker.internal:8080
~~~

Place/mount the three bag files under the configured recordings directory and start the optional profile:

~~~bash
docker compose --profile video up --build video-demo
~~~

The camera topics can be changed with FRONT_CAMERA_TOPIC, LEFT_CAMERA_TOPIC, and RIGHT_CAMERA_TOPIC. The active camera is selected with ACTIVE_CAMERA (front_camera, down_left, or down_right). The token is read from the environment or fetched from GATEWAY_URL/api/rtc/token; it is not written to the repository. Use a short-lived token and do not commit credentials.

For host-side use, install ROS and Python video dependencies first:

~~~bash
sudo apt install ros-jazzy-cv-bridge python3-opencv python3-numpy
python -m pip install -r requirements-video.txt
source /opt/ros/jazzy/setup.bash
colcon build --symlink-install --packages-select ros2_video_streamer
source install/setup.bash
python3 run_demo.py --front-bag ./recordings/front.mcap --left-bag ./recordings/left.mcap --right-bag ./recordings/right.mcap
~~~

## MQTT security and physical hardware

The bundled Mosquitto configuration enables anonymous access but binds the broker to 127.0.0.1 only. The HTTP API also binds to loopback. Do not change these bindings or expose this broker to a LAN or public network without adding MQTT authentication/TLS and topic ACLs. Before using a real robot, validate command authorization, implement command expiry and a watchdog, and use an independent hardware emergency stop. The mock simulator's command limits are not a certified safety mechanism.

## Repository layout

~~~text
ros2_mqtt_bridge/          ROS 2 simulator and MQTT bridge
ros2_video_streamer/       optional LiveKit video streamer
telemetry_backend/         MQTT consumer, SQLite layer, FastAPI and tests
docker/                    container entrypoints
Dockerfile                 core ROS 2 Jazzy image
Dockerfile.video           optional camera replay/streaming image
docker-compose.yml         local core stack + optional video profile
~~~
