"""Publish selected ROS 2 camera image topics to a LiveKit room."""
from __future__ import annotations

import asyncio
import os
import threading
import time

import cv2
import rclpy
import requests
from cv_bridge import CvBridge
from rclpy.node import Node
from sensor_msgs.msg import Image
from std_msgs.msg import Bool, String
from livekit import rtc


CAMERAS = ("front_camera", "down_left", "down_right")


class Ros2VideoStreamer(Node):
    def __init__(self, room_url: str, token: str):
        super().__init__("ros2_video_streamer")
        self.bridge = CvBridge()
        self.room_url = room_url
        self.token = token
        self.sources: dict[str, dict] = {}
        self.streaming_enabled = True
        requested_camera = os.getenv("ACTIVE_CAMERA", "front_camera")
        self.active_camera = requested_camera if requested_camera in CAMERAS else "front_camera"

        self.declare_parameter("front_camera_topic", os.getenv("FRONT_CAMERA_TOPIC", "/astra2_cam/color/image_raw"))
        self.declare_parameter("left_camera_topic", os.getenv("LEFT_CAMERA_TOPIC", "/cam_eth/color/image_raw"))
        self.declare_parameter("right_camera_topic", os.getenv("RIGHT_CAMERA_TOPIC", "/cam_usb/color/image_raw"))
        front_topic = str(self.get_parameter("front_camera_topic").value)
        left_topic = str(self.get_parameter("left_camera_topic").value)
        right_topic = str(self.get_parameter("right_camera_topic").value)

        self.get_logger().info("Starting ROS 2 camera to LiveKit video streamer")
        self.get_logger().info(f"Active camera: {self.active_camera}")
        self.frame_counts = {camera: 0 for camera in CAMERAS}
        self.sub_front = self.create_subscription(
            Image, front_topic, lambda msg: self.on_image_frame("front_camera", msg), 10
        )
        self.sub_left = self.create_subscription(
            Image, left_topic, lambda msg: self.on_image_frame("down_left", msg), 10
        )
        self.sub_right = self.create_subscription(
            Image, right_topic, lambda msg: self.on_image_frame("down_right", msg), 10
        )
        self.sub_enable = self.create_subscription(Bool, "/video_stream/enable", self.video_enable_callback, 10)
        self.sub_select = self.create_subscription(String, "/video_stream/select", self.video_select_callback, 10)

        self.loop = asyncio.new_event_loop()
        self.async_thread = threading.Thread(target=self._run_async_loop, name="livekit-asyncio", daemon=True)
        self.async_thread.start()
        self.room = None
        self.connect_future = asyncio.run_coroutine_threadsafe(self._connect_room(), self.loop)

    def _run_async_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    async def _connect_room(self):
        self.room = rtc.Room()
        try:
            await self.room.connect(self.room_url, self.token)
            self.get_logger().info("Connected to LiveKit room")
            await self._setup_track("front_camera", 1280, 720)
            await self._setup_track("down_left", 640, 480)
            await self._setup_track("down_right", 640, 480)
        except Exception as exc:
            self.get_logger().error(f"Could not connect or publish LiveKit tracks: {exc}")

    async def _setup_track(self, name: str, width: int, height: int):
        source = rtc.VideoSource(width, height)
        track = rtc.LocalVideoTrack.create_video_track(name, source)
        options = rtc.TrackPublishOptions()
        options.source = rtc.TrackSource.SOURCE_CAMERA
        await self.room.local_participant.publish_track(track, options)
        self.sources[name] = {"source": source, "width": width, "height": height}
        self.get_logger().info(f"Published {name} ({width}x{height})")

    def video_enable_callback(self, msg: Bool):
        self.streaming_enabled = bool(msg.data)
        self.get_logger().info(f"Video publishing {'enabled' if self.streaming_enabled else 'paused'}")

    def video_select_callback(self, msg: String):
        camera = str(msg.data).strip()
        if camera in CAMERAS:
            self.active_camera = camera
            self.get_logger().info(f"Selected camera: {camera}")
        else:
            self.get_logger().warning(f"Ignoring unknown camera: {camera}")

    def on_image_frame(self, camera: str, msg: Image):
        if not self.streaming_enabled or camera != self.active_camera:
            return
        track_info = self.sources.get(camera)
        if track_info is None:
            return
        try:
            image = self.bridge.imgmsg_to_cv2(msg, desired_encoding="bgr8")
            width, height = track_info["width"], track_info["height"]
            if image.shape[1] != width or image.shape[0] != height:
                image = cv2.resize(image, (width, height), interpolation=cv2.INTER_AREA)
            rgba = cv2.cvtColor(image, cv2.COLOR_BGR2RGBA)
            frame = rtc.VideoFrame(width, height, rtc.VideoBufferType.RGBA, rgba.tobytes())
            track_info["source"].capture_frame(frame)
            self.frame_counts[camera] += 1
            if self.frame_counts[camera] == 1:
                self.get_logger().info(f"First frame published for {camera}")
        except Exception as exc:
            self.get_logger().warning(f"Could not publish frame from {camera}: {exc}")

    def destroy_node(self):
        if getattr(self, "loop", None) and self.loop.is_running():
            room = getattr(self, "room", None)
            if room is not None:
                future = asyncio.run_coroutine_threadsafe(room.disconnect(), self.loop)
                try:
                    future.result(timeout=5)
                except Exception as exc:
                    self.get_logger().warning(f"LiveKit disconnect did not complete cleanly: {exc}")
            self.loop.call_soon_threadsafe(self.loop.stop)
            if getattr(self, "async_thread", None):
                self.async_thread.join(timeout=2)
        super().destroy_node()


def _connection_details() -> tuple[str, str]:
    livekit_url = os.getenv("LIVEKIT_URL", "").strip()
    token = os.getenv("LIVEKIT_TOKEN", "").strip()
    gateway_url = (os.getenv("GATEWAY_URL") or os.getenv("token_gateway_url") or "").strip()

    if not token and gateway_url:
        identity = os.getenv("LIVEKIT_IDENTITY", "ros2-video-demo")
        response = requests.get(
            f"{gateway_url.rstrip('/')}/api/rtc/token",
            params={"identity": identity},
            timeout=5,
        )
        response.raise_for_status()
        data = response.json()
        token = str(data.get("token", "")).strip()
        livekit_url = str(data.get("url") or livekit_url).strip()

    if not token or not livekit_url:
        raise RuntimeError("Set LIVEKIT_URL and LIVEKIT_TOKEN, or configure GATEWAY_URL to return both.")
    return livekit_url, token


def main(args=None):
    rclpy.init(args=args)
    try:
        livekit_url, token = _connection_details()
    except Exception as exc:
        print(f"LiveKit configuration error: {exc}")
        rclpy.shutdown()
        return

    node = Ros2VideoStreamer(livekit_url, token)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
