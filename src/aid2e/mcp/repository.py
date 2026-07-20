"""Repository indexing for the AID2E MCP server.

This module builds a semantic index of the AID2E Python source tree so MCP
planner and coder tools can answer architecture-aware questions.
"""

from __future__ import annotations

from pathlib import Path

from .models import ComponentBlueprint, RepositoryInfo, SearchResult
from .parser import RepositoryParser


class RepositoryIndex:
    """Build and query a semantic index for the AID2E source tree.

    Args:
        root: Workspace root path containing the src directory.
    """

    def __init__(self, root: Path) -> None:
        """Initialize an empty repository index.

        Args:
            root: Workspace root path.
        """
        self.root = root
        self.package_root = root / "src" / "aid2e"
        self.package_examples = root / "examples"
        self.info = RepositoryInfo(root=root)
        self._built = False

    def ensure_built(self) -> None:
        """Build the index once if it has not been built yet."""
        if not self._built:
            self.build()

    def build(self) -> RepositoryInfo:
        """Build a fresh semantic index from Python files.

        Returns:
            Newly built repository information.

        Notes:
            Files that cannot be parsed are skipped so indexing remains robust.
        """
        self.info = RepositoryInfo(root=self.root)
        _source_paths = list(self.package_root.rglob("*.py"))
        _example_paths = list(self.package_examples.rglob("*.py"))
        
        paths_ = {"source": _source_paths, "examples": _example_paths}

        for key in paths_:
            for path in paths_[key]:
                if any(part.startswith(".") for part in path.parts):
                    continue
                if key == "source":
                    module_name = self._path_to_module(path)
                else:
                    module_name = self._path_to_example_module(path)
                try:
                    module = RepositoryParser.parse_file(path, module_name)
                except Exception:
                    continue

                self.info.modules[module_name] = module

                for class_name, class_info in module.classes.items():
                    qualname = f"{module_name}.{class_name}"
                    class_info.qualname = qualname
                    self.info.classes[qualname] = class_info
                    self.info.symbols[class_name] = qualname
                    for base in class_info.bases:
                        self.info.inheritance.setdefault(base, []).append(qualname)

                for function_name, function_info in module.functions.items():
                    qualname = f"{module_name}.{function_name}"
                    function_info.qualname = qualname
                    self.info.functions[qualname] = function_info
                    self.info.symbols[function_name] = qualname

                for class_name, class_info in module.classes.items():
                    for method_name, method_info in class_info.methods.items():
                        method_qualname = f"{module_name}.{class_name}.{method_name}"
                        method_info.qualname = method_qualname
                        self.info.functions[method_qualname] = method_info
                        self.info.symbols[method_name] = method_qualname

        self._built = True
        return self.info

    def search(self, query: str, limit: int = 20) -> list[SearchResult]:
        """Search indexed symbols using a lightweight token match.

        Args:
            query: Search text.
            limit: Maximum number of returned hits.

        Returns:
            Ranked semantic search results.
        """
        self.ensure_built()
        needle = query.strip().lower()
        if not needle:
            return []

        results: list[SearchResult] = []

        for module_name, module in self.info.modules.items():
            score = self._score_text(needle, module_name + " " + module.docstring)
            if score > 0:
                results.append(
                    SearchResult(
                        symbol=module_name,
                        module=module_name,
                        kind="module",
                        score=score,
                        summary=(module.docstring or "Module without docstring."),
                    )
                )

        for qualname, cls in self.info.classes.items():
            text = " ".join([qualname, cls.docstring, " ".join(cls.bases), " ".join(cls.attributes)])
            score = self._score_text(needle, text)
            if score > 0:
                results.append(
                    SearchResult(
                        symbol=qualname,
                        module=qualname.rsplit(".", 1)[0],
                        kind="class",
                        score=score,
                        summary=(cls.docstring or "Class without docstring."),
                    )
                )

        for qualname, fn in self.info.functions.items():
            text = " ".join(
                [
                    qualname,
                    fn.signature,
                    fn.docstring,
                    " ".join(fn.calls),
                    " ".join(fn.raises),
                ]
            )
            score = self._score_text(needle, text)
            if score > 0:
                results.append(
                    SearchResult(
                        symbol=qualname,
                        module=qualname.rsplit(".", 1)[0],
                        kind="function",
                        score=score,
                        summary=(fn.docstring or "Function without docstring."),
                    )
                )

        results.sort(key=lambda item: item.score, reverse=True)
        return results[:limit]

    def get_symbol_source(self, symbol: str) -> str | None:
        """Return source text for an indexed symbol when possible.

        Args:
            symbol: Symbol name or qualified symbol name.

        Returns:
            Source snippet for the symbol, or None when unavailable.
        """
        self.ensure_built()

        target = symbol
        if symbol in self.info.symbols:
            target = self.info.symbols[symbol]

        obj = self.info.classes.get(target) or self.info.functions.get(target)
        if obj is None or obj.location is None:
            return None

        lines = obj.location.path.read_text(encoding="utf-8").splitlines()
        start = max(1, obj.location.lineno)
        end = max(start, obj.location.end_lineno)
        return "\n".join(lines[start - 1 : end])

    def build_component_blueprint(
        self,
        subsystem: str,
        reference_engine: str = "",
    ) -> ComponentBlueprint:
        """Build a component blueprint for scheduler/optimizer-like systems.

        Args:
            subsystem: Component family such as schedulers or optimizers.
            reference_engine: Optional implementation folder preference.

        Returns:
            Structured component blueprint information.
        """
        self.ensure_built()
        target = self._resolve_subsystem_path(subsystem)

        blueprint = ComponentBlueprint(
            name=subsystem,
            directory=target,
            description=f"AID2E {subsystem} component blueprint.",
        )

        if not target.exists():
            return blueprint

        base_candidates = sorted(
            [
                item
                for item in target.glob("*.py")
                if item.name.startswith("base") or item.name.endswith("_base.py")
            ]
        )
        if base_candidates:
            blueprint.abstract_base = str(base_candidates[0].relative_to(self.root))

        impl_dirs = sorted([item for item in target.iterdir() if item.is_dir() and not item.name.startswith("_")])
        if reference_engine:
            impl_dirs = sorted(impl_dirs, key=lambda item: item.name.lower() != reference_engine.lower())
        blueprint.implementations = [str(item.relative_to(self.root)) for item in impl_dirs]

        for path in target.rglob("*.py"):
            low = path.name.lower()
            if "registry" in low or "register" in low or low == "__init__.py":
                blueprint.registration_files.append(path.relative_to(self.root))

        for path in (self.root / "configurations").rglob("*.yml"):
            low = path.name.lower()
            if subsystem.rstrip("s") in low or subsystem in low:
                blueprint.configuration_files.append(path.relative_to(self.root))

        return blueprint

    def _path_to_module(self, path: Path) -> str:
        """Convert a source path to a Python module path.

        Args:
            path: Python source file path.

        Returns:
            Dotted module import path.
        """
        relative = path.relative_to(self.root / "src")
        parts = list(relative.parts)
        parts[-1] = parts[-1].replace(".py", "")
        if parts[-1] == "__init__":
            parts = parts[:-1]
        return ".".join(parts)

    def _path_to_example_module(self, path: Path) -> str:
        """Convert an example source path to a Python module path.

        Args:
            path: Example Python source file path.

        Returns:
            Dotted module import path.
        """
        relative = path.relative_to(self.package_examples)
        parts = list(relative.parts)
        parts[-1] = parts[-1].replace(".py", "")
        if parts[-1] == "__init__":
            parts = parts[:-1]
        return ".".join(parts)

    def _resolve_subsystem_path(self, subsystem: str) -> Path:
        """Resolve subsystem names to package directories.

        Args:
            subsystem: User-provided subsystem name.

        Returns:
            Best-matching directory path.
        """
        name = subsystem.strip().lower()
        mapping = {
            "schedulers": self.package_root / "schedulers",
            "optimizers": self.package_root / "optimizers",
            "stacks": self.package_root / "utilities" / "workflows",
            "geometry": self.package_root / "utilities" / "workflows",
            "examples": self.package_examples,
        }
        if name in mapping:
            return mapping[name]
        else:
            return "Unrecognized subsystem name. Valid options: " + ", ".join(mapping.keys())


    def _score_text(self, needle: str, haystack: str) -> float:
        """Score needle presence in haystack with simple heuristics.

        Args:
            needle: Lower-cased query text.
            haystack: Candidate text.

        Returns:
            Relative match score.
        """
        target = haystack.lower()
        if needle == target:
            return 4.0
        if target.startswith(needle):
            return 3.0
        if needle in target:
            return 1.0 + (len(needle) / max(1, len(target)))
        return 0.0
