"""Introspect a BeheaxiApp's command tree into the describe --json manifest."""
from __future__ import annotations

import inspect
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, get_origin

if TYPE_CHECKING:
    from .app import BeheaxiApp

_SCALARS: dict[type, str] = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    Path: "string",
}


def _type_of(annotation: Any) -> tuple[str, list[str] | None]:
    if get_origin(annotation) is list:
        return "array", None
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        return "string", [str(e.value) for e in annotation]
    return _SCALARS.get(annotation, "string"), None


def _arg_entry(param: inspect.Parameter) -> dict[str, Any]:
    required = param.default is inspect.Parameter.empty
    # Convention: required params are positional (bare name); optional render as --flags.
    name = param.name if required else f"--{param.name.replace('_', '-')}"
    typ, enum = _type_of(param.annotation)
    entry: dict[str, Any] = {"name": name, "type": typ, "required": required}
    if enum is not None:
        entry["enum"] = enum
    return entry


def build_manifest(app: BeheaxiApp) -> dict[str, Any]:
    verbs = []
    for v in app._verbs:
        args = [_arg_entry(p) for p in v.params if p.name != "self"]
        verbs.append(
            {
                "name": v.name,
                "summary": v.summary,
                "args": args,
                "pinned": v.pinned,
                "mutating": v.mutating,
            }
        )
    return {"tool": app.name, "version": app.version, "summary": app.summary, "verbs": verbs}
