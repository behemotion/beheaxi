"""Introspect verb signatures into describe --json manifest entries.

Arg entries are computed once, at registration (`BeheaxiApp.command`), so a signature the
manifest cannot express truthfully fails at import time instead of shipping a manifest that
lies to beherouter.
"""
from __future__ import annotations

import importlib
import inspect
import types
import typing
from collections.abc import Callable
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, get_args, get_origin

from typer.models import ArgumentInfo, ParameterInfo

if TYPE_CHECKING:
    from .app import BeheaxiApp

_SCALARS: dict[Any, str] = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    Path: "string",
}
_ARRAYS = (list, tuple, set, frozenset)


def _context_classes() -> tuple[type, ...]:
    """Every importable Click `Context` base (vendored in Typer >= 0.26, and/or standalone).

    Typer injects a parameter annotated with one of these; it is not a CLI argument.
    `typer.Context` subclasses the vendored one, so issubclass() covers it too.
    """
    found: list[type] = []
    for module in ("typer._click.core", "click.core"):
        try:
            cls = getattr(importlib.import_module(module), "Context", None)
        except ModuleNotFoundError:  # pragma: no cover - depends on packaging
            continue
        if isinstance(cls, type) and cls not in found:
            found.append(cls)
    return tuple(found)


_CONTEXTS = _context_classes()


def _is_context(hint: Any) -> bool:
    annotation, _ = _unwrap(hint)
    return isinstance(annotation, type) and issubclass(annotation, _CONTEXTS)


def _unwrap(annotation: Any) -> tuple[Any, ParameterInfo | None]:
    """Strip Annotated[...] (keeping typer Argument/Option metadata) and Optional[...]."""
    info: ParameterInfo | None = None
    if get_origin(annotation) is typing.Annotated:
        base, *meta = get_args(annotation)
        info = next((m for m in meta if isinstance(m, ParameterInfo)), None)
        annotation = base
    if get_origin(annotation) in (typing.Union, types.UnionType):
        members = [a for a in get_args(annotation) if a is not type(None)]
        if len(members) == 1:
            annotation = members[0]
    return annotation, info


def _type_of(annotation: Any) -> tuple[str, list[str] | None]:
    if annotation in _ARRAYS or get_origin(annotation) in _ARRAYS:
        return "array", None
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        return "string", [str(e.value) for e in annotation]
    return _SCALARS.get(annotation, "string"), None


def _option_name(param_name: str, decls: tuple[str, ...]) -> str:
    """The first `--long` declaration (`--force/--no-force` -> `--force`). With only short
    declarations (`-n`), the first one verbatim, since Typer registers no `--param-name`
    then. Typer's default `--param-name` only when nothing is declared."""
    names = [d.split("/")[0].strip() for d in decls]
    for first in names:
        if first.startswith("--"):
            return first
    if names:
        return names[0]
    return f"--{param_name.replace('_', '-')}"


def arg_entry(param: inspect.Parameter, hint: Any) -> dict[str, Any]:
    """One manifest arg entry. Raises ValueError for shapes the manifest cannot express."""
    annotation, info = _unwrap(hint)
    default: Any = param.default
    decls: tuple[str, ...] = ()
    if isinstance(default, ParameterInfo):  # old style: `x: int = typer.Option(5, "--x")`
        info, default = default, default.default
        decls = tuple(getattr(info, "param_decls", None) or ())
    elif info is not None:
        decls = tuple(getattr(info, "param_decls", None) or ())
        # Annotated style: Typer reads a str first argument as a declaration, so
        # Annotated[int, typer.Option("--limit", "-n")] stores "--limit" as `default`.
        if isinstance(info.default, str):
            decls = (info.default, *decls)
    required = default is inspect.Parameter.empty or default is ...
    if getattr(info, "default_factory", None) is not None:  # Option(default_factory=...)
        required = False
    positional = isinstance(info, ArgumentInfo) or (info is None and required)
    if positional != required:
        shape = "a required option" if required else "an optional positional argument"
        raise ValueError(
            f"parameter {param.name!r} is {shape}: the describe manifest marks required args "
            "as positional and optional args as --flags (beherouter builds argv that way), "
            "so make it a plain positional with no default, or an option with a default"
        )
    name = param.name if positional else _option_name(param.name, decls)
    typ, enum = _type_of(annotation)
    entry: dict[str, Any] = {"name": name, "type": typ, "required": required}
    if enum is not None:
        entry["enum"] = enum
    return entry


def arg_entries(fn: Callable[..., Any]) -> list[dict[str, Any]]:
    """Manifest arg entries for a verb function, in signature order.

    A `ctx: typer.Context` parameter is injected by Typer, not passed on the command line,
    so it is not an arg.
    """
    try:
        # Resolves string annotations: under `from __future__ import annotations` (used
        # across the harness) every annotation is a str that _type_of cannot map.
        hints = typing.get_type_hints(fn, include_extras=True)
    except Exception as e:  # NameError/TypeError from unresolvable refs: re-raised
        raise ValueError(
            f"cannot resolve the annotations of verb function {fn.__name__!r}: {e}. "
            "Define referenced types before the verb."
        ) from e
    return [
        arg_entry(p, hints.get(p.name, p.annotation))
        for p in inspect.signature(fn).parameters.values()
        if p.name != "self" and not _is_context(hints.get(p.name, p.annotation))
    ]


def build_manifest(app: BeheaxiApp) -> dict[str, Any]:
    verbs = [
        {
            "name": v.name,
            "summary": v.summary,
            "args": v.args,
            "pinned": v.pinned,
            "mutating": v.mutating,
        }
        for v in app._verbs
    ]
    return {"tool": app.name, "version": app.version, "summary": app.summary, "verbs": verbs}
