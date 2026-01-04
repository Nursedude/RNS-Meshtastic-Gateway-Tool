#!/usr/bin/env python3
"""
Setup script for RNS-Meshtastic Gateway Tool.

MeshForge Integration - A comprehensive network operations suite
bridging Meshtastic and Reticulum (RNS) mesh networks.
"""

from pathlib import Path
from setuptools import setup, find_packages

# Read version from version.py
version_info = {}
exec(Path("version.py").read_text(), version_info)

# Read long description from README
readme_path = Path("README.md")
long_description = readme_path.read_text() if readme_path.exists() else ""

# Read requirements
requirements_path = Path("requirements.txt")
requirements = []
if requirements_path.exists():
    requirements = [
        line.strip()
        for line in requirements_path.read_text().split("\n")
        if line.strip() and not line.startswith("#")
    ]

setup(
    name="rns-meshtastic-gateway",
    version=version_info.get("get_version", lambda: "0.0.0")(),
    author="nursedude",
    author_email="admin@noc.local",
    description="RNS-Meshtastic Gateway Tool - MeshForge Integration",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/Nursedude/RNS-Meshtastic-Gateway-Tool",
    project_urls={
        "Bug Tracker": "https://github.com/Nursedude/RNS-Meshtastic-Gateway-Tool/issues",
        "Source Code": "https://github.com/Nursedude/RNS-Meshtastic-Gateway-Tool",
        "MeshForge": "https://github.com/Nursedude/meshforge",
    },
    packages=find_packages(),
    py_modules=["launcher", "version", "ai_methods", "git_manager"],
    python_requires=">=3.9",
    install_requires=requirements,
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-cov>=4.0.0",
            "black>=23.0.0",
            "mypy>=1.0.0",
        ],
        "web": [
            "flask>=2.3.0",
        ],
        "tui": [
            "textual>=0.45.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "rns-gateway=launcher:main",
            "meshforge-gateway=launcher:main",
        ],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Environment :: Console",
        "Intended Audience :: Developers",
        "Intended Audience :: System Administrators",
        "Intended Audience :: Telecommunications Industry",
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
        "Operating System :: POSIX :: Linux",
        "Operating System :: Microsoft :: Windows",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Communications",
        "Topic :: System :: Networking",
    ],
    keywords="meshtastic, reticulum, rns, lora, mesh, networking, gateway, bridge",
    license="GPL-3.0",
    include_package_data=True,
    zip_safe=False,
)
