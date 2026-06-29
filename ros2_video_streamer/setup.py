from setuptools import find_packages, setup

package_name = 'ros2_video_streamer'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools', 'livekit'],
    zip_safe=True,
    maintainer='Golain Platform Team',
    maintainer_email='platform@golain.io',
    description='ROS2 node to capture camera topics and stream them to LiveKit over WebRTC',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'streamer = ros2_video_streamer.streamer_node:main'
        ],
    },
)
