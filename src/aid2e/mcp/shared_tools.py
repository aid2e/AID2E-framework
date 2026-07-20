"""Generic MCP tools shared between planner and coder workflows."""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import Callable
from .repository import RepositoryIndex

from .utils import (
    MODULES,
    SEARCH_MODULES,
    SYMBOL_MODULES,
    doc_summary,
    get_package_overview,
    get_quickstart,
    iter_public_members,
    load_module,
    resolve_symbol,
    safe_signature,
)

def register_shared_tools(
    mcp,
    index: RepositoryIndex,
    workspace_resolver: Callable[[str], Path] | None = None,
    workspace_root_getter: Callable[[], Path] | None = None,
) -> None:
    """Register generic package and API discovery MCP tools.

    Args:
        mcp: FastMCP server instance.
        workspace_resolver: Optional callback for resolving safe workspace paths.
        workspace_root_getter: Optional callback that returns workspace root.
    """

    @mcp.tool()
    def package_overview() -> str:
        """Describe the AID2E package and MCP entrypoint.

        Returns:
            Markdown package overview.
        """
        return get_package_overview()

    @mcp.tool()
    def list_modules() -> str:
        """List high-value AID2E modules exposed to MCP.

        Returns:
            Markdown list of module names and descriptions.
        """
        lines = ["# AID2E Modules", ""]
        for module_name, description in MODULES.items():
            lines.append(f"- **{module_name}** - {description}")
        return "\n".join(lines)

    @mcp.tool()
    def list_available_symbols() -> str:
        """List curated public symbols tracked by the MCP server.

        Returns:
            Comma-separated symbol names.
        """
        available = ", ".join(sorted(SYMBOL_MODULES))
        return f"Available AID2E symbols: {available}"

    @mcp.tool()
    def get_api_reference(symbol: str = "all") -> str:
        """Return a concise API reference for a public symbol.

        Args:
            symbol: Symbol to inspect.

        Returns:
            Markdown API reference or an availability message.
        """
        if symbol == "all":
            return list_available_symbols()

        module_name, obj = resolve_symbol(symbol)
        if obj is None:
            available = ", ".join(sorted(SYMBOL_MODULES))
            return f"No reference found for `{symbol}`. Available symbols: {available}"

        lines = [f"## `{symbol}`", f"**Module:** `{module_name}`"]
        if inspect.isclass(obj):
            lines.append("**Type:** class")
        elif inspect.isfunction(obj):
            lines.append("**Type:** function")
        else:
            lines.append(f"**Type:** {type(obj).__name__}")
        lines.append(f"**Signature:** `{symbol}{safe_signature(obj)}`")
        lines.append("")
        lines.append(doc_summary(obj))
        return "\n".join(lines)

    @mcp.tool()
    def search_api(query: str) -> str:
        """Search public modules and symbols by keyword.

        Args:
            query: Search text.

        Returns:
            Markdown search result list.
        """
        needle = query.lower().strip()
        if not needle:
            return "Please provide a non-empty search query."

        results: list[str] = []
        for module_name in SEARCH_MODULES:
            module = load_module(module_name)
            if module is None:
                continue
            if needle in module_name.lower() or needle in (inspect.getdoc(module) or "").lower():
                results.append(f"- **Module `{module_name}`**: {doc_summary(module)}")

            for name, obj in iter_public_members(module):
                haystack = " ".join(
                    [
                        name.lower(),
                        module_name.lower(),
                        (inspect.getdoc(obj) or "").lower(),
                        safe_signature(obj).lower(),
                    ]
                )
                if needle in haystack:
                    results.append(f"- **`{name}`** (`{module_name}`): {doc_summary(obj)}")

        if not results:
            return f"No results found for `{query}`."

        return f"# Search results for `{query}`\n\n" + "\n".join(dict.fromkeys(results))


    @mcp.tool()
    def search_examples_by_keyword(query: str) -> str:
        """Search example scripts and notebooks by keyword.

        Args:
            query: Search text.
        """

        needle = query.lower().strip()
        if not needle:
            return "Please provide a non-empty search query."

        root = (index.package_examples).resolve()
        if not root.exists() or not root.is_dir():
            return "Example scripts directory not found."

        lines: list[str] = []
        for path in sorted(root.rglob("*")):
            if path.is_file() and path.suffix in {".py", ".ipynb"}:
                content = path.read_text(encoding="utf-8", errors="ignore").lower()
                if needle in content or needle in path.name.lower():
                    rel_path = path.relative_to(root)
                    lines.append(f"- `{rel_path}`")

        if not lines:
            return f"No example scripts found matching '{query}'."

        return f"# Example scripts matching '{query}'\n\n" + "\n".join(lines)


    @mcp.tool()
    def quickstart() -> str:
        """Return the shortest install-to-MCP connection path.

        Returns:
            Quickstart markdown instructions.
        """
        return get_quickstart()

    if workspace_resolver is None or workspace_root_getter is None:
        return

    def _resolve_tool_path(
        path_input: str | None = None,
        path: str | None = None,
        file_path: str | None = None,
        relative_path: str | None = None,
    ) -> Path:
        """Resolve the first non-empty path alias for workspace-safe tooling.

        Args:
            path_input: Primary path argument used by MCP tools.
            path: Generic path alias accepted from some clients.
            file_path: File-specific alias accepted from some clients.
            relative_path: Relative-path alias accepted from some clients.

        Returns:
            Resolved path inside the active workspace.

        Raises:
            ValueError: If no usable path-like argument is provided.
        """
        raw = path_input or path or file_path or relative_path
        if raw is None or not raw.strip():
            raise ValueError(
                "Missing path argument. Provide one of: "
                "path_input, path, file_path, relative_path."
            )
        return workspace_resolver(raw)

    @mcp.tool()
    def normalize_workspace_path(
        path_input: str | None = None,
        path: str | None = None,
        file_path: str | None = None,
        relative_path: str | None = None,
    ) -> str:
        """Normalize a user path and return safe absolute and relative forms.

        Args:
            path_input: Relative or absolute path input.
            path: Generic path alias.
            file_path: File-path alias.
            relative_path: Relative-path alias.

        Returns:
            Newline-delimited absolute and workspace-relative path values.
        """
        resolved = _resolve_tool_path(
            path_input=path_input,
            path=path,
            file_path=file_path,
            relative_path=relative_path,
        )
        root = workspace_root_getter()
        relative = resolved.relative_to(root)
        return f"absolute: {resolved.as_posix()}\nrelative: {relative.as_posix()}"


    # @mcp.tool()
    # def read_file_in_workspace(
    #     path_input: str | None = None,
    #     path: str | None = None,
    #     file_path: str | None = None,
    #     relative_path: str | None = None,
    # ) -> str:
    #     """Read a UTF-8 text file safely inside the workspace.

    #     Args:
    #         path_input: Relative or absolute file path.
    #         path: Generic path alias.
    #         file_path: File-path alias.
    #         relative_path: Relative-path alias.

    #     Returns:
    #         File content as plain text.
    #     """
    #     target = _resolve_tool_path(
    #         path_input=path_input,
    #         path=path,
    #         file_path=file_path,
    #         relative_path=relative_path,
    #     )
    #     if not target.exists() or not target.is_file():
    #         return f"not found: {target.as_posix()}"
    #     return target.read_text(encoding="utf-8")

    # @mcp.tool()
    # def create_directory_in_workspace(
    #     path_input: str | None = None,
    #     path: str | None = None,
    #     file_path: str | None = None,
    #     relative_path: str | None = None,
    # ) -> str:
    #     """Create a directory safely inside the active workspace.

    #     Args:
    #         path_input: Relative or absolute path input.
    #         path: Generic path alias.
    #         file_path: File-path alias.
    #         relative_path: Relative-path alias.

    #     Returns:
    #         Absolute path of the created directory.
    #     """
    #     target = _resolve_tool_path(
    #         path_input=path_input,
    #         path=path,
    #         file_path=file_path,
    #         relative_path=relative_path,
    #     )
    #     target.mkdir(parents=True, exist_ok=True)
    #     return f"created: {target.as_posix()}"


    # @mcp.tool()
    # def create_file_in_workspace(
    #     content: str ,
    #     path_input: str | None = None,
    #     overwrite: bool = False,
    #     path: str | None = None,
    #     file_path: str | None = None,
    #     relative_path: str | None = None,
    # ) -> str:
    #     """Create or update a UTF-8 text file inside the workspace.

    #     Args:
    #         content: Full text content to write.
    #         path_input: Relative or absolute file path.
    #         overwrite: When true, allow replacing existing file content.
    #         path: Generic path alias.
    #         file_path: File-path alias.
    #         relative_path: Relative-path alias.

    #     Returns:
    #         Absolute path of the created file.
    #     """

    #     if (file_path or path or relative_path or path_input) is None:
    #         return (
    #             "Missing path argument. Provide one of: "
    #             "path_input, path, file_path, relative_path."
    #         )

    #     target = _resolve_tool_path(
    #         path_input=path_input,
    #         path=path,
    #         file_path=file_path,
    #         relative_path=relative_path,
    #     )
    #     target.parent.mkdir(parents=True, exist_ok=True)

    #     if target.exists() and not overwrite:
    #         return (
    #             f"refused: {target.as_posix()} already exists. "
    #             "Set overwrite=true to replace."
    #         )

    #     target.write_text(content, encoding="utf-8")
    #     return f"written: {target.as_posix()}"

    # @mcp.tool()
    # def read_file_with_lines_in_workspace(
    #     path_input: str | None = None,
    #     path: str | None = None,
    #     file_path: str | None = None,
    #     relative_path: str | None = None,
    # ) -> str:
    #     """Read a file with 1-indexed line numbers prefixed, for use with replace_lines_in_workspace.

    #     Args:
    #         path_input: Relative or absolute file path.
    #         path: Generic path alias.
    #         file_path: File-path alias.
    #         relative_path: Relative-path alias.

    #     Returns:
    #         File content with each line prefixed as 'N: <line>'.
    #     """
    #     target = _resolve_tool_path(
    #         path_input=path_input, path=path, file_path=file_path, relative_path=relative_path,
    #     )
    #     if not target.exists() or not target.is_file():
    #         return f"not found: {target.as_posix()}"
    #     lines = target.read_text(encoding="utf-8").splitlines()
    #     return "\n".join(f"{i+1}: {line}" for i, line in enumerate(lines))

    # @mcp.tool()
    # def replace_lines_in_workspace(
    #     start_line: int,
    #     end_line: int,
    #     new_content: str,
    #     path_input: str | None = None,
    #     path: str | None = None,
    #     file_path: str | None = None,
    #     relative_path: str | None = None,
    # ) -> str:
    #     """Replace an inclusive 1-indexed line range with new content. No exact-text matching required.

    #     Args:
    #         start_line: First line to replace (1-indexed, inclusive).
    #         end_line: Last line to replace (1-indexed, inclusive). Use the same value as start_line to replace a single line.
    #         new_content: Full replacement text for that range (can be multiple lines, or empty string to delete the range).
    #         path_input: Relative or absolute file path.
    #         path: Generic path alias.
    #         file_path: File-path alias.
    #         relative_path: Relative-path alias.

    #     Returns:
    #         Confirmation with the new total line count, or a diagnostic error showing the
    #         actual current content of the requested range so the caller can retry correctly.
    #     """
    #     target = _resolve_tool_path(
    #         path_input=path_input, path=path, file_path=file_path, relative_path=relative_path,
    #     )
    #     if not target.exists() or not target.is_file():
    #         return f"not found: {target.as_posix()}"

    #     lines = target.read_text(encoding="utf-8").splitlines()
    #     n = len(lines)

    #     if not (1 <= start_line <= n) or not (1 <= end_line <= n) or start_line > end_line:
    #         context = "\n".join(f"{i+1}: {lines[i]}" for i in range(max(0, start_line - 3), min(n, start_line + 2)))
    #         return (
    #             f"invalid range: file has {n} lines, requested {start_line}-{end_line}. "
    #             f"Nearby actual content:\n{context}"
    #         )

    #     new_lines = new_content.splitlines() if new_content else []
    #     updated = lines[: start_line - 1] + new_lines + lines[end_line:]
    #     target.write_text("\n".join(updated) + "\n", encoding="utf-8")
    #     return f"replaced lines {start_line}-{end_line}; file now has {len(updated)} lines: {target.as_posix()}"

    # @mcp.tool()
    # def append_to_file_in_workspace(
    #     content: str,
    #     path_input: str | None = None,
    #     path: str | None = None,
    #     file_path: str | None = None,
    #     relative_path: str | None = None,
    # ) -> str:
    #     """Append text to the end of an existing file inside the workspace.

    #     No exact-text matching or line-number reasoning required — this always
    #     writes to the end of the file. Intended for building large files
    #     incrementally, one chunk at a time, without re-sending prior content.

    #     Args:
    #         content: Text to append. A newline is inserted before it automatically
    #             if the file doesn't already end with one.
    #         path_input: Relative or absolute file path.
    #         path: Generic path alias.
    #         file_path: File-path alias.
    #         relative_path: Relative-path alias.

    #     Returns:
    #         Confirmation with the new total line count, or an error if the file
    #         doesn't exist yet (use create_file_in_workspace to create it first).
    #     """
    #     target = _resolve_tool_path(
    #         path_input=path_input, path=path, file_path=file_path, relative_path=relative_path,
    #     )
    #     if not target.exists() or not target.is_file():
    #         return (
    #             f"not found: {target.as_posix()}. "
    #             "Create the file first with create_file_in_workspace before appending."
    #         )

    #     existing = target.read_text(encoding="utf-8")
    #     separator = "" if (not existing or existing.endswith("\n")) else "\n"
    #     target.write_text(existing + separator + content, encoding="utf-8")

    #     new_line_count = len(target.read_text(encoding="utf-8").splitlines())
    #     return f"appended; file now has {new_line_count} lines: {target.as_posix()} \n new content:\n{content}"

 