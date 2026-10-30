"""Repository indexing for the AID2E MCP server.

This module builds a semantic index of the AID2E Python source tree and any
available example/configuration trees so MCP planner and coder tools can
dynamically answer architecture-aware questions across both editable git
checkouts and installed PyPI wheels.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from .models import ComponentBlueprint, RepositoryInfo, SearchResult
from .parser import RepositoryParser

_SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".venv",
    "venv",
    "node_modules",
    "build",
    "dist",
    ".eggs",
}


class RepositoryIndex:
    """Build and query a semantic index for the AID2E source tree.

    Args:
        root: Repository root or installed `aid2e` package directory.
        package_root: Optional explicit `aid2e` package directory.
        examples_root: Optional explicit examples directory.
    """

    def __init__(
        self,
        root: Path | None = None,
        package_root: Path | None = None,
        examples_root: Path | None = None,
    ) -> None:
        """Initialize a repository index that adapts to source or wheel layouts."""
        default_pkg_dir = Path(__file__).resolve().parent.parent

        if root is not None:
            resolved_root = root.resolve()
            if (resolved_root / "src" / "aid2e").is_dir():
                self.root = resolved_root
                self.package_root = package_root or (resolved_root / "src" / "aid2e")
            elif (resolved_root / "__init__.py").is_file() and resolved_root.name == "aid2e":
                self.package_root = package_root or resolved_root
                if (
                    len(resolved_root.parents) >= 2
                    and resolved_root.parent.name == "src"
                    and (resolved_root.parents[1] / "pyproject.toml").is_file()
                ):
                    self.root = resolved_root.parents[1]
                else:
                    self.root = resolved_root
            else:
                self.root = resolved_root
                self.package_root = package_root or default_pkg_dir
        else:
            if (
                len(default_pkg_dir.parents) >= 2
                and default_pkg_dir.parent.name == "src"
                and (default_pkg_dir.parents[1] / "src" / "aid2e").is_dir()
            ):
                self.root = default_pkg_dir.parents[1]
                self.package_root = package_root or default_pkg_dir
            else:
                self.root = default_pkg_dir
                self.package_root = package_root or default_pkg_dir

        self.package_examples = self._resolve_examples_root(examples_root)
        self.info = RepositoryInfo(root=self.root)
        self._built = False

    def _resolve_examples_root(self, explicit: Path | None = None) -> Path:
        """Locate the examples directory across checkout, env var, or wheel."""
        if explicit is not None and explicit.exists():
            return explicit.resolve()

        env_examples = os.environ.get("AID2E_EXAMPLES_DIR")
        if env_examples:
            candidate = Path(env_examples).expanduser().resolve()
            if candidate.is_dir():
                return candidate

        candidates = [
            self.root / "examples",
            self.package_root / "examples",
            self.package_root.parent.parent / "examples",
        ]
        for candidate in candidates:
            if candidate.is_dir():
                return candidate.resolve()

        return (self.root / "examples").resolve()

    def ensure_built(self) -> None:
        """Build the index once if it has not been built yet."""
        if not self._built:
            self.build()

    def refresh(self) -> RepositoryInfo:
        """Force a rebuild of the semantic index."""
        self._built = False
        return self.build()

    def build(self) -> RepositoryInfo:
        """Build a fresh semantic index from Python files in package and examples.

        Returns:
            Newly built repository information.
        """
        self.info = RepositoryInfo(root=self.root)
        _source_paths = (
            sorted(self.package_root.rglob("*.py"))
            if self.package_root.exists()
            else []
        )
        _example_paths = (
            sorted(self.package_examples.rglob("*.py"))
            if self.package_examples.exists()
            else []
        )

        paths_ = {"source": _source_paths, "examples": _example_paths}

        for key, path_list in paths_.items():
            for path in path_list:
                if any(part.startswith(".") or part in _SKIP_DIRS for part in path.parts):
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
                    # Prefer aid2e.* over examples.* if short symbol names collide
                    if class_name not in self.info.symbols or key == "source":
                        self.info.symbols[class_name] = qualname
                    for base in class_info.bases:
                        self.info.inheritance.setdefault(base, []).append(qualname)

                for function_name, function_info in module.functions.items():
                    qualname = f"{module_name}.{function_name}"
                    function_info.qualname = qualname
                    self.info.functions[qualname] = function_info
                    if function_name not in self.info.symbols or key == "source":
                        self.info.symbols[function_name] = qualname

                for class_name, class_info in module.classes.items():
                    for method_name, method_info in class_info.methods.items():
                        method_qualname = f"{module_name}.{class_name}.{method_name}"
                        method_info.qualname = method_qualname
                        self.info.functions[method_qualname] = method_info
                        short_method = f"{class_name}.{method_name}"
                        self.info.symbols[short_method] = method_qualname
                        if method_name not in self.info.symbols:
                            self.info.symbols[method_name] = method_qualname

        self._built = True
        return self.info

    def discover_subsystems(self) -> dict[str, Path]:
        """Dynamically discover all subsystems and subpackages inside `aid2e`."""
        subsystems: dict[str, Path] = {}
        if self.package_root.is_dir():
            for child in sorted(self.package_root.iterdir()):
                if child.is_dir() and not child.name.startswith(("_", ".")):
                    subsystems[child.name.lower()] = child
                    for subchild in sorted(child.iterdir()):
                        if subchild.is_dir() and not subchild.name.startswith(("_", ".")):
                            subsystems[subchild.name.lower()] = subchild
                            subsystems[f"{child.name.lower()}/{subchild.name.lower()}"] = subchild
                            subsystems[f"{child.name.lower()}.{subchild.name.lower()}"] = subchild

        # Convenient aliases for well-known concepts
        workflows_dir = self.package_root / "utilities" / "workflows"
        if workflows_dir.is_dir():
            subsystems.setdefault("stacks", workflows_dir)
            subsystems.setdefault("geometry", workflows_dir)
            subsystems.setdefault("workflows", workflows_dir)

        configs_dir = self.package_root / "utilities" / "configurations"
        if configs_dir.is_dir():
            subsystems.setdefault("configurations", configs_dir)
            subsystems.setdefault("configs", configs_dir)

        if self.package_examples.is_dir():
            subsystems["examples"] = self.package_examples

        return subsystems

    def resolve_subsystem_path(self, subsystem: str) -> Path | None:
        """Resolve a subsystem name or relative subpath to a directory Path."""
        raw = (subsystem or "").strip().strip("/").replace("\\", "/")
        if not raw or raw in {".", "all", "aid2e"}:
            return self.package_root

        subsystems = self.discover_subsystems()
        low = raw.lower()
        if low in subsystems:
            return subsystems[low]
        if low.rstrip("s") in subsystems:
            return subsystems[low.rstrip("s")]
        if (low + "s") in subsystems:
            return subsystems[low + "s"]

        # Try direct relative directory under package_root or root
        for base in (self.package_root, self.root):
            candidate = (base / raw).resolve()
            try:
                candidate.relative_to(base.resolve())
                if candidate.is_dir():
                    return candidate
            except ValueError:
                pass

        return None

    def _resolve_subsystem_path(self, subsystem: str) -> Path:
        """Backward-compatible helper that always returns a Path object."""
        resolved = self.resolve_subsystem_path(subsystem)
        if resolved is not None:
            return resolved
        return self.package_root / "__nonexistent_subsystem__" / subsystem.strip()

    def search(self, query: str, limit: int = 20) -> list[SearchResult]:
        """Search indexed symbols using multi-token and substring scoring.

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
            score = self._score_text(needle, module_name, module.docstring)
            if score > 0:
                results.append(
                    SearchResult(
                        symbol=module_name,
                        module=module_name,
                        kind="module",
                        score=score,
                        summary=(
                            module.docstring.splitlines()[0]
                            if module.docstring
                            else "Module without docstring."
                        ),
                    )
                )

        for qualname, cls in self.info.classes.items():
            meta_text = " ".join(
                [cls.docstring, " ".join(cls.bases), " ".join(cls.attributes)]
            )
            score = self._score_text(needle, qualname, meta_text)
            if score > 0:
                results.append(
                    SearchResult(
                        symbol=qualname,
                        module=qualname.rsplit(".", 1)[0],
                        kind="class",
                        score=score,
                        summary=(
                            cls.docstring.splitlines()[0]
                            if cls.docstring
                            else f"Class({', '.join(cls.bases)})"
                        ),
                    )
                )

        for qualname, fn in self.info.functions.items():
            meta_text = " ".join(
                [
                    fn.signature,
                    fn.docstring,
                    " ".join(fn.calls),
                    " ".join(fn.raises),
                ]
            )
            score = self._score_text(needle, qualname, meta_text)
            if score > 0:
                results.append(
                    SearchResult(
                        symbol=qualname,
                        module=qualname.rsplit(".", 1)[0],
                        kind="function",
                        score=score,
                        summary=(
                            fn.docstring.splitlines()[0]
                            if fn.docstring
                            else f"{fn.name}{fn.signature}"
                        ),
                    )
                )

        results.sort(key=lambda item: (item.score, item.kind == "class"), reverse=True)
        return results[:limit]

    def resolve_indexed_symbol(self, symbol: str):
        """Resolve a short, partial, or fully qualified symbol name in the index."""
        self.ensure_built()
        cleaned = symbol.strip().strip("`").strip("'").strip('"')
        if not cleaned:
            return None, None

        target = self.info.symbols.get(cleaned, cleaned)
        obj = self.info.classes.get(target) or self.info.functions.get(target)
        if obj is not None:
            return target, obj

        # Case-insensitive or suffix lookup
        low = cleaned.lower()
        for qualname, cls in self.info.classes.items():
            if qualname.lower() == low or cls.name.lower() == low or qualname.lower().endswith("." + low):
                return qualname, cls
        for qualname, fn in self.info.functions.items():
            if qualname.lower() == low or fn.name.lower() == low or qualname.lower().endswith("." + low):
                return qualname, fn

        return None, None

    def get_symbol_source(self, symbol: str) -> str | None:
        """Return source text (with file and line metadata) for an indexed symbol.

        Args:
            symbol: Symbol name or qualified symbol name.

        Returns:
            Source snippet for the symbol, or None when unavailable.
        """
        qualname, obj = self.resolve_indexed_symbol(symbol)
        if obj is None or obj.location is None:
            return None

        lines = obj.location.path.read_text(encoding="utf-8", errors="replace").splitlines()
        start = max(1, obj.location.lineno)
        end = max(start, obj.location.end_lineno)
        snippet = "\n".join(lines[start - 1 : end])
        rel_path = self.display_path(obj.location.path)
        return f"# {qualname} ({rel_path}:{start}-{end})\n{snippet}"

    def find_subclasses(self, base_class: str) -> list[str]:
        """Find all indexed classes that inherit (directly or by short name) from `base_class`."""
        self.ensure_built()
        needle = base_class.strip()
        short_needle = needle.rsplit(".", 1)[-1]
        matches: list[str] = []
        for qualname, cls in self.info.classes.items():
            for base in cls.bases:
                base_short = base.rsplit(".", 1)[-1]
                if base == needle or base_short == short_needle or needle.lower() in base.lower():
                    matches.append(qualname)
                    break
        return sorted(dict.fromkeys(matches))

    def grep(
        self,
        query: str,
        scope: str = "all",
        file_pattern: str = "*",
        is_regex: bool = False,
        max_results: int = 50,
    ) -> list[str]:
        """Search reference source and/or examples for text or regex matches."""
        needle = (query or "").strip()
        if not needle:
            return []

        roots: list[Path] = []
        scope_low = (scope or "all").lower()
        if scope_low in {"all", "source", "framework", "aid2e"} and self.package_root.exists():
            roots.append(self.package_root)
        if scope_low in {"all", "examples", "example"} and self.package_examples.exists():
            if self.package_examples not in roots:
                roots.append(self.package_examples)

        if is_regex:
            try:
                pattern_re = re.compile(needle, re.IGNORECASE)
            except re.error as exc:
                return [f"Invalid regex '{needle}': {exc}"]
        else:
            pattern_re = re.compile(re.escape(needle), re.IGNORECASE)

        hits: list[str] = []
        seen_files: set[Path] = set()
        for root_dir in roots:
            for path in sorted(root_dir.rglob(file_pattern)):
                if not path.is_file() or path in seen_files:
                    continue
                if any(part.startswith(".") or part in _SKIP_DIRS for part in path.parts):
                    continue
                if path.suffix.lower() in {".pyc", ".pyo", ".so", ".png", ".jpg", ".jpeg", ".gif", ".pdf"}:
                    continue
                seen_files.add(path)
                try:
                    text = path.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    continue
                rel = self.display_path(path)
                for lineno, line in enumerate(text.splitlines(), start=1):
                    if pattern_re.search(line):
                        hits.append(f"{rel}:{lineno}: {line.strip()[:200]}")
                        if len(hits) >= max_results:
                            return hits
        return hits

    def build_component_blueprint(
        self,
        subsystem: str,
        reference_engine: str = "",
    ) -> ComponentBlueprint:
        """Build a component blueprint for any subsystem in AID2E.

        Args:
            subsystem: Component family such as schedulers, optimizers, workflows, configurations.
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
                if "base" in item.name.lower()
            ]
        )
        if base_candidates:
            blueprint.abstract_base = self.display_path(base_candidates[0])

        impl_dirs = sorted(
            [
                item
                for item in target.iterdir()
                if item.is_dir() and not item.name.startswith(("_", "."))
            ]
        )
        if reference_engine:
            impl_dirs = sorted(
                impl_dirs,
                key=lambda item: item.name.lower() != reference_engine.lower(),
            )
        blueprint.implementations = [self.display_path(item) for item in impl_dirs]

        # Collect registration files both inside the subsystem and in utilities/configurations
        reg_files: list[Path] = []
        for path in sorted(target.rglob("*.py")):
            low = path.name.lower()
            if "registry" in low or "register" in low or low == "__init__.py":
                reg_files.append(path)

        configs_pkg = self.package_root / "utilities" / "configurations"
        singular = subsystem.strip().lower().rstrip("s")
        if configs_pkg.is_dir():
            for path in sorted(configs_pkg.glob("*.py")):
                low = path.name.lower()
                if singular in low or "registry" in low or "full_config" in low:
                    if path not in reg_files:
                        reg_files.append(path)

        blueprint.registration_files = [ Path(self.display_path(p)) for p in reg_files ]

        # Collect related example and configuration YAML/JSON/params files
        config_files: list[Path] = []
        search_dirs = [self.package_examples, self.root / "configurations"]
        for sdir in search_dirs:
            if not sdir.is_dir():
                continue
            for path in sorted(sdir.rglob("*")):
                if not path.is_file():
                    continue
                if path.suffix.lower() not in {".yml", ".yaml", ".json", ".config", ".params", ".py"}:
                    continue
                rel_low = str(path.relative_to(sdir)).lower()
                if (
                    singular in rel_low
                    or subsystem.lower() in rel_low
                    or (reference_engine and reference_engine.lower() in rel_low)
                ):
                    config_files.append(path)

        blueprint.configuration_files = [
            Path(self.display_path(p)) for p in config_files[:20]
        ]

        return blueprint

    def display_path(self, path: Path) -> str:
        """Format a path relative to `self.root` or `self.package_root`."""
        resolved = path.resolve()
        for base in (self.root.resolve(), self.package_root.resolve(), self.package_examples.resolve()):
            try:
                rel = resolved.relative_to(base)
                if base == self.package_examples.resolve() and not str(rel).startswith("examples"):
                    return f"examples/{rel.as_posix()}"
                return rel.as_posix()
            except ValueError:
                continue
        return resolved.as_posix()

    def resolve_reference_file(self, raw_path: str) -> Path | None:
        """Resolve a user/model file path against `src/aid2e`, `examples`, or repo root."""
        cleaned = (raw_path or "").strip().strip('"').strip("'").replace("\\", "/")
        if not cleaned:
            return None

        # Strip leading slashes if the model accidentally passed "/src/aid2e/..."
        incoming = Path(cleaned)
        if incoming.is_absolute():
            resolved = incoming.resolve()
            for allowed in (self.package_root.resolve(), self.package_examples.resolve(), self.root.resolve()):
                if allowed.exists():
                    try:
                        resolved.relative_to(allowed)
                        if resolved.is_file():
                            return resolved
                    except ValueError:
                        continue

        rel_candidates = [cleaned]
        for prefix in ("src/aid2e/", "aid2e/", "examples/"):
            if cleaned.startswith(prefix):
                rel_candidates.append(cleaned[len(prefix) :])

        search_roots = [
            self.root.resolve(),
            self.package_root.resolve(),
            self.package_examples.resolve(),
        ]
        for base in search_roots:
            if not base.exists():
                continue
            for rel in rel_candidates:
                candidate = (base / rel).resolve()
                try:
                    candidate.relative_to(base)
                except ValueError:
                    continue
                if candidate.is_file():
                    return candidate

        return None

    def _path_to_module(self, path: Path) -> str:
        """Convert a source path to a Python module path (`aid2e.*`)."""
        try:
            relative = path.resolve().relative_to(self.package_root.resolve())
            parts = ["aid2e"] + list(relative.parts)
        except ValueError:
            relative = path.resolve().relative_to(self.root.resolve())
            parts = list(relative.parts)
            if parts and parts[0] == "src":
                parts = parts[1:]

        parts[-1] = parts[-1].replace(".py", "")
        if parts[-1] == "__init__" and len(parts) > 1:
            parts = parts[:-1]
        return ".".join(parts)

    def _path_to_example_module(self, path: Path) -> str:
        """Convert an example source path to a dotted example path (`examples.*`)."""
        relative = path.resolve().relative_to(self.package_examples.resolve())
        parts = ["examples"] + list(relative.parts)
        parts[-1] = parts[-1].replace(".py", "")
        if parts[-1] == "__init__" and len(parts) > 1:
            parts = parts[:-1]
        return ".".join(parts)

    def _score_text(self, needle: str, primary: str, secondary: str = "") -> float:
        """Score needle presence against primary symbol name and secondary metadata."""
        prim_low = primary.lower()
        sec_low = secondary.lower()
        short_name = prim_low.rsplit(".", 1)[-1]
        haystack = f"{prim_low} {sec_low}"

        if needle == short_name or needle == prim_low:
            return 5.0
        if short_name.startswith(needle) or prim_low.endswith("." + needle):
            return 4.0
        if needle in prim_low:
            return 3.0
        if needle in haystack:
            return 1.5 + (len(needle) / max(1, len(haystack)))

        # Multi-token query matching (e.g., "slurm scheduler config")
        tokens = [tok for tok in re.split(r"[\s_./-]+", needle) if len(tok) >= 2]
        if len(tokens) > 1:
            matched_prim = sum(1 for tok in tokens if tok in prim_low)
            matched_all = sum(1 for tok in tokens if tok in haystack)
            if matched_all == len(tokens):
                return 2.5 + 0.3 * matched_prim
            if matched_all >= max(1, len(tokens) - 1) and matched_prim >= 1:
                return 1.0 + (matched_all / len(tokens))

        return 0.0
