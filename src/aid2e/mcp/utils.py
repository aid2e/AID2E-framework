"""Shared utility helpers for AID2E MCP tools."""

from __future__ import annotations

import importlib
import inspect
from typing import Iterable

from aid2e import __MAIN_VERSION__

MODULES = {
    "aid2e": "Top-level package metadata and version information.",
    "aid2e.cli.aid2e_cli": "Click CLI entry point for loading and validating configs.",
    "aid2e.schedulers.base": "Abstract scheduler contract and scheduler extension points.",
    "aid2e.optimizers.ax.optimizer": "Ax optimizer runtime implementation.",
    "aid2e.optimizers.pymoo.optimizer": "Pymoo optimizer runtime implementation.",
    "aid2e.utilities.configurations": "Core configuration models, loaders, and composition helpers.",
    "aid2e.utilities.workflows.execution_engine": "Workflow execution engine and orchestration logic.",
}

SYMBOL_MODULES = {
    "load_config": "aid2e.utilities.configurations.full_config",
    "FullConfig": "aid2e.utilities.configurations.full_config",
    "DesignConfig": "aid2e.utilities.configurations.design_config",
    "ProblemConfiguration": "aid2e.utilities.configurations.problem_config",
    "OptimizationConfiguration": "aid2e.utilities.configurations.optimization_config",
}

SEARCH_MODULES = tuple(dict.fromkeys(list(MODULES) + list(SYMBOL_MODULES.values())))


def get_package_overview() -> str:
    """Build a markdown overview of the AID2E package.

    Returns:
        Formatted package overview text.
    """
    return f"""# AID2E Framework

AI assisted Detector Design for EIC.

- Version: {__MAIN_VERSION__}
- CLI: `aid2e --help`
- MCP server: `aid2e mcp`
- Install MCP extras: `pip install 'aid2e[mcp]'`

Docs: https://aid2e.github.io/AID2E-framework
Repo: https://github.com/aid2e/AID2E-framework
"""


def get_quickstart() -> str:
    """Build the minimal install-to-connect quickstart.

    Returns:
        Formatted quickstart instructions.
    """
    return """# AID2E Quickstart

1. Install MCP extras:

```bash
pip install 'aid2e[mcp]'
```

2. Configure your MCP client to launch:

```bash
aid2e mcp
```

3. Ask architecture and implementation questions in Copilot or Continue.
"""


def load_module(module_name: str):
    """Import a module and return None when unavailable.

    Args:
        module_name: Import path.

    Returns:
        Imported module object or None.
    """
    try:
        return importlib.import_module(module_name)
    except Exception:
        return None


def safe_signature(obj) -> str:
    """Return a best-effort callable signature string.

    Args:
        obj: Object to inspect.

    Returns:
        Callable signature or fallback empty signature.
    """
    try:
        return str(inspect.signature(obj))
    except Exception:
        return "()"


def doc_summary(obj) -> str:
    """Return the first line of a docstring.

    Args:
        obj: Object to inspect.

    Returns:
        First docstring line or fallback text.
    """
    doc = inspect.getdoc(obj) or ""
    if not doc:
        return "No docstring available."
    return doc.strip().splitlines()[0]


def iter_public_members(module) -> Iterable[tuple[str, object]]:
    """Yield public classes and functions from a module.

    Args:
        module: Imported module object.

    Yields:
        Public symbol name and object pair.
    """
    for name, obj in inspect.getmembers(module):
        if name.startswith("_"):
            continue
        if inspect.isclass(obj) or inspect.isfunction(obj):
            yield name, obj


def resolve_symbol(symbol: str) -> tuple[str | None, object | None]:
    """Resolve a public symbol using preferred module maps.

    Args:
        symbol: Public function or class name.

    Returns:
        Tuple of module name and object when found, otherwise (None, None).
    """
    module_name = SYMBOL_MODULES.get(symbol)
    if module_name:
        module = load_module(module_name)
        if module is not None and hasattr(module, symbol):
            return module_name, getattr(module, symbol)

    for candidate in SEARCH_MODULES:
        module = load_module(candidate)
        if module is None or not hasattr(module, symbol):
            continue
        return candidate, getattr(module, symbol)

    return None, None
