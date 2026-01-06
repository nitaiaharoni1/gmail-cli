"""Setup script for Gmail CLI."""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="gmail-cli",
    version="1.0.6",
    author="Nitai Aharoni",
    description="Command-line interface for Gmail",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/nitaiaharoni/gmail-cli",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    python_requires=">=3.8",
    install_requires=[
        "google-api-python-client>=2.0.0",
        "google-auth-httplib2>=0.1.0",
        "google-auth-oauthlib>=0.5.0",
        "click>=8.0.0",
    ],
    entry_points={
        "console_scripts": [
            "gmail=gmail_cli.cli:cli",
        ],
    },
)

