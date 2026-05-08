"""
Setup script for CodeAgent.

Install with:
    pip install -e .           →  editable install (source .py, no compilation)
"""

from setuptools import setup, find_packages


# ── Actual setup call ──────────────────────────────────────────────────
setup(
    name="codeagent",
    version="1.0.0",
    description="LLM agent with Markdown config, tool loop, Web UI, sessions, memory, and webhooks",
    python_requires=">=3.9",
    packages=find_packages(where=".", include=["src*", "src.codeagent*"]),
    package_dir={"": "."},
    install_requires=[
        "requests>=2.28.0",
        "ddgs>=9.14.0",
    ],
    extras_require={
        "yaml": ["pyyaml>=6.0"],
        "dev": ["pytest>=7.0", "ruff>=0.4.0", "bandit>=1.7.0"],
        "lint": ["ruff>=0.4.0", "bandit>=1.7.0"],
        "server": [
            "uvicorn[standard]>=0.30.0",
            "starlette>=0.37.0",
            "apscheduler>=3.10.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "codeagent=src.cli_pkg:main",
            "codeagent-core=src.cli_pkg:main",
        ],
    },
)
