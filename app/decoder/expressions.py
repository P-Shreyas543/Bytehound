"""Safe arithmetic expressions over signals (Derived sheet, math channels).

``compile_expression("[CellVoltage] * [CellCurrent]")`` parses the text once
and accepts only what a formula needs: numbers, ``[signal name]``
references, ``+ - * / ** %``, unary minus, parentheses and a short list of
functions (``abs min max sqrt exp log log10 sin cos tan``). No names,
attributes, subscripts or other calls exist in the language, so an
expression cannot reach Python itself (the old math-channel ``eval`` with
numpy in its namespace could, through attribute access).

The same compiled expression evaluates scalars (live decoding) and numpy
arrays (Analysis Suite): operators are generic and the functions are numpy
ufuncs.
"""

from __future__ import annotations

import ast
import operator
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping

import numpy as np

_REF = re.compile(r"\[([^\[\]]+)\]")

_BINOPS: Dict[type, Callable[[Any, Any], Any]] = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.Pow: operator.pow, ast.Mod: operator.mod,
}
_UNARY: Dict[type, Callable[[Any], Any]] = {ast.USub: operator.neg, ast.UAdd: operator.pos}
_FUNCS: Dict[str, Callable[..., Any]] = {
    "abs": np.abs, "sqrt": np.sqrt, "exp": np.exp, "log": np.log, "log10": np.log10,
    "sin": np.sin, "cos": np.cos, "tan": np.tan,
    "min": lambda *a: np.minimum.reduce(np.broadcast_arrays(*a)) if len(a) > 1 else a[0],
    "max": lambda *a: np.maximum.reduce(np.broadcast_arrays(*a)) if len(a) > 1 else a[0],
}


class ExpressionError(ValueError):
    """The expression is not a valid formula (message says what is wrong)."""


@dataclass(frozen=True)
class Expression:
    text: str
    refs: List[str] = field(default_factory=list)      # signal names, in order of first use
    _tree: Any = None

    def evaluate(self, values: Mapping[str, Any]) -> Any:
        """Evaluate with ``values[name]`` for every reference (scalars or
        numpy arrays). Division by zero gives inf / nan, never an exception."""
        with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
            return _eval(self._tree, values, self.refs)


def compile_expression(text: str) -> Expression:
    refs: List[str] = []

    def placeholder(m: "re.Match[str]") -> str:
        name = m.group(1).strip()
        if not name:
            raise ExpressionError("empty [ ] reference")
        if name not in refs:
            refs.append(name)
        return f"__ref{refs.index(name)}"

    if "__ref" in str(text or ""):
        raise ExpressionError("'__ref' is reserved — write signals as [Signal Name]")
    source = _REF.sub(placeholder, str(text or "")).strip()
    if not source:
        raise ExpressionError("the expression is empty")
    if "[" in source or "]" in source:
        raise ExpressionError("unbalanced [ ] in the expression")
    try:
        tree = ast.parse(source, mode="eval").body
    except SyntaxError as exc:
        raise ExpressionError(f"not a valid formula ({exc.msg})") from None
    _check(tree, len(refs))
    return Expression(str(text), refs, tree)


def _check(node: ast.AST, n_refs: int) -> None:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise ExpressionError(f"only numbers are allowed as constants, not {node.value!r}")
    elif isinstance(node, ast.Name):
        m = re.fullmatch(r"__ref(\d+)", node.id)
        if m is None or int(m.group(1)) >= n_refs:
            raise ExpressionError(f"unknown name {node.id!r} — write signals as [Signal Name]")
    elif isinstance(node, ast.BinOp):
        if type(node.op) not in _BINOPS:
            raise ExpressionError("only + - * / ** % are allowed")
        _check(node.left, n_refs)
        _check(node.right, n_refs)
    elif isinstance(node, ast.UnaryOp):
        if type(node.op) not in _UNARY:
            raise ExpressionError("only unary - and + are allowed")
        _check(node.operand, n_refs)
    elif isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in _FUNCS or node.keywords:
            raise ExpressionError(f"allowed functions: {', '.join(sorted(_FUNCS))}")
        if not node.args:
            raise ExpressionError(f"{node.func.id}() needs an argument")
        for arg in node.args:
            _check(arg, n_refs)
    else:
        raise ExpressionError(f"{type(node).__name__} is not allowed in a formula")


def _eval(node: ast.AST, values: Mapping[str, Any], refs: List[str]) -> Any:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        return values[refs[int(node.id[5:])]]
    if isinstance(node, ast.BinOp):
        left, right = _eval(node.left, values, refs), _eval(node.right, values, refs)
        if isinstance(node.op, ast.Div) and np.isscalar(right) and right == 0:
            return float("nan") if np.isscalar(left) and left == 0 else float("inf") * np.sign(left)
        return _BINOPS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp):
        return _UNARY[type(node.op)](_eval(node.operand, values, refs))
    if isinstance(node, ast.Call):
        return _FUNCS[node.func.id](*(_eval(a, values, refs) for a in node.args))
    raise ExpressionError(f"{type(node).__name__} is not allowed")  # pragma: no cover - rejected at compile
