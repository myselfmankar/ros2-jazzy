import json
import os
import time
import rclpy
from rclpy.node import Node

from sensor_msgs.msg import NavSatFix
from nav_msgs.msg import Odometry
from diagnostic_msgs.msg import DiagnosticArray
from rcl_interfaces.msg import Log as RosLog
from geometry_msgs.msg import Twist, Vector3
from std_msgs.msg import Bool

import paho.mqtt.client as mqtt

class MqttBridgeNode(Node):
    def __init__(self):
        super().__init__('mqtt_bridge_node')
        self.get_logger().info("Initializing ROS2-MQTT Bridge Node...")

        # Get configurations from parameters (or use defaults)
        self.declare_parameter('mqtt_host', 'mqtt-broker')
        self.declare_parameter('mqtt_port', 1883)
        self.declare_parameter('device_id', 'device-test')

        self.mqtt_host = self.get_parameter('mqtt_host').get_parameter_value().string_value
        self.mqtt_port = self.get_parameter('mqtt_port').get_parameter_value().integer_value
        self.device_id = self.get_parameter('device_id').get_parameter_value().string_value

        self.mqtt_prefix = f"omega/{self.device_id}"

        # Initialize MQTT Client
        self.mqtt_client = mqtt.Client()
        self.mqtt_client.on_connect = self.on_mqtt_connect
        self.mqtt_client.on_message = self.on_mqtt_message
        
        self.get_logger().info(f"Connecting to MQTT broker at {self.mqtt_host}:{self.mqtt_port}...")
        try:
            self.mqtt_client.connect(self.mqtt_host, self.mqtt_port, 60)
            self.mqtt_client.loop_start()
        except Exception as e:
            self.get_logger().error(f"Failed to connect to MQTT broker: {str(e)}. Will run offline.")

        # ROS2 Publishers
        self.cmd_vel_pub = self.create_publisher(Twist, '/cmd_vel', 10)
        self.session_active_pub = self.create_publisher(Bool, '/session/active', 10)

        # ROS2 Subscriptions
        self.create_subscription(NavSatFix, '/gps/fix', self.gps_callback, 10)
        self.create_subscription(Odometry, '/odom', self.odom_callback, 10)
        self.create_subscription(DiagnosticArray, '/diagnostics', self.diagnostics_callback, 10)
        self.create_subscription(RosLog, '/rosout', self.rosout_callback, 10)

        # Control state tracking for incremental speed changes
        self.target_speed = 0.0
        self.target_yaw_rate = 0.0

    def on_mqtt_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self.get_logger().info("Successfully connected to MQTT broker.")
            # Subscribe to command topics
            self.mqtt_client.subscribe(f"{self.mqtt_prefix}/velocity/control")
            self.mqtt_client.subscribe(f"{self.mqtt_prefix}/session/active")
            self.mqtt_client.subscribe("robot/control/cmd")
            self.get_logger().info(f"Subscribed to MQTT control topics: {self.mqtt_prefix}/velocity/control, {self.mqtt_prefix}/session/active, and robot/control/cmd")
        else:
            self.get_logger().error(f"MQTT connection failed with code {rc}")

    def on_mqtt_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
            
            # Handle session/active topic
            if msg.topic == f"{self.mqtt_prefix}/session/active":
                active = payload.get('active', False)
                self.get_logger().info(f"Received session active signal from MQTT: {active}")
                bool_msg = Bool()
                bool_msg.data = bool(active)
                self.session_active_pub.publish(bool_msg)
                return

            self.get_logger().info(f"Received MQTT command: {payload}")
            
            twist = Twist()
            action = payload.get('action')

            if action:
                # Handle incremental actions from UI buttons
                if action == 'FORWARD':
                    self.target_speed = min(2.0, self.target_speed + 0.1)
                    self.get_logger().info(f"Incrementing target speed: {self.target_speed:.2f} m/s")
                elif action in ('REVERSE', 'BACKWARD'):
                    self.target_speed = max(-2.0, self.target_speed - 0.1)
                    self.get_logger().info(f"Decrementing target speed: {self.target_speed:.2f} m/s")
                elif action in ('STOP', 'E-STOP'):
                    self.target_speed = 0.0
                    self.target_yaw_rate = 0.0
                    self.get_logger().info("Stopping robot (speed set to 0)")
                elif action == 'LEFT':
                    self.target_yaw_rate = min(1.0, self.target_yaw_rate + 0.05)
                elif action == 'RIGHT':
                    self.target_yaw_rate = max(-1.0, self.target_yaw_rate - 0.05)

                twist.linear.x = self.target_speed
                twist.angular.z = self.target_yaw_rate
            else:
                # Fallback to direct speed/rate command if dict properties are present
                linear = payload.get('linear', {})
                angular = payload.get('angular', {})
                self.target_speed = float(linear.get('x', self.target_speed))
                self.target_yaw_rate = float(angular.get('z', self.target_yaw_rate))
                
                twist.linear.x = self.target_speed
                twist.angular.z = self.target_yaw_rate

            self.cmd_vel_pub.publish(twist)
            self.get_logger().info(f"Published Twist control: linear.x={twist.linear.x:.2f}, angular.z={twist.angular.z:.2f}")
        except Exception as e:
            self.get_logger().error(f"Error handling MQTT control message: {str(e)}")

    def publish_mqtt(self, topic, data):
        if self.mqtt_client.is_connected():
            try:
                self.mqtt_client.publish(topic, json.dumps(data))
            except Exception as e:
                self.get_logger().error(f"MQTT publish error: {str(e)}")

    def gps_callback(self, msg):
        timestamp = time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime(msg.header.stamp.sec)) + f".{msg.header.stamp.nanosec:09d}Z"
        
        payload = {
            'latitude': msg.latitude,
            'longitude': msg.longitude,
            'altitude': msg.altitude,
            'status': int(msg.status.status),
            'timestamp': timestamp
        }

        # Publish to MQTT
        self.publish_mqtt(f"{self.mqtt_prefix}/telemetry/gps", payload)

    def odom_callback(self, msg):
        timestamp = time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime(msg.header.stamp.sec)) + f".{msg.header.stamp.nanosec:09d}Z"
        
        # Calculate speed and yaw from quaternion
        linear_speed = msg.twist.twist.linear.x
        angular_speed = msg.twist.twist.angular.z
        
        q = msg.pose.pose.orientation
        import math
        siny_cosp = 2 * (q.w * q.z + q.x * q.y)
        cosy_cosp = 1 - 2 * (q.y * q.y + q.z * q.z)
        direction = float(round(abs(360 + (360 * (math.atan2(siny_cosp, cosy_cosp) / (2 * math.pi)))) % 360, 2))

        payload = {
            'linear_speed': linear_speed,
            'angular_speed': angular_speed,
            'direction': direction,
            'x': msg.pose.pose.position.x,
            'y': msg.pose.pose.position.y,
            'z': msg.pose.pose.position.z,
            'timestamp': timestamp
        }

        # Publish to MQTT
        self.publish_mqtt(f"{self.mqtt_prefix}/telemetry/odom", payload)

    def diagnostics_callback(self, msg):
        timestamp = time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime(msg.header.stamp.sec)) + f".{msg.header.stamp.nanosec:09d}Z"
        
        levels = {0: 'OK', 1: 'WARN', 2: 'ERROR', 3: 'STALE'}

        for status in msg.status:
            level_int = ord(status.level) if isinstance(status.level, (bytes, str)) else int(status.level)
            level_str = levels.get(level_int, 'UNKNOWN')
            
            payload = {
                'level': level_str,
                'message': status.message,
                'hardware_id': status.hardware_id,
                'timestamp': timestamp
            }

            # Publish to MQTT
            self.publish_mqtt(f"{self.mqtt_prefix}/diagnostics", payload)

    def rosout_callback(self, msg):
        # Exclude logger from this node to prevent loop logging
        if msg.name == self.get_name():
            return

        timestamp = time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime(msg.stamp.sec)) + f".{msg.stamp.nanosec:09d}Z"
        
        levels = {10: 'DEBUG', 20: 'INFO', 30: 'WARN', 40: 'ERROR', 50: 'FATAL'}
        level_str = levels.get(int(msg.level), 'UNKNOWN')

        payload = {
            'level': level_str,
            'logger_name': msg.name,
            'message': msg.msg,
            'timestamp': timestamp
        }

        # Publish to MQTT
        self.publish_mqtt(f"{self.mqtt_prefix}/logs", payload)

def main(args=None):
    rclpy.init(args=args)
    node = MqttBridgeNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.mqtt_client.loop_stop()
        node.mqtt_client.disconnect()
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
