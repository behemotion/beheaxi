"""Output rendering: JSON for machines, Rich for humans; honors --no-color."""
from __future__ import annotations

import json
import sys
from typing import Any

from rich.console import Console

from .context import AxiContext
from .errors import AxiError


def _console(ctx: AxiContext, *, stderr: bool = False) -> Console:
    return Console(no_color=ctx.no_color, stderr=stderr, highlight=False)


def emit(data: Any, ctx: AxiContext) -> None:
    """Primary success output. One JSON doc to stdout in --json mode, else Rich."""
    if ctx.json:
        sys.stdout.write(json.dumps(data) + "\n")
        return
    if ctx.quiet:
        return
    _console(ctx).print(data)


def render_error(err: AxiError, ctx: AxiContext) -> None:
    """Error output → always stderr. JSON envelope in --json mode, else Rich."""
    if ctx.json:
        sys.stderr.write(json.dumps(err.envelope()) + "\n")
        return
    con = _console(ctx, stderr=True)
    con.print(f"[red]error:[/red] {err.title}")
    if err.detail:
        con.print(err.detail)
