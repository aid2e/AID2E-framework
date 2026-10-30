"""Read-only Source Reference tools: symbol search, exact grep, source, and class contracts.

These tools expose concrete symbol-level context across the installed AID2E
package and its `examples/` tree (the Reference Source). None of them can
modify files.
"""

from __future__ import annotations

import re
from typing import Annotated

from pydantic import Field

from .repository import RepositoryIndex

_PATH_LIKE = re.compile(r"[\w.-]+(/[\w.-]+)+|[\w-]+\.(py|ya?ml|json|toml|txt|md)", re.ASCII)


def _workspace_hint(query: str) -> str:
    """Point a failed Source Reference lookup back at the user's project."""
    match = _PATH_LIKE.search(query)
    if match:
        return (
            f" `{match.group(0)}` may be a file in the user's project: "
            f"read it with read_file_in_workspace(path='{match.group(0)}')."
        )
    return " If it is in the user's project, use search_workspace or read_file_in_workspace."


def register_coder_tools(mcp, index: RepositoryIndex) -> None:
    """Register coder MCP tools.

    Args:
        mcp: FastMCP server instance.
        index: Repository semantic index.
    """

    @mcp.tool(
        description="AID2E source: find modules, classes, functions, and methods in the AID2E framework package, "
        "not the user's project (use search_workspace / read_file_in_workspace for the user's files)."
    )
    def search_repository(query: str, limit: int = 20) -> str:
        """Search repository symbols (modules, classes, functions, methods) by semantic query.

        Args:
            query: Symbol or concept to search.
            limit: Maximum number of matches to return.

        Returns:
            Ranked semantic search results.
        """
        results = index.search(query=query, limit=limit)
        if not results:
            return f"No AID2E source matches for '{query}'." + _workspace_hint(query)

        lines = [f"# Repository search for '{query}'", ""]
        for item in results:
            lines.append(
                f"- [{item.kind}] `{item.symbol}` (score={item.score:.2f}) - {item.summary}"
            )
        return "\n".join(lines)

    @mcp.tool(
        description="AID2E source: exact text or regex search of the AID2E framework source and examples "
        "(registry strings, YAML keys, imports), not the user's project; returns file:line matches."
    )
    def grep_framework_source(
        query: str,
        scope: Annotated[str, Field(description="'all', 'source', or 'examples'.")] = "all",
        file_pattern: Annotated[str, Field(description="Glob filter, e.g. '*.yml'.")] = "*",
        is_regex: bool = False,
        max_results: int = 50,
    ) -> str:
        """Search exact text or regex across the AID2E Reference Source and/or `examples/`.

        Use this when looking for registry strings, YAML keys, decorators, imports,
        or error messages that may not be top-level Python symbol names.

        Args:
            query: Text or regex pattern to search for.
            scope: 'all' (default), 'source' (only `src/aid2e`), or 'examples' (only `examples/`).
            file_pattern: Glob pattern filter such as '*.py' or '*.yml' (default '*').
            is_regex: Treat `query` as a regular expression when true.
            max_results: Maximum number of matching lines to return.

        Returns:
            Matching `file:line: content` lines from the Reference Source.
        """
        hits = index.grep(
            query=query,
            scope=scope,
            file_pattern=file_pattern,
            is_regex=is_regex,
            max_results=max_results,
        )
        if not hits:
            return f"No AID2E source matches for `{query}` in scope `{scope}`." + _workspace_hint(query)
        return f"# Reference Source matches for `{query}`\n\n" + "\n".join(hits)

    @mcp.tool(description="AID2E source: exact source and file:line range of an AID2E class, function, or method.")
    def get_symbol_source(
        symbol: Annotated[str, Field(description="e.g. 'BaseScheduler' or 'SlurmScheduler.submit'.")],
    ) -> str:
        """Get the exact source code and file/line location for a class, function, or method in AID2E.

        Args:
            symbol: Symbol name (e.g., 'BaseScheduler', 'SlurmScheduler.submit') or full qualified name.

        Returns:
            Source snippet text for the symbol.
        """
        source = index.get_symbol_source(symbol)
        if source is None:
            return f"'{symbol}' is not in the AID2E source." + _workspace_hint(symbol)
        return source

    @mcp.tool(description="AID2E source: an AID2E class's bases, known subclasses, attributes, and method signatures.")
    def get_class_contracts(class_name: str) -> str:
        """Return class inheritance, attributes, method signatures, and known subclasses.

        Args:
            class_name: Class symbol name or qualified name (e.g., 'BaseScheduler', 'BaseOptimizer').

        Returns:
            Class metadata with file location, base classes, known subclasses, attributes, and methods.
        """
        qualname, obj = index.resolve_indexed_symbol(class_name)
        if obj is None or not hasattr(obj, "methods"):
            return f"Class '{class_name}' is not in the AID2E source." + _workspace_hint(class_name)

        cls = obj
        subclasses = index.find_subclasses(cls.name)

        lines = [f"# Class contract: {cls.qualname}", ""]
        if cls.location:
            lines.append(
                f"- Location: `{index.display_path(cls.location.path)}:{cls.location.lineno}-{cls.location.end_lineno}`"
            )
        lines.append(f"- Bases: {', '.join(cls.bases) if cls.bases else 'none'}")
        if subclasses:
            lines.append(f"- Known subclasses: {', '.join(subclasses)}")
        if cls.decorators:
            lines.append(f"- Decorators: {', '.join(cls.decorators)}")
        lines.append(f"- Attributes: {', '.join(cls.attributes) if cls.attributes else 'none'}")
        lines.append("- Methods:")
        for method in cls.methods.values():
            dec_str = f" [{', '.join(method.decorators)}]" if method.decorators else ""
            ret_str = f" -> {method.returns}" if method.returns else ""
            lines.append(f"  - {method.name}{method.signature}{ret_str}{dec_str}")
        return "\n".join(lines)
