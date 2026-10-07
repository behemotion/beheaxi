"""The no-arg live dashboard: a uniform renderer fed by a per-tool status() hook."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from rich.table import Table
from rich.text import Text

from .context import AxiContext
from .output import make_console, safe_text

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
        app.emit(payload)
        return
    con = make_console(ctx)
    con.print(
        Text.assemble(safe_text(app.name, "bold"), " ", safe_text(f"{app.version} — {app.summary}"))
    )
    if status and status.state:
        t = Table(show_header=False, box=None)
        for k, val in status.state.items():
            t.add_row(safe_text(k), safe_text(val))
        con.print(t)
    if status and status.suggest:
        con.print(Text.assemble("\n", ("Next:", "bold")))
        for s in status.suggest:
            con.print(Text.assemble("  ", safe_text(s)))
    con.print(Text.assemble("\n", ("Commands:", "bold")))
    for v in verbs:
        mark = "*" if v["pinned"] else " "
        con.print(safe_text(f"  {mark} {v['name']:<16} {v['summary']}"))
