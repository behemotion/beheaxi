"""The no-arg live dashboard: a uniform renderer fed by a per-tool status() hook."""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from rich.console import Console
from rich.table import Table

from .context import AxiContext

if TYPE_CHECKING:
    from .app import BeheaxiApp


@dataclass
class Status:
    state: dict[str, Any] = field(default_factory=dict)
    suggest: list[str] = field(default_factory=list)


def render(app: BeheaxiApp, ctx: AxiContext) -> None:
    status: Status | None = app._status_fn() if app._status_fn else None
    verbs = [{"name": v.name, "summary": v.summary, "pinned": v.pinned} for v in app._verbs]
    if ctx.json:
        payload = {
            "tool": app.name,
            "version": app.version,
            "summary": app.summary,
            "state": status.state if status else {},
            "suggest": status.suggest if status else [],
            "verbs": verbs,
        }
        sys.stdout.write(json.dumps(payload) + "\n")
        return
    con = Console(no_color=ctx.no_color, highlight=False)
    con.print(f"[bold]{app.name}[/bold] {app.version} — {app.summary}")
    if status and status.state:
        t = Table(show_header=False, box=None)
        for k, val in status.state.items():
            t.add_row(str(k), str(val))
        con.print(t)
    if status and status.suggest:
        con.print("\n[bold]Next:[/bold]")
        for s in status.suggest:
            con.print(f"  {s}")
    con.print("\n[bold]Commands:[/bold]")
    for v in verbs:
        mark = "*" if v["pinned"] else " "
        con.print(f"  {mark} {v['name']:<16} {v['summary']}")
