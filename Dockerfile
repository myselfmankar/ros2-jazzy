FROM ros:jazzy-ros-base

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    ROS_DOMAIN_ID=42 \
    ROS_LOCALHOST_ONLY=0

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-pip python3-colcon-common-extensions \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install --break-system-packages --no-cache-dir "paho-mqtt==1.6.1"

WORKDIR /ros2_ws/src
COPY ros2_mqtt_bridge/ /ros2_ws/src/ros2_mqtt_bridge/
WORKDIR /ros2_ws
RUN . /opt/ros/jazzy/setup.sh && colcon build --symlink-install

COPY docker/ros_entrypoint.sh /ros_entrypoint.sh
RUN chmod +x /ros_entrypoint.sh
ENTRYPOINT ["/ros_entrypoint.sh"]
CMD ["ros2", "run", "ros2_mqtt_bridge", "mqtt_bridge_node"]
