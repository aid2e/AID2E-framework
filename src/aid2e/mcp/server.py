"""FastMCP server entrypoint for AID2E.

The server binds three tool groups:
- shared tools for package/API discovery and full User Workspace file operations
- planner tools for Reference Source architecture, blueprints, and file reading
- coder tools for symbol-level contracts, source inspection, and reference grep

Tools are registered when the server starts, using one of two profiles:
`full` (default; complete User Workspace read/write suite for VS Code) or
`reference` (read-only Reference Source tools for Claude Code / Codex, which
edit files with their own tools).
"""

from __future__ import annotations

import os
from pathlib import Path
import re

import click

try:
    # MCP Python SDK v2.
    from mcp.server import MCPServer
except ImportError:
    try:
        # MCP Python SDK v1.
        from mcp.server.fastmcp import FastMCP as MCPServer
    except ImportError as exc:  # pragma: no cover - exercised only when extra missing
        raise RuntimeError(
            "The AID2E MCP server requires the MCP Python SDK. "
            "Install it with `python -m pip install -e \".[mcp]\"`."
        ) from exc

from .coder_tools import register_coder_tools
from .planner_tools import register_planner_tools
from .repository import RepositoryIndex
from .shared_tools import in_reference_source, register_shared_tools, source_writes_allowed


TOOL_PROFILES = ("full", "reference")

_FULL_INSTRUCTIONS = (
    "AID2E (AI-assisted Detector Design for EIC) MCP server: detector design optimization for the EIC. "
    "Read-only Source Reference tools (read_framework_file, read_example_file, "
    "get_subsystem_blueprints, get_class_contracts, get_symbol_source, "
    "search_repository, grep_framework_source) verify AID2E classes, contracts, "
    "registries, and examples before you propose or write code; the AID2E source "
    "cannot be modified. Workspace tools (*_in_workspace, validate_workspace_file) "
    "read and write the user's project. run_workspace_tests runs pytest in the user's "
    "project: after writing code, write a small pytest test for it, run it, and fix "
    "failures before reporting done. Files and functions the user names are in "
    "the workspace: read them directly with read_file_in_workspace. Use "
    "debug_workspace only if a workspace path fails or the root is unknown. "
    "If asked to modify AID2E itself, say the AID2E source is read-only and offer to "
    "implement the change in the user's project instead (for example a subclass or a new module). "
    "Pass the file as `path`; pass `overwrite` as a separate Boolean argument."
)

# Sent only with the `reference` profile (hosted agents such as Claude Code and Codex).
_REFERENCE_INSTRUCTIONS = (
    "AID2E (AI-assisted Detector Design for EIC) MCP server, reference profile. "
    "These tools expose the installed AID2E package and its examples: the read-only "
    "Reference Source. Edit the user's project with your own file tools. Rules: "
    "(1) Verify before use: confirm every AID2E class, function, registry, config key, "
    "and path with get_subsystem_blueprints, get_class_contracts, get_symbol_source, "
    "search_repository, grep_framework_source, read_framework_file, or read_example_file "
    "before relying on it. Never invent names; if evidence cannot be found, say what is "
    "missing. (2) Never modify the Reference Source; if asked to, offer to implement the change in the "
    "user's project instead. Read AID2E through these tools "
    "rather than site-packages. (3) Extend, don't fork: import existing AID2E classes and "
    "mirror the Reference architecture (layout, naming, registration, config style) inside "
    "the user's project. (4) Validate: run validate_workspace_file on new .py files and AID2E "
    "configs (.yml/.yaml/.json/.config/.params), and finish with an example config or script "
    "adapted from the closest Reference example."
)

mcp = MCPServer("aid2e", instructions=_FULL_INSTRUCTIONS)

_ACTIVE_WORKSPACE_ROOT: Path | None = None


def _source_root() -> Path:
    """Resolve the repository or installed package root from this module location.

    Works in both an editable git checkout (`<repo>/src/aid2e/mcp/server.py`)
    and an installed wheel (`.../site-packages/aid2e/mcp/server.py`).
    """
    pkg_dir = Path(__file__).resolve().parent.parent
    if (
        len(pkg_dir.parents) >= 2
        and pkg_dir.parent.name == "src"
        and (pkg_dir.parents[1] / "src" / "aid2e").is_dir()
    ):
        return pkg_dir.parents[1]
    return pkg_dir


def _workspace_root() -> Path:
    """Return the explicitly selected user workspace root."""
    global _ACTIVE_WORKSPACE_ROOT
    if _ACTIVE_WORKSPACE_ROOT is not None:
        return _ACTIVE_WORKSPACE_ROOT
    env_ws = os.environ.get("AID2E_WORKSPACE")
    if env_ws:
        candidate = Path(env_ws).expanduser().resolve()
        if candidate.exists() and candidate.is_dir():
            return candidate
        raise ValueError(f"AID2E_WORKSPACE is not an existing directory: {candidate}")
    raise ValueError(
        "User Workspace is not set. Launch with --workspace PATH, set "
        "AID2E_WORKSPACE, or call set_workspace_root with a path supplied by the user."
    )


def set_active_workspace_root(path_str: str) -> Path:
    """Update the active workspace root directory for the current MCP session."""
    global _ACTIVE_WORKSPACE_ROOT
    cleaned = (path_str or "").strip().strip('"').strip("'")
    if not cleaned:
        raise ValueError("Workspace path cannot be empty.")
    selected = Path(cleaned).expanduser()
    if not selected.is_absolute():
        raise ValueError("Workspace path must be absolute; do not rely on the MCP launch directory.")
    target = selected.resolve()
    if not target.exists():
        raise FileNotFoundError(f"Directory does not exist: {target.as_posix()}")
    if not target.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {target.as_posix()}")
    if not source_writes_allowed() and in_reference_source(target, _INDEX):
        raise PermissionError(
            f"{target.as_posix()} is inside the read-only AID2E Reference Source; "
            "choose the user's own project directory as the workspace."
        )
    _ACTIVE_WORKSPACE_ROOT = target
    return target


def workspace_path(path_input: str) -> Path:
    """Resolve a user-supplied path safely inside the active workspace.

    Accepts:
    - workspace-relative paths (preferred)
    - `<workspace>/...` placeholder prefixes emitted by models
    - absolute POSIX paths inside the workspace
    - absolute Windows drive paths / WSL paths (`mnt/c/...`)
    """
    root = _workspace_root().resolve()
    raw = (path_input or "").strip().strip('"').strip("'").replace("\\", "/")

    if not raw or raw in {".", "./"}:
        return root

    # Strip literal `<workspace>/` or `${workspaceFolder}/` placeholders if emitted
    for prefix in ("<workspace>/", "${workspaceFolder}/", "$WORKSPACE/"):
        if raw.startswith(prefix):
            raw = raw[len(prefix) :]

    # Normalize common malformed WSL input from models.
    if raw.startswith("mnt/"):
        raw = "/" + raw

    is_drive = re.match(r"^[A-Za-z]:/", raw) is not None

    if raw.startswith("/"):
        candidate = Path(raw).resolve()
        # If the model passed `/subdir/file.py` intending a workspace-relative path,
        # fall back to resolving relative to `root` when `/subdir/file.py` is not under `root`.
        try:
            candidate.relative_to(root)
        except ValueError:
            rel_candidate = (root / raw.lstrip("/")).resolve()
            try:
                rel_candidate.relative_to(root)
                # Only auto-resolve leading-slash paths when they don't point to another real root dir like /sciclone or /home
                top_seg = raw.lstrip("/").split("/", 1)[0]
                if not Path("/" + top_seg).exists():
                    candidate = rel_candidate
            except ValueError:
                pass
    elif is_drive:
        candidate = Path(raw).resolve()
    else:
        candidate = (root / raw).resolve()

    # Enforce workspace boundary. Do not allow writing outside the active workspace.
    try:
        candidate.relative_to(root)
    except ValueError:
        raise PermissionError(
            f"Access denied: {candidate} is outside workspace root {root}. "
            f"Use a path relative to {root} (or call set_workspace_root if working in a different project directory)."
        )

    return candidate


_INDEX = RepositoryIndex(root=_source_root())


def debug_workspace() -> dict[str, str]:
    """Return workspace status, CWD, and AID2E reference source root."""
    try:
        workspace = str(_workspace_root())
    except ValueError as exc:
        workspace = f"UNSET: {exc}"
    return {
        "CWD": os.getcwd(),
        "workspace": workspace,
        "source": str(_INDEX.package_root),
        "examples": str(_INDEX.package_examples),
    }


def set_workspace_root(path: str) -> str:
    """Set the active User Workspace root directory for all workspace read/write tools.

    Call this only with a project directory explicitly supplied by the user.

    Args:
        path: Absolute path to the user's target project directory.

    Returns:
        Confirmation message with the updated workspace root path.
    """
    try:
        updated = set_active_workspace_root(path)
        return f"active workspace set to: {updated.as_posix()}"
    except Exception as exc:
        return f"error setting workspace root: {exc}"


_REGISTERED_PROFILE: str | None = None


def _strip_titles(schema):
    """Recursively drop pydantic's auto-generated `title` keys from a JSON schema."""
    if isinstance(schema, dict):
        return {k: _strip_titles(v) for k, v in schema.items() if k != "title"}
    if isinstance(schema, list):
        return [_strip_titles(v) for v in schema]
    return schema


def _compact_tool_schemas() -> None:
    """Remove `title` noise from every registered tool's parameter schema.

    Titles repeat the parameter names and cost tokens on every request, which
    matters most for small local models.
    """
    tools = getattr(getattr(mcp, "_tool_manager", None), "_tools", {})
    for tool in tools.values():
        if isinstance(getattr(tool, "parameters", None), dict):
            tool.parameters = _strip_titles(tool.parameters)


def _set_server_instructions(text: str) -> None:
    """Update the instructions advertised to clients during initialization."""
    # SDK v2 keeps them on `_lowlevel_server`, v1 on `_mcp_server`.
    for attr in ("_lowlevel_server", "_mcp_server"):
        server = getattr(mcp, attr, None)
        if server is not None and hasattr(server, "instructions"):
            server.instructions = text


def register_tools(profile: str = "full") -> None:
    """Register MCP tool groups against the shared repository index.

    Args:
        profile: 'full' registers the complete Reference Source and User
            Workspace read/write suite (for clients without native file tools,
            such as VS Code with built-in tools disabled). 'reference' registers
            only the read-only Reference Source tools plus `debug_workspace` and
            `validate_workspace_file`, for clients like Claude Code and Codex
            that edit files with their own tools.
    """
    global _REGISTERED_PROFILE
    if profile not in TOOL_PROFILES:
        raise ValueError(f"Unknown tool profile {profile!r}; choose from {', '.join(TOOL_PROFILES)}.")
    if _REGISTERED_PROFILE is not None:
        if _REGISTERED_PROFILE != profile:
            raise RuntimeError(
                f"MCP tools already registered with profile {_REGISTERED_PROFILE!r}; cannot switch to {profile!r}."
            )
        return

    mcp.tool(
        description="User project: show the active User Workspace root and the read-only AID2E source paths. "
        "Use only if a workspace path fails or the root is unknown."
    )(debug_workspace)
    if profile == "full":
        mcp.tool(
            description="User project: set the User Workspace root. Only use an absolute project path the user supplied."
        )(set_workspace_root)
    register_shared_tools(
        mcp,
        _INDEX,
        workspace_resolver=workspace_path,
        workspace_root_getter=_workspace_root,
        workspace_tools="all" if profile == "full" else "validate",
    )
    register_planner_tools(mcp, _INDEX)
    register_coder_tools(mcp, _INDEX)
    _compact_tool_schemas()
    _set_server_instructions(_FULL_INSTRUCTIONS if profile == "full" else _REFERENCE_INSTRUCTIONS)
    _REGISTERED_PROFILE = profile


@click.command()
@click.option("--sse", is_flag=True, help="Run over streamable HTTP instead of stdio.")
@click.option(
    "--workspace",
    default=None,
    help="Set the initial User Workspace directory (or use AID2E_WORKSPACE; no CWD fallback).",
)
@click.option(
    "--tools",
    "tools",
    type=click.Choice(TOOL_PROFILES),
    default="full",
    show_default=True,
    help="Tool profile: 'full' (workspace read/write suite) or 'reference' (read-only Reference Source tools).",
)
def mcp_command(sse: bool, workspace: str | None = None, tools: str = "full") -> None:
    """Run the AID2E MCP server.

    Args:
        sse: Use streamable HTTP when true. Use stdio when false.
        workspace: Optional initial workspace directory path.
        tools: Tool profile to expose ('full' or 'reference').
    """
    if workspace:
        set_active_workspace_root(workspace)
    register_tools(tools)
    transport = "sse" if sse else "stdio"
    mcp.run(transport=transport)


if __name__ == "__main__":
    mcp_command()
