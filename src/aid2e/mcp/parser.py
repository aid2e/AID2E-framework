"""AST parser for the AID2E MCP repository index.

The parser walks Python modules and extracts semantic data used by planner and
coder MCP tools.
"""

from __future__ import annotations

import ast
from pathlib import Path

from .models import ClassInfo, FunctionInfo, ModuleInfo, SourceLocation


class FunctionAnalyzer(ast.NodeVisitor):
    """Collect semantic information from function bodies.

    Notes:
        This visitor is intentionally conservative and best-effort. Any AST
        unparsing error is ignored so indexing can continue.
    """

    def __init__(self) -> None:
        """Initialize mutable analysis sets."""
        self.instantiates: set[str] = set()
        self.attributes: set[str] = set()
        self.imported_symbols: set[str] = set()
        self.literals: set[str] = set()
        self.calls: set[str] = set()
        self.reads: set[str] = set()
        self.writes: set[str] = set()
        self.raises: set[str] = set()
        self.creates: set[str] = set()
        self.returns: str | None = None

    def visit_Call(self, node: ast.Call) -> None:
        """Record function calls and simple constructor-like invocations.

        Args:
            node: Call expression AST node.
        """
        try:
            name = ast.unparse(node.func)
            self.calls.add(name)
            if isinstance(node.func, ast.Name):
                self.instantiates.add(node.func.id)
        except Exception:
            pass
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        """Record attribute access expressions.

        Args:
            node: Attribute AST node.
        """
        try:
            self.attributes.add(ast.unparse(node))
        except Exception:
            pass
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        """Record literal constants.

        Args:
            node: Constant AST node.
        """
        value = node.value
        if isinstance(value, (str, int, float, bool)):
            self.literals.add(repr(value))
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        """Record variable reads and writes.

        Args:
            node: Name AST node.
        """
        if isinstance(node.ctx, ast.Load):
            self.reads.add(node.id)
        elif isinstance(node.ctx, ast.Store):
            self.writes.add(node.id)
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        """Record imported symbols encountered in a function body.

        Args:
            node: Import AST node.
        """
        for alias in node.names:
            self.imported_symbols.add(alias.asname or alias.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """Record from-import symbols encountered in a function body.

        Args:
            node: ImportFrom AST node.
        """
        for alias in node.names:
            self.imported_symbols.add(alias.asname or alias.name)
        self.generic_visit(node)

    def visit_Raise(self, node: ast.Raise) -> None:
        """Record raised expressions.

        Args:
            node: Raise AST node.
        """
        if node.exc is not None:
            try:
                self.raises.add(ast.unparse(node.exc))
            except Exception:
                pass
        self.generic_visit(node)

    def visit_With(self, node: ast.With) -> None:
        """Record resources created through context managers.

        Args:
            node: With AST node.
        """
        for item in node.items:
            if item.optional_vars is not None:
                try:
                    self.creates.add(ast.unparse(item.optional_vars))
                except Exception:
                    pass
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Capture explicit return type annotations.

        Args:
            node: FunctionDef AST node.
        """
        if node.returns:
            try:
                self.returns = ast.unparse(node.returns)
            except Exception:
                pass
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Delegate async function annotation handling to function handler.

        Args:
            node: AsyncFunctionDef AST node.
        """
        self.visit_FunctionDef(node)


class RepositoryParser(ast.NodeVisitor):
    """Parse one Python module into semantic objects."""

    def __init__(self, module_name: str, path: Path) -> None:
        """Initialize parser state.

        Args:
            module_name: Module import path.
            path: File path to parse.
        """
        self.module = ModuleInfo(name=module_name, path=path, docstring="")
        self.path = path
        self.current_class: ClassInfo | None = None

    @classmethod
    def parse_file(cls, path: Path, module_name: str) -> ModuleInfo:
        """Parse a Python source file into a ModuleInfo object.

        Args:
            path: Source file path.
            module_name: Module import path.

        Returns:
            Parsed module metadata.
        """
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        parser = cls(module_name, path)
        parser.module.docstring = ast.get_docstring(tree) or ""
        parser.visit(tree)
        return parser.module

    def visit_Import(self, node: ast.Import) -> None:
        """Record top-level imports.

        Args:
            node: Import AST node.
        """
        for alias in node.names:
            self.module.imports.append(alias.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """Record top-level from-imports.

        Args:
            node: ImportFrom AST node.
        """
        module = node.module or ""
        for alias in node.names:
            self.module.imports.append(f"{module}.{alias.name}")
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Record class declarations and nested methods.

        Args:
            node: ClassDef AST node.
        """
        bases = [self._expr_to_string(base) for base in node.bases]
        decorators = [self._expr_to_string(dec) for dec in node.decorator_list]

        cls = ClassInfo(
            name=node.name,
            qualname=node.name,
            docstring=ast.get_docstring(node) or "",
            bases=bases,
            decorators=decorators,
            location=SourceLocation(
                path=self.path,
                lineno=node.lineno,
                end_lineno=node.end_lineno or node.lineno,
            ),
        )

        self.module.classes[cls.name] = cls
        previous = self.current_class
        self.current_class = cls
        self.generic_visit(node)
        self.current_class = previous

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Handle top-level and class methods.

        Args:
            node: FunctionDef AST node.
        """
        self._handle_function(node, is_async=False)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Handle top-level and class async methods.

        Args:
            node: AsyncFunctionDef AST node.
        """
        self._handle_function(node, is_async=True)

    def _handle_function(self, node: ast.AST, is_async: bool) -> None:
        """Create a FunctionInfo object from an AST function node.

        Args:
            node: FunctionDef or AsyncFunctionDef AST node.
            is_async: Whether the function is asynchronous.
        """
        signature = self._build_signature(node)
        analyzer = FunctionAnalyzer()
        analyzer.visit(node)

        decorators = [self._expr_to_string(dec) for dec in node.decorator_list]

        function = FunctionInfo(
            name=node.name,
            qualname=node.name,
            signature=signature,
            docstring=ast.get_docstring(node) or "",
            decorators=decorators,
            is_async=is_async,
            is_method=self.current_class is not None,
            parent_class=self.current_class.name if self.current_class else None,
            location=SourceLocation(
                path=self.path,
                lineno=node.lineno,
                end_lineno=node.end_lineno or node.lineno,
            ),
            calls=analyzer.calls,
            reads=analyzer.reads,
            writes=analyzer.writes,
            raises=analyzer.raises,
            returns=analyzer.returns,
            instantiates=analyzer.instantiates,
            attributes=analyzer.attributes,
            imported_symbols=analyzer.imported_symbols,
            literals=analyzer.literals,
            creates=analyzer.creates,
        )

        if self.current_class:
            function.qualname = f"{self.current_class.name}.{node.name}"
            self.current_class.methods[node.name] = function
        else:
            self.module.functions[node.name] = function

        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        """Record class-level assignments as attributes.

        Args:
            node: Assign AST node.
        """
        if self.current_class:
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self.current_class.attributes.append(target.id)
        self.generic_visit(node)

    def _expr_to_string(self, expr: ast.AST) -> str:
        """Convert an AST expression into readable Python.

        Args:
            expr: AST expression node.

        Returns:
            String representation of the expression.
        """
        try:
            return ast.unparse(expr)
        except Exception:
            return "<unknown>"

    def _build_signature(self, node: ast.AST) -> str:
        """Build a lightweight function signature string.

        Args:
            node: FunctionDef or AsyncFunctionDef AST node.

        Returns:
            Signature string containing argument names.
        """
        args: list[str] = []
        for arg in node.args.args:
            args.append(arg.arg)
        if node.args.vararg:
            args.append("*" + node.args.vararg.arg)
        for arg in node.args.kwonlyargs:
            args.append(arg.arg)
        if node.args.kwarg:
            args.append("**" + node.args.kwarg.arg)
        return "(" + ", ".join(args) + ")"
