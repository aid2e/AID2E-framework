"""Coder-oriented MCP tools.

These tools expose concrete symbol-level context for implementation models.
"""

from __future__ import annotations

from .repository import RepositoryIndex


def register_coder_tools(mcp, index: RepositoryIndex) -> None:
    """Register coder-only MCP tools.

    Args:
        mcp: FastMCP server instance.
        index: Repository semantic index.
    """

    @mcp.tool()
    def search_repository(query: str, limit: int = 20) -> str:
        """Search repository symbols by semantic query.

        Args:
            query: Symbol or concept to search.
            limit: Maximum number of matches to return.

        Returns:
            Ranked semantic search results.
        """
        results = index.search(query=query, limit=limit)
        if not results:
            return f"No semantic matches found for '{query}'."

        lines = [f"# Repository search for '{query}'", ""]
        for item in results:
            lines.append(
                f"- [{item.kind}] `{item.symbol}` (score={item.score:.2f}) - {item.summary}"
            )
        return "\n".join(lines)

    @mcp.tool()
    def get_symbol_source(symbol: str) -> str:
        """Get source code for a symbol from the semantic index.

        Args:
            symbol: Symbol name or qualified name.

        Returns:
            Source snippet text for the symbol.
        """
        source = index.get_symbol_source(symbol)
        if source is None:
            return f"Source not found for symbol '{symbol}'."
        return source

    @mcp.tool()
    def get_class_contracts(class_name: str) -> str:
        """Return class signature details for implementation guidance.

        Args:
            class_name: Class symbol name or qualified name.

        Returns:
            Class metadata with base classes and methods.
        """
        index.ensure_built()

        target = class_name
        if class_name in index.info.symbols:
            target = index.info.symbols[class_name]

        cls = index.info.classes.get(target)
        if cls is None:
            return f"Class '{class_name}' not found."

        lines = [f"# Class contract: {cls.qualname}", ""]
        lines.append(f"- Bases: {', '.join(cls.bases) if cls.bases else 'none'}")
        lines.append(f"- Attributes: {', '.join(cls.attributes) if cls.attributes else 'none'}")
        lines.append("- Methods:")
        for method in cls.methods.values():
            lines.append(f"  - {method.name}{method.signature}")
        return "\n".join(lines)
