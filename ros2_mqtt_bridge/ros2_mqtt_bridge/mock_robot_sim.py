"""Simple differential-drive-style robot simulator publishing ROS 2 telemetry."""
from __future__ import annotations

import math
import random

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import NavSatFix, NavSatStatus
from nav_msgs.msg import Odometry
from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus, KeyValue
from geometry_msgs.msg import Point, Quaternion, Twist, Vector3
from std_msgs.msg import Bool

MAX_LINEAR_SPEED = 1.0
MAX_ANGULAR_SPEED = 1.0


class MockRobotSim(Node):
    """Publishes synthetic GPS, odometry and diagnostics for local testing."""

    def __init__(self):
        super().__init__("mock_robot_sim")
        self.get_logger().info("Starting mock robot simulation near Swargate, Pune")
        # Start near Swargate and point towards the next illustrative route waypoint.
        self.origin_lat = 18.49959
        self.origin_lon = 73.85781
        next_lat, next_lon = 18.51340, 73.85490
        dy = (next_lat - self.origin_lat) * 111139.0
        dx = (next_lon - self.origin_lon) * 111139.0 * math.cos(math.radians(self.origin_lat))
        self.theta = math.atan2(dy, dx)

        self.x = 0.0
        self.y = 0.0
        self.lat = self.origin_lat
        self.lon = self.origin_lon
        self.altitude = 215.0
        self.current_speed = 0.0
        self.target_speed = 0.0
        self.target_yaw_rate = 0.0
        self.battery = 100.0
        self.active = False

        self.gps_pub = self.create_publisher(NavSatFix, "/gps/fix", 10)
        self.odom_pub = self.create_publisher(Odometry, "/odom", 10)
        self.diag_pub = self.create_publisher(DiagnosticArray, "/diagnostics", 10)
        self.create_subscription(Twist, "/cmd_vel", self.cmd_vel_callback, 10)
        self.create_subscription(Bool, "/session/active", self.session_callback, 10)
        self.timer = self.create_timer(1.0, self.timer_callback)

    def cmd_vel_callback(self, msg: Twist):
        # Keep synthetic commands bounded. Hardware deployments need their own
        # independent safety controller and emergency stop.
        linear = float(msg.linear.x)
        angular = float(msg.angular.z)
        if not math.isfinite(linear) or not math.isfinite(angular):
            self.get_logger().warning("Ignoring non-finite velocity command")
            return
        self.target_speed = max(-MAX_LINEAR_SPEED, min(MAX_LINEAR_SPEED, linear))
        self.target_yaw_rate = max(-MAX_ANGULAR_SPEED, min(MAX_ANGULAR_SPEED, angular))

    def session_callback(self, msg: Bool):
        self.active = bool(msg.data)
        if not self.active:
            self.target_speed = 0.0
            self.target_yaw_rate = 0.0
            self.current_speed = 0.0
            self.get_logger().info("Session paused; telemetry publishing stopped")
        else:
            self.get_logger().info("Session active; telemetry publishing started")

    def timer_callback(self):
        if not self.active:
            return

        dt = 1.0
        acceleration = 0.5
        if self.current_speed < self.target_speed:
            self.current_speed = min(self.target_speed, self.current_speed + acceleration * dt)
        elif self.current_speed > self.target_speed:
            self.current_speed = max(self.target_speed, self.current_speed - acceleration * dt)

        self.theta = (self.theta + self.target_yaw_rate * dt + math.pi) % (2.0 * math.pi) - math.pi
        self.x += math.cos(self.theta) * self.current_speed * dt
        self.y += math.sin(self.theta) * self.current_speed * dt
        self.lat = self.origin_lat + self.y / 111139.0
        longitude_scale = 111139.0 * math.cos(math.radians(self.origin_lat))
        self.lon = self.origin_lon + self.x / longitude_scale
        self.battery = max(0.0, self.battery - 0.01)

        now = self.get_clock().now().to_msg()
        gps = NavSatFix()
        gps.header.stamp = now
        gps.header.frame_id = "gps_sensor"
        gps.status.status = NavSatStatus.STATUS_FIX
        gps.status.service = NavSatStatus.SERVICE_GPS
        gps.latitude = self.lat
        gps.longitude = self.lon
        gps.altitude = self.altitude
        gps.position_covariance = [0.1, 0.0, 0.0, 0.0, 0.1, 0.0, 0.0, 0.0, 0.1]
        gps.position_covariance_type = NavSatFix.COVARIANCE_TYPE_APPROXIMATED
        self.gps_pub.publish(gps)

        odom = Odometry()
        odom.header.stamp = now
        odom.header.frame_id = "odom"
        odom.child_frame_id = "base_link"
        odom.pose.pose.position = Point(x=self.x, y=self.y, z=0.0)
        half_yaw = self.theta * 0.5
        odom.pose.pose.orientation = Quaternion(x=0.0, y=0.0, z=math.sin(half_yaw), w=math.cos(half_yaw))
        odom.twist.twist.linear = Vector3(x=self.current_speed, y=0.0, z=0.0)
        odom.twist.twist.angular = Vector3(x=0.0, y=0.0, z=self.target_yaw_rate)
        self.odom_pub.publish(odom)

        diagnostics = DiagnosticArray()
        diagnostics.header.stamp = now
        battery = DiagnosticStatus()
        battery.name = "power_system: Battery"
        battery.hardware_id = "battery_pack_0"
        battery.level = DiagnosticStatus.OK if self.battery > 20 else DiagnosticStatus.WARN
        battery.message = f"Simulated battery charge at {self.battery:.1f}%"
        battery.values = [KeyValue(key="charge", value=f"{self.battery:.2f}%")]
        diagnostics.status.append(battery)

        cpu_load = random.uniform(20.0, 85.0)
        cpu = DiagnosticStatus()
        cpu.name = "compute: CPU"
        cpu.hardware_id = "onboard_pc"
        cpu.level = DiagnosticStatus.OK if cpu_load < 80 else DiagnosticStatus.WARN
        cpu.message = f"Simulated CPU load at {cpu_load:.1f}%"
        cpu.values = [KeyValue(key="load", value=f"{cpu_load:.2f}%")]
        diagnostics.status.append(cpu)
        if random.random() < 0.02:
            fault = DiagnosticStatus()
            fault.name = "motors: Wheel Driver"
            fault.hardware_id = "driver_left"
            fault.level = DiagnosticStatus.ERROR
            fault.message = "Simulated driver communication fault"
            diagnostics.status.append(fault)
        self.diag_pub.publish(diagnostics)

        if random.random() < 0.15:
            self.get_logger().info(
                f"Simulated pose lat={self.lat:.6f}, lon={self.lon:.6f}, "
                f"speed={self.current_speed:.2f} m/s"
            )


def main(args=None):
    rclpy.init(args=args)
    node = MockRobotSim()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
