#!/usr/bin/env bash
set -e
source /opt/ros/jazzy/setup.bash
source /ros2_ws/install/setup.bash
exec python3 /workspace/run_demo.py "$@"
