import math
import random
import rclpy
from rclpy.node import Node

from sensor_msgs.msg import NavSatFix, NavSatStatus
from nav_msgs.msg import Odometry
from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus, KeyValue
from geometry_msgs.msg import Point, Pose, Quaternion, Twist, Vector3

class MockRobotSim(Node):
    def __init__(self):
        super().__init__('mock_robot_sim')
        self.get_logger().info("Initializing Mock Robot Simulation Node (Pune Metro Route)...")

        # Publishers
        self.gps_pub = self.create_publisher(NavSatFix, '/gps/fix', 10)
        self.odom_pub = self.create_publisher(Odometry, '/odom', 10)
        self.diag_pub = self.create_publisher(DiagnosticArray, '/diagnostics', 10)

        # Swargate -> Mandai -> Kasba Peth -> Civil Court (Pune Metro Route)
        self.route = [
            (18.49959, 73.85781),  # Swargate
            (18.51340, 73.85490),  # Mandai
            (18.52122, 73.85953),  # Kasba Peth
            (18.52678, 73.85712)   # Civil Court
        ]

        # Calculate segment lengths in meters
        self.segments = []
        for i in range(len(self.route) - 1):
            lat1, lon1 = self.route[i]
            lat2, lon2 = self.route[i+1]
            dy = (lat2 - lat1) * 111139.0
            dx = (lon2 - lon1) * 111139.0 * math.cos(math.radians((lat1 + lat2) / 2))
            length = math.sqrt(dx**2 + dy**2)
            self.segments.append((dx, dy, length))

        # Simulation states
        self.current_segment = 0
        self.segment_progress = 0.0  # 0.0 to 1.0
        self.speed = 1.0  # m/s (can be adjusted via /cmd_vel)
        self.alt = 215.0
        self.lat, self.lon = self.route[0]
        self.theta = 0.0
        self.x = 0.0
        self.y = 0.0
        self.battery = 100.0

        # Subscribe to /cmd_vel for speed changes
        self.cmd_vel_sub = self.create_subscription(
            Twist,
            '/cmd_vel',
            self.cmd_vel_callback,
            10
        )

        # Timer (1 Hz)
        self.timer = self.create_timer(1.0, self.timer_callback)

    def cmd_vel_callback(self, msg):
        self.speed = msg.linear.x
        self.get_logger().info(f"Speed set to: {self.speed:.2f} m/s")

    def timer_callback(self):
        dt = 1.0
        
        # 1. Update simulation physics along the route
        if self.speed != 0.0 and len(self.segments) > 0:
            dx, dy, length = self.segments[self.current_segment]
            
            # Progress step
            progress_step = (self.speed * dt) / length
            self.segment_progress += progress_step
            
            # Check bounds and segment transition
            if self.segment_progress >= 1.0:
                self.current_segment = (self.current_segment + 1) % len(self.segments)
                self.segment_progress = 0.0
            elif self.segment_progress < 0.0:
                self.current_segment = (self.current_segment - 1) % len(self.segments)
                self.segment_progress = 1.0 - abs(self.segment_progress)

            # Interpolate position
            p1 = self.route[self.current_segment]
            p2 = self.route[self.current_segment + 1]
            self.lat = p1[0] + self.segment_progress * (p2[0] - p1[0])
            self.lon = p1[1] + self.segment_progress * (p2[1] - p1[1])
            
            # Calculate heading angle (East is 0 rad, North is PI/2 rad)
            self.theta = math.atan2(dy, dx)
            
            # Compute local metric coordinates from start (Swargate)
            self.x = (self.lon - self.route[0][1]) * 111139.0 * math.cos(math.radians(self.route[0][0]))
            self.y = (self.lat - self.route[0][0]) * 111139.0

        # Update battery status
        self.battery = max(0.0, self.battery - 0.05)

        # 2. Publish GPS Fix
        gps_msg = NavSatFix()
        gps_msg.header.stamp = self.get_clock().now().to_msg()
        gps_msg.header.frame_id = 'gps_sensor'
        gps_msg.status.status = NavSatStatus.STATUS_FIX
        gps_msg.status.service = NavSatStatus.SERVICE_GPS
        gps_msg.latitude = self.lat
        gps_msg.longitude = self.lon
        gps_msg.altitude = self.alt
        gps_msg.position_covariance = [0.1, 0.0, 0.0, 0.0, 0.1, 0.0, 0.0, 0.0, 0.1]
        gps_msg.position_covariance_type = NavSatFix.COVARIANCE_TYPE_UNKNOWN
        self.gps_pub.publish(gps_msg)

        # 3. Publish Odometry
        odom_msg = Odometry()
        odom_msg.header.stamp = self.get_clock().now().to_msg()
        odom_msg.header.frame_id = 'odom'
        odom_msg.child_frame_id = 'base_link'
        
        # Position
        odom_msg.pose.pose.position = Point(x=self.x, y=self.y, z=0.0)
        # Orientation (z-axis rotation theta to quaternion)
        cy = math.cos(self.theta * 0.5)
        sy = math.sin(self.theta * 0.5)
        odom_msg.pose.pose.orientation = Quaternion(x=0.0, y=0.0, z=sy, w=cy)
        
        # Velocity
        odom_msg.twist.twist.linear = Vector3(x=self.speed, y=0.0, z=0.0)
        odom_msg.twist.twist.angular = Vector3(x=0.0, y=0.0, z=0.0)
        self.odom_pub.publish(odom_msg)

        # 4. Publish Diagnostics
        diag_msg = DiagnosticArray()
        diag_msg.header.stamp = self.get_clock().now().to_msg()

        # Battery Status
        battery_status = DiagnosticStatus()
        battery_status.name = 'power_system: Battery'
        battery_status.hardware_id = 'battery_pack_0'
        battery_status.level = DiagnosticStatus.OK if self.battery > 20 else DiagnosticStatus.WARN
        battery_status.message = f"Battery charge at {self.battery:.1f}%"
        battery_status.values = [KeyValue(key='charge', value=f"{self.battery:.2f}%")]
        diag_msg.status.append(battery_status)

        # CPU Status
        cpu_load = random.uniform(20.0, 85.0)
        cpu_status = DiagnosticStatus()
        cpu_status.name = 'compute: CPU'
        cpu_status.hardware_id = 'onboard_pc'
        cpu_status.level = DiagnosticStatus.OK if cpu_load < 80 else DiagnosticStatus.WARN
        cpu_status.message = f"CPU Load at {cpu_load:.1f}%"
        cpu_status.values = [KeyValue(key='load', value=f"{cpu_load:.2f}%")]
        diag_msg.status.append(cpu_status)

        # Inject periodic random hardware warnings/errors
        if random.random() < 0.05:
            self.get_logger().error("Hardware Fault: Wheel driver communications timeout!")
            fault_status = DiagnosticStatus()
            fault_status.name = 'motors: Wheel Driver'
            fault_status.hardware_id = 'driver_left'
            fault_status.level = DiagnosticStatus.ERROR
            fault_status.message = "Driver communication loss"
            diag_msg.status.append(fault_status)
        elif random.random() < 0.10:
            self.get_logger().warning("Sensor Warning: LIDAR cleaning recommended (high dust/refraction).")

        self.diag_pub.publish(diag_msg)

        # Periodic logging
        if random.random() < 0.15:
            self.get_logger().info(f"Simulating Metro route. Pos: ({self.lat:.5f}, {self.lon:.5f}), Speed: {self.speed:.2f} m/s")

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

if __name__ == '__main__':
    main()
