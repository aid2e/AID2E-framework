"""User Workspace MCP tools: list, search, read, write, edit, validate, and test.

These tools operate only inside the active User Workspace. Write tools refuse
any path inside the read-only AID2E Reference Source (the installed `aid2e`
package and its examples), even when the workspace root contains it, unless
the server operator sets `AID2E_ALLOW_SOURCE_WRITES=1`. `run_workspace_tests`
executes the user's code with pytest in the server's Python environment.
"""

from __future__ import annotations

import os
import re
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path, PurePath
from typing import Annotated, Callable

from pydantic import Field

from .repository import RepositoryIndex, _SKIP_DIRS
from .utils import check_python_syntax, format_numbered_lines

ALLOW_SOURCE_WRITES_ENV = "AID2E_ALLOW_SOURCE_WRITES"
TEST_TIMEOUT_ENV = "AID2E_TEST_TIMEOUT"

_MAX_WORKSPACE_SCAN = 2000
# Below the ~60 s request timeout of MCP clients such as OpenCode, so the model
# gets a TIMED OUT result instead of a client-side error while pytest keeps running.
_DEFAULT_TEST_TIMEOUT_SECONDS = 50
# torch/BLAS default to one thread per core; on a shared many-core node a tiny
# Ax test then spends most of its time in thread contention (36 s vs 5 s at 4).
_TEST_THREAD_ENV = ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS")
_DEFAULT_TEST_THREADS = "4"
_MAX_TEST_OUTPUT_CHARS = 8000
# pytest exit codes: https://docs.pytest.org/en/stable/reference/exit-codes.html
_PYTEST_STATUS = {
    0: "PASSED",
    1: "FAILED",
    2: "INTERRUPTED (collection error or keyboard interrupt)",
    3: "INTERNAL ERROR",
    4: "USAGE ERROR",
    5: "NO TESTS COLLECTED (name files test_*.py and functions test_*)",
}


def _test_timeout_seconds() -> float:
    """Return the operator-configured pytest timeout, falling back to the default."""
    try:
        value = float(os.environ.get(TEST_TIMEOUT_ENV, ""))
    except ValueError:
        return _DEFAULT_TEST_TIMEOUT_SECONDS
    return value if value > 0 else _DEFAULT_TEST_TIMEOUT_SECONDS


def _test_env() -> dict[str, str]:
    """Environment for a test run: no bytecode files and capped math threads (operator values win)."""
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    for name in _TEST_THREAD_ENV:
        env.setdefault(name, _DEFAULT_TEST_THREADS)
    return env


def _kill_process_tree(proc: subprocess.Popen) -> None:
    """Kill a test run and any workers it started (its own process group on POSIX)."""
    try:
        if os.name == "posix":
            os.killpg(proc.pid, signal.SIGKILL)
        else:
            proc.kill()
    except (ProcessLookupError, PermissionError):
        pass


def _clip(text: str, limit: int = _MAX_TEST_OUTPUT_CHARS) -> str:
    """Keep the start of long output (first failure and its `E` lines) and the end (summary)."""
    if len(text) <= limit:
        return text
    head, tail = text[: limit * 3 // 4], text[-(limit // 4):]
    return f"{head}\n... ({len(text) - len(head) - len(tail)} characters omitted) ...\n{tail}"


def _objective_plan_order_warnings(node, path: str = "") -> list[str]:
    """Warn about objective-plan steps with no `depends_on` after the first one.

    AID2E orders such steps by string hash, which changes per process, so a plan
    listed as a -> b -> c can run c first and pass or fail from one run to the next.
    """
    warnings: list[str] = []
    if isinstance(node, list):
        for i, item in enumerate(node):
            warnings.extend(_objective_plan_order_warnings(item, f"{path}[{i}]"))
        return warnings
    if not isinstance(node, dict):
        return warnings
    for key, value in node.items():
        child = f"{path}.{key}" if path else str(key)
        steps = value.get("steps") if key == "objective_plan" and isinstance(value, dict) else None
        stages = steps.get("stages") if isinstance(steps, dict) else None
        if isinstance(stages, list) and len(stages) > 1:
            unordered = [
                str(stage.get("name"))
                for stage in stages[1:]
                if isinstance(stage, dict) and not stage.get("depends_on")
            ]
            if unordered:
                warnings.append(
                    f"WARNING: {child}: steps {', '.join(unordered)} have no depends_on, so AID2E "
                    "runs them in an arbitrary order that changes between runs (listing order is "
                    "not used). Add depends_on: [<previous step>] to each step that needs an "
                    "earlier one. A step's return value reaches the steps that depend on it as "
                    "inputs['<step name>']; no shared files are needed."
                )
        warnings.extend(_objective_plan_order_warnings(value, child))
    return warnings


def _workflow_structure_warnings(data: dict) -> list[str]:
    """Warn about workflow blocks that pass schema validation but never run.

    The workflow models ignore unknown keys, so a misplaced `stages` block is dropped
    on load, and a workflow with nothing to run fails later with only a missing
    objectives error.
    """
    from aid2e.utilities.configurations.experimental_stack_config import (
        StackBranchDefinition,
        StackJobDefinition,
        StackStageDefinition,
        StackWorkflowDefinition,
        StackWorkflowsConfiguration,
    )

    warnings: list[str] = []

    def check_keys(node, model, path: str) -> bool:
        if not isinstance(node, dict):
            return False
        # A stray description is harmless, and the EPIC examples use one on stages.
        unknown = [
            str(key) for key in node if key not in model.model_fields and key != "description"
        ]
        if unknown:
            warnings.append(
                f"WARNING: {path}: AID2E ignores unknown keys {', '.join(unknown)}, so they have "
                f"no effect. Valid keys: {', '.join(model.model_fields)}."
            )
        return True

    def items(node: dict, key: str) -> list:
        value = node.get(key)
        return value if isinstance(value, list) else []

    def has_plan(node: dict) -> bool:
        return bool(node.get("combined_objectives")) or any(
            isinstance(objective, dict) and objective.get("objective_plan")
            for objective in items(node, "objectives")
        )

    container = data.get("workflows")
    if not check_keys(container, StackWorkflowsConfiguration, "workflows"):
        return warnings
    problem = data.get("problem")
    problem_has_plan = isinstance(problem, dict) and has_plan(problem)
    for w, workflow in enumerate(items(container, "workflows")):
        path = f"workflows.workflows[{w}]"
        if not check_keys(workflow, StackWorkflowDefinition, path):
            continue
        if not (workflow.get("branches") or problem_has_plan or has_plan(workflow)):
            warnings.append(
                f"WARNING: {path}: no branches, so no stage or job runs and the trial fails with "
                "'Workflow did not produce declared objectives'. Stages go under "
                "branches: [{name: main, stages: [...]}]."
            )
        for b, branch in enumerate(items(workflow, "branches")):
            branch_path = f"{path}.branches[{b}]"
            if not check_keys(branch, StackBranchDefinition, branch_path):
                continue
            for s, stage in enumerate(items(branch, "stages")):
                stage_path = f"{branch_path}.stages[{s}]"
                if not check_keys(stage, StackStageDefinition, stage_path):
                    continue
                for j, job in enumerate(items(stage, "jobs")):
                    check_keys(job, StackJobDefinition, f"{stage_path}.jobs[{j}]")
    return warnings


def _workspace_entries(directory: Path, recursive: bool):
    """Yield visible entries with a hard traversal cap; never follow directory symlinks."""
    pending = [directory]
    scanned = 0
    while pending:
        current = pending.pop()
        children = []
        try:
            with os.scandir(current) as iterator:
                for entry in iterator:
                    scanned += 1
                    if scanned > _MAX_WORKSPACE_SCAN:
                        yield None
                        return
                    if entry.name in _SKIP_DIRS or (
                        entry.name.startswith(".") and entry.name not in {".gitignore", ".env"}
                    ):
                        continue
                    children.append(entry)
        except OSError:
            continue
        subdirs = []
        for entry in sorted(children, key=lambda item: item.name):
            path = Path(entry.path)
            try:
                if entry.is_dir(follow_symlinks=False):
                    if recursive:
                        subdirs.append(path)
                    else:
                        yield path
                elif entry.is_file(follow_symlinks=False):
                    yield path
            except OSError:
                continue
        pending.extend(reversed(subdirs))


def _workspace_pattern_matches(path: Path, root: Path, pattern: str) -> bool:
    return PurePath(path.relative_to(root)).match(pattern)


def source_writes_allowed() -> bool:
    """Return whether the operator explicitly allowed writes into the Reference Source."""
    return os.environ.get(ALLOW_SOURCE_WRITES_ENV, "").strip().lower() in {"1", "true", "yes"}


def reference_source_roots(index: RepositoryIndex) -> tuple[Path, ...]:
    """Return the resolved read-only Reference Source roots (package and examples)."""
    return tuple(dict.fromkeys(p.resolve() for p in (index.package_root, index.package_examples)))


def in_reference_source(path: Path, index: RepositoryIndex) -> bool:
    """Return whether `path` is inside the read-only AID2E Reference Source."""
    resolved = path.resolve()
    return any(resolved == root or root in resolved.parents for root in reference_source_roots(index))


WorkspacePath = Annotated[str, Field(description="Workspace-relative file path, e.g. 'schedulers/k8s/runner.py'.")]


def register_shared_tools(
    mcp,
    index: RepositoryIndex,
    workspace_resolver: Callable[[str], Path] | None = None,
    workspace_root_getter: Callable[[], Path] | None = None,
    workspace_tools: str = "all",
) -> None:
    """Register the User Workspace MCP tools.

    Args:
        mcp: FastMCP server instance.
        index: Shared RepositoryIndex; its package and examples roots are the
            read-only Reference Source that write tools refuse to modify.
        workspace_resolver: Callback for resolving safe workspace paths.
        workspace_root_getter: Callback that returns workspace root.
        workspace_tools: Which tools to register: 'all' (full read/write suite
            plus `run_workspace_tests`),
            'validate' (only `validate_workspace_file`, for clients that bring
            their own file tools), or 'none'.
    """
    if workspace_tools not in {"all", "validate", "none"}:
        raise ValueError(f"Unknown workspace_tools selection: {workspace_tools!r}")
    if workspace_tools == "none" or workspace_resolver is None or workspace_root_getter is None:
        return

    # A client that times out does not stop the server-side run; refuse a retry
    # instead of starting a second pytest that competes for the same CPUs.
    test_run_lock = threading.Lock()

    def _workspace_tool(description: str):
        """Register a workspace tool only for the full suite."""

        def decorator(fn):
            return mcp.tool(description=description)(fn) if workspace_tools == "all" else fn

        return decorator

    def _display(path: Path) -> str:
        """Return `path` relative to the workspace root (absolute if outside it)."""
        try:
            return path.relative_to(workspace_root_getter()).as_posix() or "."
        except ValueError:
            return path.as_posix()

    def _check_writable(target: Path) -> None:
        """Refuse writes inside the read-only Reference Source."""
        if not source_writes_allowed() and in_reference_source(target, index):
            raise PermissionError(
                f"{_display(target)} is in the read-only AID2E Reference Source. "
                "Write your code in the User Workspace instead (writes to AID2E itself "
                "can only be enabled by the server operator)."
            )

    def _resolve_tool_path(path: str, *, write: bool = False) -> Path:
        """Resolve the `path` argument safely inside the workspace."""
        raw = (path or "").strip()
        if not raw:
            raise ValueError("Missing `path` argument: pass the workspace-relative file as `path`.")
        option_in_path = re.search(
            r"(?<![A-Za-z0-9_])(?:overwrite|start_line|end_line|line_numbers|content|new_content|path)\s*=",
            raw,
            re.IGNORECASE,
        )
        if option_in_path:
            raise ValueError(
                f"The path includes `{option_in_path.group(0).strip()}`. "
                "Pass only the filename in `path`; pass other options as separate tool arguments."
            )
        target = workspace_resolver(raw)
        if write:
            _check_writable(target)
        return target

    @_workspace_tool("User project: list files and folders in the user's project. Start non-recursive; narrow `directory` before recursing.")
    def list_workspace_files(
        directory: str = ".",
        pattern: Annotated[str, Field(description="Glob filter, e.g. '*.py'.")] = "*",
        recursive: bool = False,
    ) -> str:
        """List files and directories inside the User Workspace.

        Args:
            directory: Workspace-relative directory to list.
            pattern: Glob pattern to filter files.
            recursive: When true, list files under subdirectories (bounded).

        Returns:
            Markdown list of workspace-relative file paths.
        """
        try:
            target_dir = workspace_resolver(directory or ".")
        except Exception as exc:
            return f"error: {exc}"

        if not target_dir.exists():
            return f"not found: {_display(target_dir)}"
        if not target_dir.is_dir():
            return f"not a directory: {_display(target_dir)}"

        root = workspace_root_getter()
        entries: list[str] = []
        truncated = False
        for item in _workspace_entries(target_dir, recursive):
            if item is None:
                truncated = True
                break
            if not _workspace_pattern_matches(item, target_dir, pattern):
                continue
            rel_str = item.relative_to(root).as_posix()
            if item.is_dir():
                if not recursive:
                    entries.append(f"- `{rel_str}/`")
            else:
                entries.append(f"- `{rel_str}`")
            if len(entries) >= 300:
                truncated = True
                break

        if truncated:
            entries.append(
                "- ... (truncated; narrow `directory` or `pattern`, or list a subdirectory)"
            )
        if not entries:
            return f"No files found in workspace directory `{directory}` matching `{pattern}`."
        return f"# Workspace files in `{target_dir.relative_to(root).as_posix()}` (root: `{root.as_posix()}`)\n\n" + "\n".join(entries)

    @_workspace_tool("User project: search the user's project files for a function name, text, or regex; returns file:line matches.")
    def search_workspace(
        query: str,
        directory: str = ".",
        file_pattern: Annotated[str, Field(description="Glob filter, e.g. '*.yml'.")] = "*",
        is_regex: bool = False,
        max_results: int = 50,
    ) -> str:
        """Search files in the User Workspace for a keyword or regular expression.

        Args:
            query: Text or regex pattern to search for.
            directory: Workspace-relative subdirectory to search.
            file_pattern: File glob filter.
            is_regex: Treat `query` as a regular expression when true.
            max_results: Maximum number of matching lines to return.

        Returns:
            Matching workspace-relative `file:line: content` lines.
        """
        needle = (query or "").strip()
        if not needle:
            return "Please provide a non-empty search query."

        try:
            target_dir = workspace_resolver(directory or ".")
        except Exception as exc:
            return f"error: {exc}"

        if not target_dir.exists() or not target_dir.is_dir():
            return f"not found: {_display(target_dir)}"

        if is_regex:
            try:
                regex = re.compile(needle, re.IGNORECASE)
            except re.error as exc:
                return f"Invalid regex '{needle}': {exc}"
        else:
            regex = re.compile(re.escape(needle), re.IGNORECASE)

        root = workspace_root_getter()
        hits: list[str] = []
        truncated = False
        for path in _workspace_entries(target_dir, recursive=True):
            if path is None:
                truncated = True
                break
            if not _workspace_pattern_matches(path, target_dir, file_pattern) or not path.is_file():
                continue
            if path.suffix.lower() in {".pyc", ".pyo", ".so", ".png", ".jpg", ".jpeg", ".gif", ".pdf"}:
                continue
            try:
                if path.stat().st_size > 2_000_000:
                    continue
                text = path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            rel_str = path.relative_to(root).as_posix()
            for lineno, line in enumerate(text.splitlines(), start=1):
                if regex.search(line):
                    hits.append(f"{rel_str}:{lineno}: {line.strip()[:200]}")
                    if len(hits) >= max_results:
                        return f"# Workspace matches for `{query}` (showing first {max_results})\n\n" + "\n".join(hits)

        if not hits and truncated:
            return f"No matches in the first {_MAX_WORKSPACE_SCAN} entries. Narrow `directory` or `file_pattern`."
        if not hits:
            try:
                is_file = workspace_resolver(needle).is_file()
            except Exception:
                is_file = False
            if is_file:
                return (
                    f"No lines contain `{query}`, but it is a file: "
                    f"read it with read_file_in_workspace(path='{needle}')."
                )
            return f"No matches found for `{query}` in workspace `{directory}`."
        suffix = f"\n... (scan limited to {_MAX_WORKSPACE_SCAN} entries; narrow `directory`)" if truncated else ""
        return f"# Workspace matches for `{query}`\n\n" + "\n".join(hits) + suffix

    @_workspace_tool(
        "User project: read a file in the user's project. Set line_numbers=true before replace_lines_in_workspace; "
        "never copy the `N:` prefixes into file content."
    )
    def read_file_in_workspace(
        path: WorkspacePath,
        start_line: Annotated[int, Field(description="First line, 1-indexed.")] = 1,
        end_line: Annotated[int, Field(description="Last line; 0 = end of file.")] = 0,
        line_numbers: Annotated[bool, Field(description="Prefix each line with `N: `.")] = False,
    ) -> str:
        """Read a UTF-8 text file inside the User Workspace.

        Args:
            path: Workspace-relative file path.
            start_line: 1-indexed first line to read.
            end_line: 1-indexed last line to read (0 means end of file).
            line_numbers: Prefix each line with `N: ` for line-based editing.

        Returns:
            File text, or a numbered slice when line numbers or a range are requested.
        """
        try:
            target = _resolve_tool_path(path)
        except Exception as exc:
            return f"error: {exc}"

        if not target.exists() or not target.is_file():
            return f"not found: {_display(target)}"

        text = target.read_text(encoding="utf-8", errors="replace")
        if line_numbers or (start_line and start_line > 1) or (end_line and end_line > 0):
            rendered, s, e, total = format_numbered_lines(
                text, start_line=start_line, end_line=end_line, include_line_numbers=True
            )
            header = f"# {_display(target)} (lines {s}-{e} of {total})"
            return f"{header}\n{rendered}" if rendered else f"{header}\n(empty file)"
        return text

    @_workspace_tool(
        "User project: create a file in the user's project (parent folders are created). "
        "Set overwrite=true to replace an existing file. Checks Python syntax."
    )
    def create_file_in_workspace(
        path: WorkspacePath,
        content: Annotated[str, Field(description="Complete file content.")],
        overwrite: bool = False,
    ) -> str:
        """Create or replace a UTF-8 text file inside the User Workspace.

        Args:
            path: Workspace-relative filename.
            content: Full text content to write.
            overwrite: Allow replacing an existing file.

        Returns:
            Confirmation with line count and any Python syntax warning.
        """
        try:
            target = _resolve_tool_path(path, write=True)
        except Exception as exc:
            return f"error: {exc}"

        if target.exists() and not overwrite:
            return (
                f"refused: {_display(target)} already exists. "
                "Set overwrite=true to replace, or use replace_lines_in_workspace / append_to_file_in_workspace."
            )

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        line_count = len(content.splitlines())
        syntax_note = check_python_syntax(target, content)
        if syntax_note:
            return f"written ({line_count} lines): {_display(target)}\n{syntax_note}"
        return f"written ({line_count} lines): {_display(target)}"

    @_workspace_tool("User project: move or rename a file in the user's project. Set overwrite=true to replace an existing destination.")
    def move_file_in_workspace(
        source_path: str,
        destination_path: str,
        overwrite: bool = False,
    ) -> str:
        """Move or rename a file within the User Workspace.

        Args:
            source_path: Existing workspace-relative filename.
            destination_path: New workspace-relative filename.
            overwrite: Whether to replace an existing destination file.

        Returns:
            Confirmation or refusal message.
        """
        try:
            # A mistaken filename may literally contain `.overwrite=True`;
            # moving it is the recovery path, so only the destination uses
            # the option-in-path guard.
            source = workspace_resolver(source_path)
            _check_writable(source)
            destination = _resolve_tool_path(destination_path, write=True)
        except Exception as exc:
            return f"error: {exc}"

        if not source.is_file():
            return f"not found: {_display(source)}"
        if source == destination:
            return "error: source and destination are the same file"
        if destination.exists():
            if not destination.is_file():
                return f"refused: destination is not a file: {_display(destination)}"
            if not overwrite:
                return (
                    f"refused: {_display(destination)} already exists. "
                    "Set overwrite=true only if replacing it is intentional."
                )

        destination.parent.mkdir(parents=True, exist_ok=True)
        if overwrite:
            source.replace(destination)
        else:
            source.rename(destination)
        return f"moved: {_display(source)} -> {_display(destination)}"

    @_workspace_tool(
        "User project: replace lines start_line..end_line (inclusive, 1-indexed) of a file in the user's project. "
        "Read it with line_numbers=true first and pass those lines' current text as old_content; the edit is "
        "refused if they differ. Empty new_content deletes the lines. Line numbers after the edit shift; use the "
        "numbers in the result for a further edit."
    )
    def replace_lines_in_workspace(
        path: WorkspacePath,
        start_line: int,
        end_line: int,
        old_content: Annotated[
            str, Field(description="Current text of lines start_line..end_line, without the `N: ` prefixes.")
        ],
        new_content: str,
    ) -> str:
        """Replace an inclusive 1-indexed line range in a workspace file.

        The range must still hold `old_content` (compared line by line, ignoring
        trailing whitespace). This catches line numbers made stale by an earlier
        edit, which would otherwise overwrite the wrong lines.

        Args:
            path: Workspace-relative file path.
            start_line: First line to replace (inclusive).
            end_line: Last line to replace (inclusive).
            old_content: Current text of the range, as read with line numbers.
            new_content: Replacement text (empty string deletes the range).

        Returns:
            Confirmation with the edited region renumbered, or a refusal showing
            the range's actual content.
        """
        try:
            target = _resolve_tool_path(path, write=True)
        except Exception as exc:
            return f"error: {exc}"

        if not target.exists() or not target.is_file():
            return f"not found: {_display(target)}"

        lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
        n = len(lines)

        if not (1 <= start_line <= n) or not (1 <= end_line <= n) or start_line > end_line:
            ctx_start = max(0, min(start_line - 3, n - 5))
            ctx_end = min(n, max(end_line + 2, start_line + 3))
            context = "\n".join(f"{i+1}: {lines[i]}" for i in range(ctx_start, ctx_end))
            return (
                f"invalid range: file has {n} lines, requested {start_line}-{end_line}. "
                f"Nearby actual content:\n{context}"
            )

        expected = [line.rstrip() for line in old_content.splitlines()]
        actual = [line.rstrip() for line in lines[start_line - 1 : end_line]]
        if expected != actual:
            shown = "\n".join(f"{i}: {lines[i - 1]}" for i in range(start_line, end_line + 1))
            hint = ""
            width = len(expected)
            matches = [
                i + 1 for i in range(n - width + 1)
                if width and [line.rstrip() for line in lines[i : i + width]] == expected
            ]
            if len(matches) == 1:
                hint = f"\nold_content is at lines {matches[0]}-{matches[0] + width - 1}; retry with that range."
            return (
                f"refused: lines {start_line}-{end_line} of {_display(target)} do not match old_content "
                f"(stale line numbers?). Nothing was changed. Current lines {start_line}-{end_line}:\n{shown}{hint}"
            )

        new_lines = new_content.splitlines() if new_content else []
        updated = lines[: start_line - 1] + new_lines + lines[end_line:]
        final_text = "\n".join(updated) + ("\n" if updated else "")
        target.write_text(final_text, encoding="utf-8")

        syntax_note = check_python_syntax(target, final_text)
        new_end = start_line + len(new_lines) - 1
        view_start, view_end = max(1, start_line - 2), min(len(updated), max(new_end, start_line - 1) + 2)
        region = "\n".join(f"{i}: {updated[i - 1]}" for i in range(view_start, view_end + 1))
        msg = (
            f"replaced lines {start_line}-{end_line}; file now has {len(updated)} lines: {_display(target)}\n"
            f"Lines {view_start}-{view_end} now:\n{region}"
        )
        if syntax_note:
            return f"{msg}\n{syntax_note}"
        return msg

    @_workspace_tool("User project: append text to an existing file in the user's project, to build large files in chunks.")
    def append_to_file_in_workspace(
        path: WorkspacePath,
        content: str,
    ) -> str:
        """Append text to the end of an existing User Workspace file.

        Args:
            path: Workspace-relative file path.
            content: Text to append; a newline is inserted first if needed.

        Returns:
            Confirmation with the new line count and any Python syntax warning.
        """
        try:
            target = _resolve_tool_path(path, write=True)
        except Exception as exc:
            return f"error: {exc}"

        if not target.exists() or not target.is_file():
            return (
                f"not found: {_display(target)}. "
                "Create the file first with create_file_in_workspace before appending."
            )

        existing = target.read_text(encoding="utf-8", errors="replace")
        separator = "" if (not existing or existing.endswith("\n")) else "\n"
        combined = existing + separator + content
        target.write_text(combined, encoding="utf-8")

        new_line_count = len(combined.splitlines())
        syntax_note = check_python_syntax(target, combined)
        msg = f"appended; file now has {new_line_count} lines: {_display(target)}"
        if syntax_note:
            return f"{msg}\n{syntax_note}"
        return msg

    @_workspace_tool(
        "User project: run pytest on a test file or folder in the user's project and return the result. "
        "This executes the user's code. Write a small test for new code, run it, and fix failures before reporting done."
    )
    def run_workspace_tests(
        path: Annotated[str, Field(description="Workspace-relative test file or folder, e.g. 'test_sphere.py'.")] = ".",
        test_filter: Annotated[str, Field(description="Optional pytest -k expression to select tests.")] = "",
    ) -> str:
        """Run pytest on a User Workspace test file or directory.

        Uses the MCP server's Python interpreter (where `aid2e` is installed),
        runs from the workspace root with no shell and closed stdin, and kills
        the run, including any workers it started, after `AID2E_TEST_TIMEOUT`
        seconds (default 50). Math libraries get 4 threads unless the server's
        environment sets them. Only one run happens at a time.

        Args:
            path: Workspace-relative test file or directory.
            test_filter: Optional pytest `-k` expression.

        Returns:
            Pass/fail status, exit code, duration, and pytest's output without captured
            stdout/logs (long output keeps its start and end).
        """
        try:
            target = _resolve_tool_path(path)
        except Exception as exc:
            return f"error: {exc}"

        if not target.exists():
            return f"not found: {_display(target)}"
        if in_reference_source(target, index):
            return (
                f"refused: {_display(target)} is in the read-only AID2E Reference Source. "
                "Run tests written in the User Workspace."
            )

        # Captured stdout/logs and warning summaries are dropped: AID2E's executor logs
        # ~10 kB per run, which pushed the failing `E` lines out of the returned output.
        command = [
            sys.executable, "-m", "pytest", str(target),
            "-q", "--maxfail=3", "--tb=short", "--no-header", "--color=no", "-p", "no:cacheprovider",
            "--show-capture=no", "--disable-warnings",
        ]
        if test_filter.strip():
            command += ["-k", test_filter.strip()]
        timeout = _test_timeout_seconds()

        if not test_run_lock.acquire(blocking=False):
            return (
                "busy: an earlier run_workspace_tests call is still running and will stop within "
                f"{timeout:.0f}s. Do not start another run yet; tell the user the result is pending, "
                "or make the test smaller before running it again."
            )
        try:
            started = time.monotonic()
            # stdin must not be inherited: over stdio it carries the MCP protocol.
            proc = subprocess.Popen(
                command,
                cwd=workspace_root_getter(),
                env=_test_env(),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                start_new_session=os.name == "posix",
            )
            try:
                raw, _ = proc.communicate(timeout=timeout)
            except subprocess.TimeoutExpired:
                _kill_process_tree(proc)
                raw, _ = proc.communicate()
                output = _clip(raw.decode("utf-8", errors="replace"))
                return (
                    f"pytest TIMED OUT after {timeout:.0f}s and was stopped: {_display(target)}. "
                    "The code was not verified. Make the test smaller or faster (fewer trials or "
                    "evaluations), or tell the user it timed out.\n\n" + output
                )
            elapsed = time.monotonic() - started
        finally:
            test_run_lock.release()
        output = raw.decode("utf-8", errors="replace")

        if proc.returncode != 0 and "No module named pytest" in output:
            return (
                f"error: pytest is not installed for the MCP server's Python ({sys.executable}). "
                "Ask the user to run `python -m pip install pytest` in that environment."
            )
        status = _PYTEST_STATUS.get(proc.returncode, "ERROR")
        return f"pytest {status} (exit {proc.returncode}, {elapsed:.1f}s): {_display(target)}\n\n{_clip(output)}"

    @mcp.tool(
        description="User project: validate a .py file (syntax) or an AID2E config (.yml/.yaml/.json/.config/.params) "
        "in the user's project against AID2E's schemas."
    )
    def validate_workspace_file(path: WorkspacePath) -> str:
        """Validate a Python file or AID2E configuration file in the User Workspace.

        Args:
            path: Workspace-relative file path.

        Returns:
            Validation report indicating success or exact line/schema errors.
        """
        try:
            target = _resolve_tool_path(path)
        except Exception as exc:
            return f"error: {exc}"

        if not target.exists() or not target.is_file():
            return f"not found: {_display(target)}"

        suffix = target.suffix.lower()
        text = target.read_text(encoding="utf-8", errors="replace")

        if suffix == ".py":
            err = check_python_syntax(target, text)
            if err:
                return f"INVALID Python syntax in {_display(target)}:\n{err}"
            try:
                mod = target.stem
                from .parser import RepositoryParser

                info = RepositoryParser.parse_file(target, mod)
                classes = list(info.classes.keys())
                funcs = list(info.functions.keys())
                return (
                    f"VALID Python file: {_display(target)} ({len(text.splitlines())} lines)\n"
                    f"- Classes: {', '.join(classes) if classes else 'none'}\n"
                    f"- Functions: {', '.join(funcs) if funcs else 'none'}"
                )
            except Exception as exc:
                return f"VALID Python syntax: {_display(target)} ({exc})"

        if suffix in {".yml", ".yaml", ".json", ".config", ".params"}:
            import yaml

            try:
                data = yaml.safe_load(text)
            except Exception as exc:
                return f"INVALID YAML/JSON syntax in {_display(target)}:\n{exc}"

            if not isinstance(data, dict):
                return f"VALID YAML/JSON syntax in {_display(target)} (top-level type: {type(data).__name__})."

            try:
                from aid2e.cli._helpers import detect_config_type
                from aid2e.utilities.configurations import (
                    DesignConfigLoader,
                    OptimizerConfiguration,
                    ProblemConfigLoader,
                    load_config,
                )

                cfg_type = detect_config_type(data)
                if cfg_type == "unknown":
                    return (
                        f"UNRECOGNIZED AID2E configuration: {_display(target)}. "
                        "YAML/JSON syntax is valid, but no AID2E schema was identified or validated."
                    )
                if cfg_type == "full":
                    load_config(str(target))
                elif cfg_type == "problem":
                    ProblemConfigLoader.load(str(target))
                elif cfg_type == "design":
                    DesignConfigLoader.load(str(target))
                elif cfg_type == "optimizer":
                    opt = data.get("optimizer", data)
                    OptimizerConfiguration(**opt)
                report = f"VALID AID2E configuration ({cfg_type}): {_display(target)}"
                return "\n".join(
                    [
                        report,
                        *_workflow_structure_warnings(data),
                        *_objective_plan_order_warnings(data),
                    ]
                )
            except Exception as exc:
                return (
                    f"YAML syntax is valid in {_display(target)}, "
                    f"but AID2E schema validation reported: {exc}"
                )

        return f"File exists ({len(text.splitlines())} lines): {_display(target)}"
