from setuptools import find_packages, setup

setup(
    name="instascope-scraper",
    version="0.1.0",
    packages=find_packages(),
    install_requires=["playwright>=1.49.0", "httpx>=0.28.0"],
)
