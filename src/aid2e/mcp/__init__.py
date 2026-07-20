"""AID2E MCP integration package.

This package contains a repository-aware Model Context Protocol (MCP) server
used by coding assistants. It provides planner and coder tool groups with
shared repository indexing primitives.
"""

from aid2e import __MAIN_VERSION__

from .repository import RepositoryIndex

__version__ = __MAIN_VERSION__

__all__ = ["RepositoryIndex", "__version__", "__MAIN_VERSION__"]
