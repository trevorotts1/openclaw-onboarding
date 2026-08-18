from setuptools import setup, find_namespace_packages

setup(
    name="convert-and-flow-cli",
    version="1.0.0",
    description="Convert and Flow CLI — GoHighLevel operator for the BlackCEO fleet",
    author="BlackCEO",
    # "cli_anything.*" alone matches SUB-packages only — the top-level
    # cli_anything package itself never matches, so `import cli_anything`
    # failed even after a successful install. Both patterns are required.
    packages=find_namespace_packages(include=["cli_anything", "cli_anything.*"]),
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
    # The shipped venv is stock-macOS python3 (3.9.6) — `>=3.10` refused every
    # `pip install -e` on the fleet outright. Nothing in this package needs
    # 3.10+ (no match/case, no itertools.pairwise; type hints rely on
    # `from __future__ import annotations`, which is 3.9-safe). Verified live:
    # `pip install -e .` succeeds and `import cli_anything` works on 3.9.6.
    python_requires=">=3.9",
)
