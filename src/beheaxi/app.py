"""BeheaxiApp — the one object that auto-wires the AXI standard."""
from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, Callable

import typer

from .context import AxiContext, extract_global_flags
from .errors import ExitCode
from . import output


@dataclass
class Verb:
    name: str
    summary: str
    params: list[Any]
    pinned: bool
    mutating: bool


class BeheaxiApp:
    def __init__(self, name: str, version: str, summary: str) -> None:
        self.name = name
        self.version = version
        self.summary = summary
        self.ctx = AxiContext()
        self._verbs: list[Verb] = []
        self._status_fn: Callable[[], Any] | None = None
        self._typer = typer.Typer(
            add_completion=False, no_args_is_help=False, rich_markup_mode=None
        )
        # Force multi-command (group) mode even with a single registered command —
        # otherwise Typer/Click collapses to single-command mode and the verb name is
        # not parsed as a subcommand. A no-op callback is the standard Typer idiom.
        @self._typer.callback()
        def _root() -> None:  # pragma: no cover - structural
            pass

        # Auto-register the `describe` command so it always exists. It is framework
        # plumbing: intentionally NOT added to self._verbs, so it is excluded from the
        # manifest and the dashboard verb menu.
        from . import describe as _describe

        @self._typer.command(name="describe")
        def _describe_cmd() -> None:
            """Emit the registration manifest (describe --json is the contract surface)."""
            self.emit(_describe.build_manifest(self))

    # --- registration -------------------------------------------------------
    def command(
        self, *, pinned: bool = False, mutating: bool = False, name: str | None = None
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
            verb_name = name or fn.__name__.replace("_", "-")
            summary = (inspect.getdoc(fn) or "").split("\n")[0]
            self._verbs.append(
                Verb(
                    verb_name,
                    summary,
                    list(inspect.signature(fn).parameters.values()),
                    pinned,
                    mutating,
                )
            )
            self._typer.command(name=verb_name)(fn)
            return fn

        return deco

    def status(self) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
            self._status_fn = fn
            return fn

        return deco

    # --- output helper (read by command bodies) -----------------------------
    def emit(self, data: Any) -> None:
        output.emit(data, self.ctx)

    # --- entrypoint ---------------------------------------------------------
    def main(self, argv: list[str] | None = None) -> int:
        import sys

        raw = list(sys.argv[1:]) if argv is None else list(argv)
        self.ctx, rest = extract_global_flags(raw)
        if not rest:
            return int(self._run_dashboard())
        try:
            self._typer(args=rest, standalone_mode=False)
            return int(ExitCode.OK)
        except SystemExit as e:  # Typer/Click usage errors (full handling added in Task 7)
            return int(e.code) if isinstance(e.code, int) else int(ExitCode.USAGE)

    def _run_dashboard(self) -> int:  # replaced in Task 8
        output.emit({"tool": self.name, "version": self.version}, self.ctx)
        return int(ExitCode.OK)
