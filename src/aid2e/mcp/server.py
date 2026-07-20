"""FastMCP server entrypoint for AID2E.

The server binds three tool groups:
- shared tools for package and API discovery
- planner tools for architecture-aware decomposition
- coder tools for symbol-level implementation support
"""

from __future__ import annotations

from pathlib import Path
import re

import click

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as exc:  # pragma: no cover - exercised only when extra missing
    raise RuntimeError(
        "The AID2E MCP server requires the optional 'mcp' dependency. "
        "Install it with `python -m pip install -e \".[mcp]\"`."
    ) from exc

from .coder_tools import register_coder_tools
from .planner_tools import register_planner_tools
from .repository import RepositoryIndex
from .shared_tools import register_shared_tools


mcp = FastMCP(
    "aid2e",
    instructions=(
        "CRITICAL BEHAVIORAL RULE: You are an expert developer for the AID2E framework. "
        "Answer questions immediately using minimal scannable text. Do NOT create multi-turn plans "
        "unless the user explicitly starts their message with the word 'build'."
    ),
)


def _source_root() -> Path:
    """Resolve the repository root path from this module location.

    Returns:
        Source root path for semantic indexing.
    """
    return Path(__file__).resolve().parents[3]


def _workspace_root() -> Path:
    """Return the active user workspace."""
    return Path.cwd().resolve()


def workspace_path(path_input: str) -> Path:
    """
    Resolve a user-supplied path safely inside the active workspace.

    Accepts:
    - relative paths (preferred)
    - absolute POSIX paths
    - absolute Windows drive paths
    - WSL-like paths missing leading slash (mnt/c/...)
    """
    root = _workspace_root().resolve()
    raw = (path_input or "").strip().strip('"').strip("'").replace("\\", "/")

    if not raw:
        return root

    # Normalize common malformed absolute-like input from models.
    if raw.startswith("mnt/"):
        raw = "/" + raw

    # Treat drive paths as absolute-like for parsing logic.
    is_drive = re.match(r"^[A-Za-z]:/", raw) is not None

    if raw.startswith("/"):
        candidate = Path(raw).resolve()
    elif is_drive:
        candidate = Path(raw).resolve()
    else:
        candidate = (root / raw).resolve()

    # Enforce workspace boundary. Do not auto-rewrite out-of-root paths.
    try:
        candidate.relative_to(root)
    except ValueError:
        raise PermissionError(
            f"Access denied: {candidate} is outside workspace root {root}"
        )

    return candidate

@mcp.tool()
def debug_workspace():
    """Return the current workspace and source roots."""
    import os
    return {
        "CWD": os.getcwd(),
        "workspace": str(_workspace_root()),
        "source": str(_source_root()),
    }

def _register_tools() -> None:
    """Register all MCP tool groups against a shared repository index."""
    index = RepositoryIndex(root=_source_root())
    register_shared_tools(
        mcp,
        index,
        workspace_resolver=workspace_path,
        workspace_root_getter=_workspace_root,
    )
    register_planner_tools(mcp, index)
    register_coder_tools(mcp, index)


_register_tools()


@click.command()
@click.option("--sse", is_flag=True, help="Run over streamable HTTP instead of stdio.")
def mcp_command(sse: bool) -> None:
    """Run the AID2E MCP server.

    Args:
        sse: Use streamable HTTP when true. Use stdio when false.
    """
    transport = "sse" if sse else "stdio"
    mcp.run(transport=transport)


if __name__ == "__main__":
    mcp_command()
