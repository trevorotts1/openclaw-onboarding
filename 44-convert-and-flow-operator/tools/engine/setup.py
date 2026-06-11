from setuptools import setup, find_namespace_packages

setup(
    name="convert-and-flow-cli",
    version="1.0.0",
    description="Convert and Flow CLI — GoHighLevel operator for the BlackCEO fleet",
    author="BlackCEO",
    packages=find_namespace_packages(include=["cli_anything.*"]),
    package_data={
        "cli_anything.gohighlevel": ["skills/*.md"],
    },
    install_requires=[
        "click>=8.0.0",
        "prompt-toolkit>=3.0.0",
        "requests>=2.28.0",
        "rich>=13.0.0",
    ],
    entry_points={
        "console_scripts": [
            "convertandflow=cli_anything.gohighlevel.gohighlevel_cli:main",
            "caf=cli_anything.gohighlevel.gohighlevel_cli:main",
            "ghl=cli_anything.gohighlevel.gohighlevel_cli:main",
        ],
    },
    python_requires=">=3.10",
)
