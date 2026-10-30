"""Replay three camera bags and start the ROS 2 LiveKit streamer.

Example:
  python3 run_demo.py --front-bag ./recordings/front.mcap \
    --left-bag ./recordings/left.mcap --right-bag ./recordings/right.mcap
"""
from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Replay three ROS 2 image bags and publish the selected camera to LiveKit."
    )
    parser.add_argument("--front-bag", required=True, help="Path to front camera ROS 2 bag")
    parser.add_argument("--left-bag", required=True, help="Path to left camera ROS 2 bag")
    parser.add_argument("--right-bag", required=True, help="Path to right camera ROS 2 bag")
    parser.add_argument("--startup-wait", type=float, default=3.0, help="Seconds to wait for bag topics")
    return parser.parse_args()


def stop_processes(processes: list[subprocess.Popen]) -> None:
    for process in processes:
        if process.poll() is None:
            process.terminate()
    for process in processes:
        if process.poll() is None:
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)


def main() -> int:
    args = parse_args()
    bag_paths = {
        "Front": Path(args.front_bag).expanduser(),
        "Down-left": Path(args.left_bag).expanduser(),
        "Down-right": Path(args.right_bag).expanduser(),
    }
    missing = [f"{label}: {path}" for label, path in bag_paths.items() if not path.exists()]
    if missing:
        print("Camera bag file(s) not found:")
        print("\n".join(missing))
        return 2

    has_direct_credentials = bool(os.getenv("LIVEKIT_URL") and os.getenv("LIVEKIT_TOKEN"))
    has_token_gateway = bool(os.getenv("GATEWAY_URL"))
    if not (has_direct_credentials or has_token_gateway):
        print("Set LIVEKIT_URL and LIVEKIT_TOKEN, or configure GATEWAY_URL.")
        return 2

    processes: list[subprocess.Popen] = []
    topics = (
        "/astra2_cam/color/image_raw",
        "/cam_eth/color/image_raw",
        "/cam_usb/color/image_raw",
    )
    try:
        for label, path in bag_paths.items():
            print(f"Starting {label} camera bag: {path}")
            command = ["ros2", "bag", "play", "--loop"]
            if path.is_file() and path.suffix.lower() == ".mcap":
                command.extend(["--storage", "mcap"])
            command.append(str(path))
            processes.append(subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            ))

        time.sleep(max(0.0, args.startup_wait))
        for topic in topics:
            result = subprocess.run(
                ["ros2", "topic", "info", topic],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            print(f"\nTopic check: {topic}")
            print(result.stdout.strip() or result.stderr.strip() or "No topic information returned.")

        print("\nStarting LiveKit streamer. Press Ctrl+C to stop the demo.")
        return subprocess.run(
            ["ros2", "run", "ros2_video_streamer", "streamer"],
            check=False,
        ).returncode
    except FileNotFoundError as exc:
        print(f"Required ROS 2 command not found: {exc}", file=sys.stderr)
        return 127
    except KeyboardInterrupt:
        return 130
    finally:
        stop_processes(processes)


if __name__ == "__main__":
    raise SystemExit(main())
