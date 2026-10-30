"""Bidirectional ROS 2 / MQTT bridge for robot telemetry and commands."""
from __future__ import annotations

import json
import math
import os
import queue
import time

import paho.mqtt.client as mqtt
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import NavSatFix
from nav_msgs.msg import Odometry
from diagnostic_msgs.msg import DiagnosticArray
from rcl_interfaces.msg import Log as RosLog
from geometry_msgs.msg import Twist
from std_msgs.msg import Bool, String


MAX_LINEAR_SPEED = 1.0
MAX_ANGULAR_SPEED = 1.0


def finite_clamp(value, maximum: float, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if not math.isfinite(number):
        raise ValueError(f"{field} must be finite")
    return max(-maximum, min(maximum, number))


class MqttBridgeNode(Node):
    def __init__(self):
        super().__init__("mqtt_bridge_node")
        self.declare_parameter("mqtt_host", os.getenv("MQTT_HOST", "mqtt-broker"))
        self.declare_parameter("mqtt_port", int(os.getenv("MQTT_PORT", "1883")))
        self.declare_parameter("device_id", os.getenv("ROBOT_DEVICE_ID", "device-test"))
        self.declare_parameter("topic_root", os.getenv("MQTT_TOPIC_ROOT", "omega"))

        self.mqtt_host = self.get_parameter("mqtt_host").value
        self.mqtt_port = int(self.get_parameter("mqtt_port").value)
        self.device_id = str(self.get_parameter("device_id").value)
        self.topic_root = str(self.get_parameter("topic_root").value).strip("/")
        self.mqtt_prefix = f"{self.topic_root}/{self.device_id}"

        self.cmd_vel_pub = self.create_publisher(Twist, "/cmd_vel", 10)
        self.session_active_pub = self.create_publisher(Bool, "/session/active", 10)
        self.video_enable_pub = self.create_publisher(Bool, "/video_stream/enable", 10)
        self.video_select_pub = self.create_publisher(String, "/video_stream/select", 10)

        self.create_subscription(NavSatFix, "/gps/fix", self.gps_callback, 10)
        self.create_subscription(Odometry, "/odom", self.odom_callback, 10)
        self.create_subscription(DiagnosticArray, "/diagnostics", self.diagnostics_callback, 10)
        self.create_subscription(RosLog, "/rosout", self.rosout_callback, 10)

        self.target_speed = 0.0
        self.target_yaw_rate = 0.0
        # MQTT callbacks run on Paho's network thread. Queue commands and publish
        # ROS messages from the rclpy timer/executor thread instead.
        self.command_queue: queue.Queue[tuple[str, dict]] = queue.Queue(maxsize=200)
        self.command_timer = self.create_timer(0.05, self._drain_commands)

        self.mqtt_client = mqtt.Client(client_id=f"ros2-bridge-{self.device_id}")
        self.mqtt_client.on_connect = self.on_mqtt_connect
        self.mqtt_client.on_message = self.on_mqtt_message
        self.mqtt_client.reconnect_delay_set(min_delay=1, max_delay=30)
        self.get_logger().info(
            f"Connecting to MQTT broker at {self.mqtt_host}:{self.mqtt_port} "
            f"for device {self.device_id}"
        )
        self.mqtt_client.connect_async(self.mqtt_host, self.mqtt_port, keepalive=60)
        self.mqtt_client.loop_start()

    def on_mqtt_connect(self, client, userdata, flags, rc):
        if rc != 0:
            self.get_logger().error(f"MQTT connection failed with code {rc}")
            return
        subscriptions = [
            (f"{self.mqtt_prefix}/velocity/control", 1),
            (f"{self.mqtt_prefix}/session/active", 1),
            ("robot/control/cmd", 1),
        ]
        client.subscribe(subscriptions)
        self.get_logger().info("Connected to MQTT and subscribed to robot control topics")

    def on_mqtt_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("Command payload must be a JSON object")
            self.command_queue.put_nowait((msg.topic, payload))
        except queue.Full:
            self.get_logger().error("Command queue is full; dropping incoming MQTT command")
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            self.get_logger().warning(f"Ignoring invalid MQTT command: {exc}")

    def _drain_commands(self):
        for _ in range(50):
            try:
                topic, payload = self.command_queue.get_nowait()
            except queue.Empty:
                return
            try:
                self._handle_command(topic, payload)
            except (TypeError, ValueError) as exc:
                self.get_logger().warning(f"Rejected MQTT command on {topic}: {exc}")

    def _handle_command(self, topic: str, payload: dict):
        if topic == f"{self.mqtt_prefix}/session/active":
            active = payload.get("active", False)
            if not isinstance(active, bool):
                raise ValueError("session active value must be a JSON boolean")
            message = Bool()
            message.data = active
            self.session_active_pub.publish(message)
            return

        action = str(payload.get("action", "")).upper()
        if action in {"STREAM_STOP", "STREAM_PAUSE", "STREAM_OFF", "DISABLE_STREAM"}:
            message = Bool()
            message.data = False
            self.video_enable_pub.publish(message)
            return
        if action in {"STREAM_START", "STREAM_RESUME", "STREAM_ON", "ENABLE_STREAM"}:
            message = Bool()
            message.data = True
            self.video_enable_pub.publish(message)
            return
        if action.startswith(("SELECT_CAMERA:", "CAM_SELECT:", "SELECT_CAM:")):
            camera = action.split(":", 1)[1].strip().lower()
            if camera not in {"front_camera", "down_left", "down_right"}:
                raise ValueError(f"Unknown camera selection: {camera}")
            message = String()
            message.data = camera
            self.video_select_pub.publish(message)
            return

        if action == "FORWARD":
            self.target_speed = finite_clamp(self.target_speed + 0.1, MAX_LINEAR_SPEED, "linear speed")
        elif action in {"REVERSE", "BACKWARD"}:
            self.target_speed = finite_clamp(self.target_speed - 0.1, MAX_LINEAR_SPEED, "linear speed")
        elif action in {"STOP", "E-STOP"}:
            self.target_speed = 0.0
            self.target_yaw_rate = 0.0
        elif action == "LEFT":
            self.target_yaw_rate = finite_clamp(self.target_yaw_rate + 0.1, MAX_ANGULAR_SPEED, "angular speed")
        elif action == "RIGHT":
            self.target_yaw_rate = finite_clamp(self.target_yaw_rate - 0.1, MAX_ANGULAR_SPEED, "angular speed")
        elif not action:
            linear = payload.get("linear", {})
            angular = payload.get("angular", {})
            if not isinstance(linear, dict) or not isinstance(angular, dict):
                raise ValueError("linear and angular commands must be JSON objects")
            self.target_speed = finite_clamp(linear.get("x", self.target_speed), MAX_LINEAR_SPEED, "linear.x")
            self.target_yaw_rate = finite_clamp(angular.get("z", self.target_yaw_rate), MAX_ANGULAR_SPEED, "angular.z")
        else:
            raise ValueError(f"Unknown command action: {action}")

        twist = Twist()
        twist.linear.x = self.target_speed
        twist.angular.z = self.target_yaw_rate
        self.cmd_vel_pub.publish(twist)
        self.get_logger().info(
            f"Published velocity command: linear.x={twist.linear.x:.2f}, "
            f"angular.z={twist.angular.z:.2f}"
        )

    def publish_mqtt(self, topic: str, data: dict):
        if not self.mqtt_client.is_connected():
            return
        result = self.mqtt_client.publish(topic, json.dumps(data), qos=1)
        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            self.get_logger().warning(f"MQTT publish returned status {result.rc} for {topic}")

    @staticmethod
    def timestamp(stamp) -> str:
        seconds = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(stamp.sec))
        return f"{seconds}.{stamp.nanosec:09d}Z"

    def gps_callback(self, msg: NavSatFix):
        self.publish_mqtt(f"{self.mqtt_prefix}/telemetry/gps", {
            "latitude": msg.latitude,
            "longitude": msg.longitude,
            "altitude": msg.altitude,
            "status": int(msg.status.status),
            "timestamp": self.timestamp(msg.header.stamp),
        })

    def odom_callback(self, msg: Odometry):
        q = msg.pose.pose.orientation
        siny_cosp = 2.0 * (q.w * q.z + q.x * q.y)
        cosy_cosp = 1.0 - 2.0 * (q.y * q.y + q.z * q.z)
        direction = math.degrees(math.atan2(siny_cosp, cosy_cosp)) % 360.0
        self.publish_mqtt(f"{self.mqtt_prefix}/telemetry/odom", {
            "linear_speed": msg.twist.twist.linear.x,
            "angular_speed": msg.twist.twist.angular.z,
            "direction": round(direction, 2),
            "x": msg.pose.pose.position.x,
            "y": msg.pose.pose.position.y,
            "z": msg.pose.pose.position.z,
            "timestamp": self.timestamp(msg.header.stamp),
        })

    def diagnostics_callback(self, msg: DiagnosticArray):
        timestamp = self.timestamp(msg.header.stamp)
        levels = {0: "OK", 1: "WARN", 2: "ERROR", 3: "STALE"}
        for status in msg.status:
            self.publish_mqtt(f"{self.mqtt_prefix}/diagnostics", {
                "level": levels.get(int(status.level), "UNKNOWN"),
                "message": status.message,
                "hardware_id": status.hardware_id,
                "timestamp": timestamp,
            })

    def rosout_callback(self, msg: RosLog):
        if msg.name == self.get_name():
            return
        levels = {10: "DEBUG", 20: "INFO", 30: "WARN", 40: "ERROR", 50: "FATAL"}
        self.publish_mqtt(f"{self.mqtt_prefix}/logs", {
            "level": levels.get(int(msg.level), "UNKNOWN"),
            "logger_name": msg.name,
            "message": msg.msg,
            "timestamp": self.timestamp(msg.stamp),
        })

    def destroy_node(self):
        self.mqtt_client.loop_stop()
        if self.mqtt_client.is_connected():
            self.mqtt_client.disconnect()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = MqttBridgeNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
