"""Read-only Source Reference tools: subsystem blueprints, file listing, and file reading.

These tools expose the installed AID2E package and its `examples/` tree (the
Reference Source). None of them can modify files.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from .repository import RepositoryIndex, _SKIP_DIRS

_REFERENCE_CHUNK_LINES = 80
_REFERENCE_CHUNK_CHARS = 12000


def _format_reference_chunk(content: str, display: str, start_line: int, end_line: int, max_chars: int = _REFERENCE_CHUNK_CHARS) -> str:
    """Return one bounded, line-numbered reference chunk with an explicit continuation."""
    lines = content.splitlines()
    total = len(lines)
    if not total:
        return f"# {display} (empty file)"

    start = max(1, start_line or 1)
    if start > total:
        return f"# {display} ({total} lines total)\n\nLine {start} is past end of file; no more content."

    limit = min(_REFERENCE_CHUNK_CHARS, max_chars) if max_chars > 0 else _REFERENCE_CHUNK_CHARS
    limit = max(200, limit)
    stop = min(total, start + _REFERENCE_CHUNK_LINES - 1)
    if end_line > 0:
        stop = min(stop, max(start, end_line))

    rendered_lines = []
    used = 0
    for line_number in range(start, stop + 1):
        numbered = f"{line_number}: {lines[line_number - 1]}"
        available = limit - used - (1 if rendered_lines else 0)
        if len(numbered) > available:
            if rendered_lines:
                break
            numbered = numbered[: max(0, available - len(" [line clipped]"))] + " [line clipped]"
        rendered_lines.append(numbered)
        used += len(numbered) + (1 if len(rendered_lines) > 1 else 0)
        if numbered.endswith(" [line clipped]"):
            break

    actual_end = start + len(rendered_lines) - 1
    continuation = f"\n\nNext chunk: start_line={actual_end + 1}" if actual_end < total else "\n\nEnd of file."
    return f"# {display} (lines {start}-{actual_end} of {total})\n\n" + "\n".join(rendered_lines) + continuation


def register_planner_tools(mcp, index: RepositoryIndex) -> None:
    """Register planner MCP tools for Reference Source exploration.

    Args:
        mcp: FastMCP server instance.
        index: Repository semantic index.
    """

    @mcp.tool(
        description="AID2E source: blueprint of an AID2E subsystem (base class, implementations, registries, example configs). "
        "Empty subsystem lists them."
    )
    def get_subsystem_blueprints(
        subsystem: Annotated[str, Field(description="e.g. 'schedulers', 'optimizers', 'workflows', 'configurations'.")] = "",
        reference_engine: Annotated[str, Field(description="Optional implementation to focus on, e.g. 'Slurm', 'ax'.")] = "",
    ) -> str:
        """Get abstract base, implementation folders, registries, and example configs for a subsystem.

        Args:
            subsystem: Component family such as 'schedulers', 'optimizers', 'workflows',
                'configurations', 'epic_utils', 'cli', or '' to list all available subsystems.
            reference_engine: Optional implementation preference (e.g., 'Slurm', 'JobLib', 'ax', 'pymoo').

        Returns:
            Structured blueprint text for planning new implementations.
        """
        subsystems = index.discover_subsystems()
        if not subsystem or not subsystem.strip():
            available = ", ".join(sorted(k for k in subsystems if "/" not in k and "." not in k))
            return f"Available AID2E subsystems: {available}"

        blueprint = index.build_component_blueprint(subsystem, reference_engine)
        if not blueprint.directory.exists():
            available = ", ".join(sorted(k for k in subsystems if "/" not in k and "." not in k))
            return (
                f"Subsystem '{subsystem}' not found. "
                f"Available subsystems: {available}"
            )

        lines = [f"# {subsystem.title()} Blueprint", ""]
        lines.append(f"- Directory: `{index.display_path(blueprint.directory)}`")
        lines.append(f"- Abstract base: `{blueprint.abstract_base or 'not found'}`")

        if blueprint.implementations:
            lines.append("- Implementations:")
            for impl in blueprint.implementations:
                lines.append(f"  - `{impl}`")

        if blueprint.registration_files:
            lines.append("- Registration & configuration schema files:")
            for path in blueprint.registration_files[:15]:
                lines.append(f"  - `{path}`")

        if blueprint.configuration_files:
            lines.append("- Related example & config files:")
            for path in blueprint.configuration_files[:15]:
                lines.append(f"  - `{path}`")

        lines.append("")
        lines.append("Planner instructions:")
        lines.append("1. Read abstract base contracts and registry files first.")
        lines.append("2. Compare one production implementation end-to-end.")
        lines.append("3. Produce a verified file-by-file implementation plan before coding.")
        return "\n".join(lines)

    @mcp.tool(description="AID2E source: read an AID2E source file. Returns at most 80 numbered lines per call; continue with start_line.")
    def read_framework_file(
        path: Annotated[str, Field(description="Path relative to the aid2e package, e.g. 'schedulers/base.py'.")],
        start_line: Annotated[int, Field(description="First line, 1-indexed.")] = 1,
        end_line: Annotated[int, Field(description="Last line; 0 = one 80-line chunk.")] = 0,
    ) -> str:
        """Read a file from the AID2E Reference Source with 1-indexed line numbers.

        Args:
            path: File path relative to `src/aid2e/` or the repository root.
            start_line: 1-indexed first line to read.
            end_line: 1-indexed last line requested (0 means one default chunk).

        Returns:
            Numbered file content (at most 80 lines / 12000 characters) or an error message.
        """
        raw = path
        if not raw or not raw.strip():
            return "Missing `path` argument: pass the file as `path`, e.g. 'schedulers/base.py'."

        target = index.resolve_reference_file(raw)
        if target is None or not target.exists() or not target.is_file():
            return f"Not found in AID2E reference source: {raw}"

        content = target.read_text(encoding="utf-8", errors="replace")
        display = index.display_path(target)
        return _format_reference_chunk(content, display, start_line, end_line)

    @mcp.tool(description="AID2E source: read an AID2E example script or config. Returns at most 80 numbered lines per call; continue with start_line.")
    def read_example_file(
        path: Annotated[str, Field(description="Path relative to examples/, e.g. 'dtlz2/dtlz2_evaluator.py'.")],
        start_line: Annotated[int, Field(description="First line, 1-indexed.")] = 1,
        end_line: Annotated[int, Field(description="Last line; 0 = one 80-line chunk.")] = 0,
    ) -> str:
        """Read a file from the AID2E `examples/` tree with 1-indexed line numbers.

        Args:
            path: File path relative to `examples/`.
            start_line: 1-indexed first line to read.
            end_line: 1-indexed last line requested (0 means one default chunk).

        Returns:
            Numbered file content (at most 80 lines / 12000 characters) or an error message.
        """
        raw = path
        if not raw or not raw.strip():
            return "Missing `path` argument: pass the file as `path`, e.g. 'dtlz2/dtlz2_evaluator.py'."

        cleaned = raw.strip().strip('"').strip("'").replace("\\", "/")
        if cleaned.startswith("examples/"):
            cleaned = cleaned[len("examples/") :]

        root = index.package_examples.resolve()
        candidate = (root / cleaned).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            return f"Access denied: {candidate.as_posix()} is outside {root.as_posix()}"

        if not candidate.exists() or not candidate.is_file():
            # Fall back to general reference resolver in case a framework path was passed
            alt = index.resolve_reference_file(raw)
            if alt is not None and alt.is_file():
                candidate = alt
            else:
                return f"Not found in examples: {raw}"

        content = candidate.read_text(encoding="utf-8", errors="replace")
        display = index.display_path(candidate)
        return _format_reference_chunk(content, display, start_line, end_line)

    @mcp.tool(description="AID2E source: list AID2E source files in a subsystem ('' or 'all' = whole package).")
    def list_files_in_framework_subdirectory(
        subsystem: Annotated[str, Field(description="e.g. 'schedulers', 'optimizers', 'configurations'.")] = "",
        pattern: Annotated[str, Field(description="Glob filter, e.g. '*.py'.")] = "*",
    ) -> str:
        """List files in an AID2E subsystem directory (or the entire `aid2e` package when `subsystem` is empty or `'all'`).

        Args:
            subsystem: Subsystem name (e.g., 'schedulers', 'optimizers', 'utilities',
                'configurations', 'workflows', 'epic_utils', 'cli', or 'all').
            pattern: Glob pattern to filter files (default '*').

        Returns:
            Markdown list of files in the subsystem.
        """
        target_dir = index.resolve_subsystem_path(subsystem)
        if target_dir is None or not target_dir.exists():
            subsystems = index.discover_subsystems()
            available = ", ".join(sorted(k for k in subsystems if "/" not in k and "." not in k))
            return (
                f"Subsystem '{subsystem}' not found. "
                f"Available subsystems: {available}"
            )

        files = [
            f
            for f in sorted(target_dir.rglob(pattern))
            if f.is_file() and not any(part.startswith(".") or part in _SKIP_DIRS for part in f.parts)
        ]
        if not files:
            return f"No files found in '{subsystem or 'aid2e'}' matching pattern '{pattern}'."

        lines = [f"# Files in '{subsystem or 'aid2e'}' matching '{pattern}'", ""]
        for file in files:
            lines.append(f"- `{index.display_path(file)}`")
        return "\n".join(lines)

    @mcp.tool(description="AID2E source: list AID2E example files (scripts, YAML configs, .params).")
    def list_example_directory_files(
        pattern: Annotated[str, Field(description="Glob filter, e.g. '*.yml'.")] = "*",
    ) -> str:
        """List files in the AID2E `examples/` directory tree.

        Args:
            pattern: Glob pattern to filter files (default '*').

        Returns:
            Markdown list of example files.
        """
        root = index.package_examples
        if not root.exists():
            return "Examples directory not found."

        files = [
            f
            for f in sorted(root.rglob(pattern))
            if f.is_file() and not any(part.startswith(".") or part in _SKIP_DIRS for part in f.parts)
        ]
        if not files:
            return f"No files found in example source tree matching pattern '{pattern}'."

        lines = [f"# Example files matching '{pattern}'", ""]
        for file in files:
            rel_path = file.relative_to(root).as_posix()
            lines.append(f"- `{rel_path}`")
        return "\n".join(lines)
