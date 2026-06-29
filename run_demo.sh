#!/bin/bash

# Exit on error
set -e

echo "============================================="
echo "  Golain WebRTC Camera Streamer Demo Setup   "
echo "============================================="

# 1. Pull latest code changes
echo "1. Checking git updates..."
git pull origin main

# 2. Install pip dependencies for Python 3.10
echo "2. Installing required Python packages..."
pip3 install --upgrade pip
pip3 install livekit-api requests opencv-python --user

# 3. Build the ROS2 workspace
echo "3. Building the ros2_video_streamer package..."
# Check if colcon is available
if ! command -v colcon &> /dev/null; then
    echo "Error: colcon build tool not found. Make sure ROS2 environment is sourced."
    exit 1
fi
colcon build --packages-select ros2_video_streamer
source install/setup.bash

# 4. Prompt / Select recording timestamp
# Default to 20260616_182225
TIMESTAMP="20260616_182225"
echo "---------------------------------------------"
echo "Default recording run: $TIMESTAMP"
read -p "Press Enter to use default, or type another timestamp from mcap_loc.txt: " input_timestamp
if [ ! -z "$input_timestamp" ]; then
    TIMESTAMP=$input_timestamp
fi

# Define paths to MCAP files based on selected timestamp
BAG_FRONT="/home/eric/baggit_composition/baggit_astra/baggit_recordings_astra/recordings_${TIMESTAMP}/front_cam/front_cam_0.mcap"
BAG_DOWN_LEFT="/home/eric/baggit_composition/baggit_gemini_eth/baggit_recordings_gemini_eth/recordings_${TIMESTAMP}/left_cam/left_cam_0.mcap"
BAG_DOWN_RIGHT="/home/eric/baggit_composition/baggit_gemini_usb/baggit_recordings_gemini_usb/recordings_${TIMESTAMP}/right_cam/right_cam_0.mcap"

# Verify files exist
if [ ! -f "$BAG_FRONT" ]; then
    echo "Error: Front camera bag not found at $BAG_FRONT"
    exit 1
fi
if [ ! -f "$BAG_DOWN_LEFT" ]; then
    echo "Error: Down Left camera bag not found at $BAG_DOWN_LEFT"
    exit 1
fi
if [ ! -f "$BAG_DOWN_RIGHT" ]; then
    echo "Error: Down Right camera bag not found at $BAG_DOWN_RIGHT"
    exit 1
fi

echo "All 3 camera bags found successfully!"

# 5. Play bags in background
echo "4. Replaying ROS2 bags in background..."
ros2 bag play "$BAG_FRONT" "$BAG_DOWN_LEFT" "$BAG_DOWN_RIGHT" &
BAG_PID=$!

# Register exit handler to kill bag player when script exits
cleanup() {
    echo "Stopping bag player..."
    kill $BAG_PID || true
    exit
}
trap cleanup INT TERM EXIT

# 6. Start WebRTC Streamer Node
echo "5. Starting ros2_video_streamer node..."
echo "Connecting to local gateway to exchange token..."
ros2 run ros2_video_streamer streamer
