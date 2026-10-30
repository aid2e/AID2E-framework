"""Shared utility helpers for AID2E MCP tools."""

from __future__ import annotations

import ast
from pathlib import Path


def check_python_syntax(path: Path, source: str | None = None) -> str | None:
    """Check Python syntax if `path` is a `.py` file.

    Returns:
        None if syntax is valid (or not a `.py` file), or a concise warning string
        with the line number and syntax error details.
    """
    if path.suffix.lower() != ".py":
        return None
    text = source if source is not None else path.read_text(encoding="utf-8", errors="replace")
    try:
        ast.parse(text, filename=path.as_posix())
        return None
    except SyntaxError as exc:
        return (
            f"syntax warning ({path.name} line {exc.lineno}): {exc.msg}"
            + (f"\n  {exc.text.rstrip()}" if exc.text else "")
        )


def format_numbered_lines(
    text: str,
    start_line: int = 1,
    end_line: int = 0,
    include_line_numbers: bool = True,
) -> tuple[str, int, int, int]:
    """Slice text by 1-indexed inclusive line range and optionally prefix line numbers.

    Returns:
        Tuple of (formatted_text, actual_start, actual_end, total_lines).
    """
    lines = text.splitlines()
    total = len(lines)
    if total == 0:
        return ("", 0, 0, 0)

    s = max(1, start_line or 1)
    e = total if (not end_line or end_line <= 0 or end_line > total) else end_line
    if s > e:
        s = min(s, total)
        e = s

    selected = lines[s - 1 : e]
    if include_line_numbers:
        rendered = "\n".join(f"{i}: {line}" for i, line in enumerate(selected, start=s))
    else:
        rendered = "\n".join(selected)
    return rendered, s, e, total
