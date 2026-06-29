import os
import subprocess
import sys
import time
import signal
import shutil

def run_cmd(args, shell=False, check=True):
    try:
        res = subprocess.run(args, shell=shell, check=check, text=True, capture_output=True)
        return res.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"Error executing command: {' '.join(args) if isinstance(args, list) else args}")
        print(f"Stderr: {e.stderr}")
        if check:
            sys.exit(1)
        return ""

def main():
    print("=============================================")
    print("  Golain WebRTC Camera Streamer Demo Setup   ")
    print("=============================================")

    # 1. Pull latest code
    print("\n1. Pulling git updates...")
    run_cmd(["git", "pull", "origin", "main"])

    # 2. Install Pip dependencies
    print("\n2. Installing required Python packages...")
    pip_cmd = [sys.executable, "-m", "pip", "install", "--upgrade", "pip"]
    run_cmd(pip_cmd)
    
    install_cmd = [sys.executable, "-m", "pip", "install", "livekit-api", "requests", "opencv-python", "--user"]
    run_cmd(install_cmd)

    # 3. Check for colcon and build package
    print("\n3. Building the ros2_video_streamer package...")
    if not shutil.which("colcon"):
        print("Error: 'colcon' build tool not found. Make sure ROS2 environment is sourced.")
        sys.exit(1)
        
    run_cmd(["colcon", "build", "--packages-select", "ros2_video_streamer"])

    # 4. Prompt for recording timestamp
    timestamp = "20260616_182225"
    print("\n---------------------------------------------")
    print(f"Default recording run: {timestamp}")
    user_input = input("Press Enter to use default, or type another timestamp from mcap_loc.txt: ").strip()
    if user_input:
        timestamp = user_input

    # 5. Resolve bag files
    bag_front = f"/home/eric/baggit_composition/baggit_astra/baggit_recordings_astra/recordings_{timestamp}/front_cam/front_cam_0.mcap"
    bag_left = f"/home/eric/baggit_composition/baggit_gemini_eth/baggit_recordings_gemini_eth/recordings_{timestamp}/left_cam/left_cam_0.mcap"
    bag_right = f"/home/eric/baggit_composition/baggit_gemini_usb/baggit_recordings_gemini_usb/recordings_{timestamp}/right_cam/right_cam_0.mcap"

    # Verify existences
    for label, path in [("Front", bag_front), ("Down Left", bag_left), ("Down Right", bag_right)]:
        if not os.path.exists(path):
            print(f"Error: {label} camera bag not found at {path}")
            sys.exit(1)
            
    print("All 3 camera bags found successfully!")

    # 6. Play ROS2 bags in background
    print("\n4. Replaying ROS2 bags in background...")
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

    # 7. Start WebRTC Streamer Node
    print("\n5. Sourcing workspace and starting WebRTC Streamer Node...")
    # Sourcing + running in single bash call so ROS2 recognizes the built package
    run_streamer_cmd = "source install/setup.bash && ros2 run ros2_video_streamer streamer"
    
    try:
        subprocess.run(run_streamer_cmd, shell=True, executable="/bin/bash")
    except KeyboardInterrupt:
        pass
    finally:
        cleanup(None, None)

if __name__ == "__main__":
    main()
