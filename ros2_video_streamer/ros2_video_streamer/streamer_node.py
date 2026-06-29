import asyncio
import sys
import threading
import requests
import cv2

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from cv_bridge import CvBridge

# Import LiveKit SDK (v1.5.x)
try:
    from livekit import rtc
except ImportError as e:
    import traceback
    print("--- LiveKit Import Error Details ---")
    traceback.print_exc()
    print("------------------------------------")
    sys.exit(1)


class Ros2VideoStreamer(Node):
    def __init__(self, room_url, token):
        super().__init__('ros2_video_streamer')
        self.bridge = CvBridge()
        self.room_url = room_url
        self.token = token
        self.sources = {}  # track_name -> rtc.VideoSource

        self.logger = self.get_logger()
        self.logger.info("Initializing ROS2 Video Streamer for LiveKit...")

        # Subscribe to replayed ROS2 bag image topics
        self.frame_counts = {'front_camera': 0, 'down_left': 0, 'down_right': 0}
        self.sub_front = self.create_subscription(
            Image,
            '/astra2_cam/color/image_raw',
            lambda msg: self.on_image_frame('front_camera', msg),
            10
        )
        self.sub_left = self.create_subscription(
            Image,
            '/cam_eth/color/image_raw',
            lambda msg: self.on_image_frame('down_left', msg),
            10
        )
        self.sub_right = self.create_subscription(
            Image,
            '/cam_usb/color/image_raw',
            lambda msg: self.on_image_frame('down_right', msg),
            10
        )

        # Run asyncio loop in background thread for LiveKit connection
        self.loop = asyncio.new_event_loop()
        self.async_thread = threading.Thread(target=self._run_async_loop, daemon=True)
        self.async_thread.start()

        # Connect to LiveKit room
        asyncio.run_coroutine_threadsafe(self._connect_room(), self.loop)

    def _run_async_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    async def _connect_room(self):
        self.logger.info(f"Connecting to LiveKit room at {self.room_url}...")
        self.room = rtc.Room()
        try:
            await self.room.connect(self.room_url, self.token)
            self.logger.info("Connected to LiveKit room successfully!")

            # Setup the three video tracks
            await self._setup_track('front_camera', 1280, 720)
            await self._setup_track('down_left', 640, 480)
            await self._setup_track('down_right', 640, 480)
        except Exception as e:
            self.logger.error(f"Failed to setup LiveKit tracks: {e}")

    async def _setup_track(self, track_name, width, height):
        # Create VideoSource (correct class in livekit SDK v1.5)
        source = rtc.VideoSource(width, height)
        track = rtc.LocalVideoTrack.create_video_track(track_name, source)

        # Publish track to the room
        options = rtc.TrackPublishOptions()
        options.source = rtc.TrackSource.SOURCE_CAMERA
        await self.room.local_participant.publish_track(track, options)
        self.sources[track_name] = {
            'source': source,
            'width': width,
            'height': height
        }
        self.logger.info(f"Published track '{track_name}' ({width}x{height})")

    def on_image_frame(self, track_name, msg):
        if track_name == 'front_camera':
            self.logger.info("Front camera callback triggered!")

        if track_name not in self.sources:
            return

        self.frame_counts[track_name] += 1

        try:
            # Convert ROS2 image message to OpenCV BGR frame
            cv_img = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')

            track_info = self.sources[track_name]
            width = track_info['width']
            height = track_info['height']

            # Resize if needed
            if cv_img.shape[1] != width or cv_img.shape[0] != height:
                cv_img = cv2.resize(cv_img, (width, height))

            # Convert BGR to RGBA (required by LiveKit v1.5)
            rgba_img = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGBA)

            # Create VideoFrame using correct v1.5 API
            frame = rtc.VideoFrame(
                width,
                height,
                rtc.VideoBufferType.RGBA,
                rgba_img.tobytes()
            )

            track_info['source'].capture_frame(frame)
        except Exception as e:
            self.logger.warn(f"Failed to process frame for {track_name}: {e}")

    def destroy_node(self):
        self.logger.info("Cleaning up streamer node connections...")
        if hasattr(self, 'room'):
            asyncio.run_coroutine_threadsafe(self.room.disconnect(), self.loop)
        self.loop.call_soon_threadsafe(self.loop.stop)
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)

    # Resolve connection info from local gateway (keeps secrets off the robot)
    gateway_url = "http://100.120.80.121:8080"
    livekit_url = "wss://prod.rtc.golain.io"
    token = ""

    try:
        print(f"Attempting secure token fetch from gateway: {gateway_url}...")
        resp = requests.get(
            f"{gateway_url}/api/rtc/token?identity=ericr-desktop",
            timeout=3
        )
        if resp.status_code == 200:
            data = resp.json()
            token = data.get("token")
            livekit_url = data.get("url", livekit_url)
            print("Successfully acquired signed temporary WebRTC JWT token!")
    except Exception as e:
        print(f"Warning: could not contact gateway token manager: {e}")

    if not token:
        if len(sys.argv) < 3:
            print("Gateway unreachable. Usage: python3 streamer_node.py <livekit_url> <token>")
            sys.exit(1)
        livekit_url = sys.argv[1]
        token = sys.argv[2]

    node = Ros2VideoStreamer(livekit_url, token)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
