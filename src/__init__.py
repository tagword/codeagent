# CodeAgent Package - Main entry point

from .cli_pkg import main as cli_main

__version__ = "1.0.0"
__description__ = "Autonomous task execution agent"

def run():
    """Run the CodeAgent CLI."""
    cli_main()
