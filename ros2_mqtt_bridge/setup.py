from setuptools import find_packages, setup

package_name = "ros2_mqtt_bridge"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
    ],
    install_requires=["setuptools", "paho-mqtt==1.6.1"],
    zip_safe=True,
    maintainer="Vaishnav Mankar",
    maintainer_email="vaishnavmankar04@gmail.com",
    description="ROS 2 telemetry simulator and bidirectional MQTT bridge",
    license="Apache-2.0",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "mock_robot_sim = ros2_mqtt_bridge.mock_robot_sim:main",
            "mqtt_bridge_node = ros2_mqtt_bridge.mqtt_bridge_node:main",
        ],
    },
)
