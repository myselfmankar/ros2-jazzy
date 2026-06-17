from setuptools import find_packages, setup

package_name = 'ros2_mqtt_bridge'

setup(
    name=package_name,
    version='0.0.1',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Vaishnav',
    maintainer_email='vaishnav@golain.io',
    description='ROS2 to MQTT and SQLite bridge with simulated telemetry',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'mock_robot_sim = ros2_mqtt_bridge.mock_robot_sim:main',
            'mqtt_bridge_node = ros2_mqtt_bridge.mqtt_bridge_node:main',
        ],
    },
)
