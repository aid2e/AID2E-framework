"""Datamodels used by the AID2E MCP repository index.

The repository index stores lightweight semantic data about modules, classes,
functions, and search results. These models are intentionally small and easy
for tools to serialize.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass(slots=True)
class SourceLocation:
    """Represent a location in source code.

    Args:
        path: File path for the source unit.
        lineno: Start line number.
        end_lineno: End line number.
    """

    path: Path
    lineno: int
    end_lineno: int


@dataclass(slots=True)
class FunctionInfo:
    """Store metadata for a Python function or method.

    Args:
        name: Local symbol name.
        qualname: Qualified symbol name.
        signature: Lightweight function signature string.
        docstring: Function docstring text.
        decorators: Applied decorators.
        location: Source location in the owning file.
        is_method: Whether this function is defined in a class.
        is_async: Whether this function is async.
        parent_class: Parent class name for methods.
        calls: Called symbols discovered in function body.
        reads: Variables read in function body.
        writes: Variables written in function body.
        raises: Raised exception expressions.
        returns: Return type annotation string when present.
        instantiates: Constructor-like calls made in body.
        attributes: Attribute access expressions.
        imported_symbols: Imported symbols referenced in body.
        literals: Literal constants seen in body.
        creates: Created resource hints discovered in body.
    """

    name: str
    qualname: str
    signature: str
    docstring: str
    decorators: list[str] = field(default_factory=list)
    location: Optional[SourceLocation] = None
    is_method: bool = False
    is_async: bool = False
    parent_class: Optional[str] = None
    calls: set[str] = field(default_factory=set)
    reads: set[str] = field(default_factory=set)
    writes: set[str] = field(default_factory=set)
    raises: set[str] = field(default_factory=set)
    returns: Optional[str] = None
    instantiates: set[str] = field(default_factory=set)
    attributes: set[str] = field(default_factory=set)
    imported_symbols: set[str] = field(default_factory=set)
    literals: set[str] = field(default_factory=set)
    creates: set[str] = field(default_factory=set)


@dataclass(slots=True)
class ClassInfo:
    """Store metadata for a Python class.

    Args:
        name: Local class name.
        qualname: Qualified class name.
        docstring: Class docstring text.
        bases: Base class expressions.
        decorators: Applied decorators.
        methods: Methods defined by the class.
        attributes: Class attributes assigned in class body.
        location: Source location in file.
    """

    name: str
    qualname: str
    docstring: str
    bases: list[str] = field(default_factory=list)
    decorators: list[str] = field(default_factory=list)
    methods: dict[str, FunctionInfo] = field(default_factory=dict)
    attributes: list[str] = field(default_factory=list)
    location: Optional[SourceLocation] = None


@dataclass(slots=True)
class ModuleInfo:
    """Store metadata for a Python module.

    Args:
        name: Module import name.
        path: File path for the module.
        docstring: Module-level docstring text.
        imports: Imported modules and symbols.
        classes: Top-level classes in module.
        functions: Top-level functions in module.
    """

    name: str
    path: Path
    docstring: str
    imports: list[str] = field(default_factory=list)
    classes: dict[str, ClassInfo] = field(default_factory=dict)
    functions: dict[str, FunctionInfo] = field(default_factory=dict)


@dataclass(slots=True)
class RepositoryInfo:
    """Store semantic state for an indexed repository.

    Args:
        root: Workspace root used for indexing.
        modules: Indexed modules by module name.
        classes: Indexed classes by qualified name.
        functions: Indexed functions by qualified name.
        inheritance: Base class to derived class relationships.
        symbols: Symbol name to fully-qualified owner.
    """

    root: Path
    modules: dict[str, ModuleInfo] = field(default_factory=dict)
    classes: dict[str, ClassInfo] = field(default_factory=dict)
    functions: dict[str, FunctionInfo] = field(default_factory=dict)
    inheritance: dict[str, list[str]] = field(default_factory=dict)
    symbols: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class SearchResult:
    """Represent a semantic search match.

    Args:
        symbol: Symbol that matched the query.
        module: Module containing the symbol.
        kind: Match kind such as class, function, or module.
        score: Relative score for sorting.
        summary: Short explanation of the match.
    """

    symbol: str
    module: str
    kind: str
    score: float
    summary: str


@dataclass(slots=True)
class ComponentBlueprint:
    """Represent a blueprint for extensible subsystem implementations.

    Args:
        name: Component family name.
        directory: Base package directory for the component.
        abstract_base: Resolved abstract base class file path, when found.
        implementations: Candidate implementation directories.
        registration_files: Registration files related to the component.
        configuration_files: Configuration files related to the component.
        description: Human-readable component summary.
    """

    name: str
    directory: Path
    abstract_base: Optional[str] = None
    implementations: list[str] = field(default_factory=list)
    registration_files: list[Path] = field(default_factory=list)
    configuration_files: list[Path] = field(default_factory=list)
    description: str = ""
