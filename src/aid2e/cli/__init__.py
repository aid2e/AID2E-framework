"""
AID2E CLI package.

Modular command-line interface with organized command categories:
- Config commands: describe, inspect, validate
- Workflow commands: optimize, run (future)
- Utility commands: list, version

The CLI can be imported in two ways for backward compatibility:
	from aid2e.cli.aid2e_cli import cli  # Legacy
	from aid2e.cli import cli             # Preferred
"""

from aid2e import __MAIN_VERSION__
from .aid2e_cli import cli

__version__ = __MAIN_VERSION__
__all__ = ["cli"]
