from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="ssh-recorder",
    version="1.0.0",
    author="SSH Recorder Team",
    description="SSH session recording and playback tool",
    long_description=long_description,
    long_description_content_type="text/markdown",
    packages=find_packages(),
    python_requires=">=3.8",
    install_requires=[
        "paramiko>=3.0.0",
        "pyyaml>=6.0",
        "jinja2>=3.0",
        "blessed>=1.19",
    ],
    entry_points={
        "console_scripts": [
            "ssh-recorder=ssh_recorder.cli:main",
        ],
    },
)
