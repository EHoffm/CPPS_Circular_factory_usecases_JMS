#!/usr/bin/env python3
"""
Legacy setup.py for backward compatibility with older tools.
This file dynamically reads from pyproject.toml for configuration.
"""

import os
from setuptools import setup, find_packages


# Read the long description from README
def read_readme():
    """Read README.md for the long description."""
    with open("README.md", "r", encoding="utf-8") as f:
        return f.read()


# Basic package information
setup(
    name="jms-usecase-2",
    version="0.1.0",
    author="Your Name",
    author_email="your.email@example.com",
    description="FlexConveyor System with GraphDB integration and Streamlit interface",
    long_description=read_readme(),
    long_description_content_type="text/markdown",
    url="https://gitlab.kit.edu/kit/ifl/forschung/sfb1574/inf/jms_usecase_2",
    project_urls={
        "Bug Tracker": "https://gitlab.kit.edu/kit/ifl/forschung/sfb1574/inf/jms_usecase_2/-/issues",
        "Repository": "https://gitlab.kit.edu/kit/ifl/forschung/sfb1574/inf/jms_usecase_2",
    },
    packages=find_packages(),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Scientific/Engineering",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
    python_requires=">=3.9",
    install_requires=[
        "graph-db-interface",
        "streamlit>=1.28.0",
        "matplotlib>=3.7.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.4.0",
            "pytest-cov>=4.1.0",
            "black>=23.7.0",
            "flake8>=6.0.0",
            "mypy>=1.5.0",
            "pre-commit>=3.3.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "flexconveyor-interface=jms_usecase_2.src.streamlit_interface:main",
        ],
    },
    include_package_data=True,
    zip_safe=False,
    keywords=["flexconveyor", "graphdb", "streamlit", "automation", "logistics"],
)
