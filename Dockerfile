FROM ros:jazzy-ros-base

# Install dependencies
RUN apt-get update && apt-get install -y \
    python3-pip \
    python3-colcon-common-extensions \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# Install paho-mqtt
RUN pip3 install --break-system-packages paho-mqtt

# Create workspace directory structure
WORKDIR /ros2_ws/src

# Copy package source
COPY ros2_mqtt_bridge/ /ros2_ws/src/ros2_mqtt_bridge/

# Copy database initialization helper
COPY db_init.py /ros2_ws/db_init.py

# Build workspace
WORKDIR /ros2_ws
RUN . /opt/ros/jazzy/setup.sh && colcon build

# Add workspace sourcing to bashrc
RUN echo "source /opt/ros/jazzy/setup.bash" >> ~/.bashrc
RUN echo "source /ros2_ws/install/setup.bash" >> ~/.bashrc

# Set up volume mount for DB storage
VOLUME ["/data"]

# Entrypoint script
COPY <<EOF /entrypoint.sh
#!/bin/bash
set -e
source /opt/ros/jazzy/setup.bash
source /ros2_ws/install/setup.bash

# Initialize SQLite database schema
python3 /ros2_ws/db_init.py /data/local_robot.db

exec "\$@"
EOF

RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["ros2", "run", "ros2_mqtt_bridge", "mqtt_bridge_node"]
