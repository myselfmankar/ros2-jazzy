import os
import subprocess
import sys
import signal
import re

def find_largest_recording_run():
    """Scans recordings folders to find the timestamp with the largest combined bag size."""
    astra_dir = "/home/eric/baggit_composition/baggit_astra/baggit_recordings_astra"
    if not os.path.exists(astra_dir):
        return None

    pattern = re.compile(r"recordings_(\d{8}_\d{6})")
    runs = []
    
    # List all recordings folders
    try:
        for entry in os.listdir(astra_dir):
            match = pattern.match(entry)
            if match:
                timestamp = match.group(1)
                # Verify matching triplets exist
                bag_front = f"/home/eric/baggit_composition/baggit_astra/baggit_recordings_astra/recordings_{timestamp}/front_cam/front_cam_0.mcap"
                bag_left = f"/home/eric/baggit_composition/baggit_gemini_eth/baggit_recordings_gemini_eth/recordings_{timestamp}/left_cam/left_cam_0.mcap"
                bag_right = f"/home/eric/baggit_composition/baggit_gemini_usb/baggit_recordings_gemini_usb/recordings_{timestamp}/right_cam/right_cam_0.mcap"
                
                if os.path.exists(bag_front) and os.path.exists(bag_left) and os.path.exists(bag_right):
                    # Sum file sizes
                    total_size = os.path.getsize(bag_front) + os.path.getsize(bag_left) + os.path.getsize(bag_right)
                    runs.append((total_size, timestamp))
    except Exception as e:
        print(f"Warning: directory scan failed: {e}")
        return None

    if not runs:
        return None
        
    # Sort by size descending
    runs.sort(reverse=True)
    return runs[0][1]

def main():
    print("=============================================")
    print("  Golain WebRTC Camera Streamer Demo Setup   ")
    print("=============================================")

    # Find the largest recording run as default
    print("\nScanning recordings for the largest run...")
    detected_timestamp = find_largest_recording_run()
    
    timestamp = detected_timestamp if detected_timestamp else "20260616_182225"
    
    print("\n---------------------------------------------")
    print(f"Automatically selected largest recording run: {timestamp}")

    # Resolve bag files
    bag_front = f"/home/eric/baggit_composition/baggit_astra/baggit_recordings_astra/recordings_{timestamp}/front_cam/front_cam_0.mcap"
    bag_left = f"/home/eric/baggit_composition/baggit_gemini_eth/baggit_recordings_gemini_eth/recordings_{timestamp}/left_cam/left_cam_0.mcap"
    bag_right = f"/home/eric/baggit_composition/baggit_gemini_usb/baggit_recordings_gemini_usb/recordings_{timestamp}/right_cam/right_cam_0.mcap"

    # Verify existences
    for label, path in [("Front", bag_front), ("Down Left", bag_left), ("Down Right", bag_right)]:
        if not os.path.exists(path):
            print(f"Error: {label} camera bag not found at {path}")
            sys.exit(1)
            
    print("All 3 camera bags verified successfully!")

    # 1. Play ROS2 bags in background
    print("\n1. Replaying ROS2 bags in background...")
    bag_proc = subprocess.Popen(
        ["ros2", "bag", "play", bag_front, bag_left, bag_right],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    # Cleanup callback to stop bag player on exit
    def cleanup(signum, frame):
        print("\nStopping background bag player...")
        bag_proc.terminate()
        try:
            bag_proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            bag_proc.kill()
        sys.exit(0)

    # Register exit signals
    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    # 2. Start WebRTC Streamer Node
    print("\n2. Sourcing workspace and starting WebRTC Streamer Node...")
    run_streamer_cmd = "source install/setup.bash && ros2 run ros2_video_streamer streamer"
    
    try:
        subprocess.run(run_streamer_cmd, shell=True, executable="/bin/bash")
    except KeyboardInterrupt:
        pass
    finally:
        cleanup(None, None)

if __name__ == "__main__":
    main()
