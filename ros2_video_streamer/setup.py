from setuptools import find_packages, setup

package_name = "ros2_video_streamer"

setup(
    name=package_name,
    version="0.2.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="Vaishnav Mankar",
    maintainer_email="vaishnavmankar04@gmail.com",
    description="Optional ROS 2 camera topic to LiveKit WebRTC video streamer",
    license="Apache-2.0",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "streamer = ros2_video_streamer.streamer_node:main",
        ],
    },
)
