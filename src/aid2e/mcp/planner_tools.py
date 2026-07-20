"""Planner-oriented MCP tools.

These tools expose high-level architecture context intended for planning
models before code generation begins.
"""

from __future__ import annotations
from pathlib import Path
from .repository import RepositoryIndex


def register_planner_tools(mcp, index: RepositoryIndex) -> None:
    """Register planner-only MCP tools.

    Args:
        mcp: FastMCP server instance.
        index: Repository semantic index.
    """

    @mcp.tool()
    def get_subsystem_blueprints(subsystem: str, reference_engine: str = "") -> str:
        """Get abstract base and implementation blueprint context in one call.

        Args:
            subsystem: Component family such as schedulers or optimizers.
            reference_engine: Optional implementation preference.

        Returns:
            Structured blueprint text for planning new implementations.
        """
        blueprint = index.build_component_blueprint(subsystem, reference_engine)
        if not blueprint.directory.exists():
            return (
                f"Error: Subsystem '{subsystem}' directory not found at "
                f"{blueprint.directory}"
            )

        lines = [f"# {subsystem.title()} Blueprint", ""]
        lines.append(f"- Directory: `{blueprint.directory}`")
        lines.append(f"- Abstract base: `{blueprint.abstract_base or 'not found'}`")

        if blueprint.implementations:
            lines.append("- Implementations:")
            for impl in blueprint.implementations:
                lines.append(f"  - `{impl}`")

        if blueprint.registration_files:
            lines.append("- Registration files:")
            for path in blueprint.registration_files[:10]:
                lines.append(f"  - `{path}`")

        if blueprint.configuration_files:
            lines.append("- Related configs:")
            for path in blueprint.configuration_files[:10]:
                lines.append(f"  - `{path}`")

        lines.append("")
        lines.append("Planner instructions:")
        lines.append("1. Read abstract base contracts first.")
        lines.append("2. Compare one production implementation end-to-end.")
        lines.append("3. Produce file-by-file implementation plan before coding.")
        return "\n".join(lines)

    @mcp.tool()
    def plan_symbol_search(query: str, limit: int = 20) -> str:
        """Search semantic symbols to seed implementation planning.

        Args:
            query: Free-text architecture question or symbol hint.
            limit: Maximum number of matches to return.

        Returns:
            Ranked list of candidate modules and symbols.
        """
        results = index.search(query=query, limit=limit)
        if not results:
            return f"No semantic matches found for '{query}'."

        lines = [f"# Planning matches for '{query}'", ""]
        for item in results:
            lines.append(
                f"- [{item.kind}] `{item.symbol}` (score={item.score:.2f}) - {item.summary}"
            )
        return "\n".join(lines)

    @mcp.tool()
    def read_framework_file(
        path_input: str | None = None,
        path: str | None = None,
        file_path: str | None = None,
        relative_path: str | None = None,
        max_chars: int = 50000,
    ) -> str:
        """Read a source file from the AID2E reference source tree.

        Args:
            path_input: Primary path input.
            path: Generic path alias.
            file_path: File-path alias.
            relative_path: Relative path alias.
            max_chars: Maximum number of characters returned.

        Returns:
            File content or an error message.
        """
        raw = path_input or path or file_path or relative_path
        if raw is None or not raw.strip():
            return (
                "Missing path argument. Provide one of: "
                "path_input, path, file_path, relative_path."
            )

        root = (index.root / "src" / "aid2e").resolve()
        cleaned = raw.strip().strip('"').strip("'").replace("\\", "/")

        # Keep planner reads anchored to reference source package.
        if cleaned.startswith("src/aid2e/"):
            cleaned = cleaned[len("src/aid2e/"):]
        elif cleaned.startswith("aid2e/"):
            cleaned = cleaned[len("aid2e/"):]

        incoming = Path(cleaned)
        if incoming.is_absolute():
            target = incoming.resolve()
        else:
            target = (root / incoming).resolve()

        try:
            target.relative_to(root)
        except ValueError:
            return f"Access denied: {target.as_posix()} is outside {root.as_posix()}"

        if not target.exists() or not target.is_file():
            return f"Not found: {target.as_posix()}"

        content = target.read_text(encoding="utf-8", errors="replace")
        if max_chars > 0 and len(content) > max_chars:
            content = content[:max_chars]
            return (
                f"# {target.as_posix()}\n"
                f"(truncated to {max_chars} chars)\n\n{content}"
            )

        return f"# {target.as_posix()}\n\n{content}"

    @mcp.tool()
    def read_example_file(
        path_input: str | None = None,
        path: str | None = None,
        file_path: str | None = None,
        relative_path: str | None = None,
        max_chars: int = 50000,
    ) -> str:
        """Read a source file from the AID2E example source tree.

        Args:
            path_input: Primary path input.
            path: Generic path alias.
            file_path: File-path alias.
            relative_path: Relative path alias.
            max_chars: Maximum number of characters returned.

        Returns:
            File content or an error message.
        """
        raw = path_input or path or file_path or relative_path
        if raw is None or not raw.strip():
            return (
                "Missing path argument. Provide one of: "
                "path_input, path, file_path, relative_path."
            )

        root = (index.package_examples).resolve()
        cleaned = raw.strip().strip('"').strip("'").replace("\\", "/")

        incoming = Path(cleaned)
        if incoming.is_absolute():
            target = incoming.resolve()
        else:
            target = (root / incoming).resolve()

        try:
            target.relative_to(root)
        except ValueError:
            return f"Access denied: {target.as_posix()} is outside {root.as_posix()}"

        if not target.exists() or not target.is_file():
            return f"Not found: {target.as_posix()}"

        content = target.read_text(encoding="utf-8", errors="replace")
        if max_chars > 0 and len(content) > max_chars:
            content = content[:max_chars]
            return (
                f"# {target.as_posix()}\n"
                f"(truncated to {max_chars} chars)\n\n{content}"
            )

        return f"# {target.as_posix()}\n\n{content}"

    @mcp.tool()
    def list_files_in_framework_subdirectory(subsystem: str, pattern: str = "*") -> str:
        """List files in a subsystem directory.

        Args:
            subsystem: Component family such as schedulers or optimizers.
            pattern: Glob pattern to filter files.
        """

        blueprint = index.build_component_blueprint(subsystem)
        if not blueprint.directory.exists():
            return (
                f"Error: Subsystem '{subsystem}' directory not found at "
                f"{blueprint.directory}"
            )

        files = list(blueprint.directory.rglob(pattern))
        if not files:
            return f"No files found in '{subsystem}' matching pattern '{pattern}'."

        lines = [f"# Files in '{subsystem}' matching '{pattern}'", ""]
        for file in files:
            rel_path = file.relative_to(blueprint.directory)
            lines.append(f"- `{rel_path}`")
        return "\n".join(lines)

    @mcp.tool()
    def list_example_directory_files(pattern: str = "*") -> str:
        """List files in the example source tree.

        Args:
            pattern: Glob pattern to filter files.
        """

        root = index.package_examples
        files = list(root.rglob(pattern))
        if not files:
            return f"No files found in example source tree matching pattern '{pattern}'."

        lines = [f"# Example source tree files matching '{pattern}'", ""]
        for file in files:
            rel_path = file.relative_to(root)
            lines.append(f"- `{rel_path}`")
        return "\n".join(lines)

