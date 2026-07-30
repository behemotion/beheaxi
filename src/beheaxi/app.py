"""BeheaxiApp — the one object that auto-wires the AXI standard."""
from __future__ import annotations

import importlib
import inspect
from dataclasses import dataclass
from typing import Any, Callable

import typer

from .context import AxiContext, extract_global_flags
from .errors import ExitCode
from . import output

def _click_exception_types() -> tuple[type[BaseException], ...]:
    """Every ClickException class that Typer might raise, in this environment.

    Click is a standalone package in older Typer and vendored under
    `typer._click` in >=0.26 — but BOTH can be importable at once, because a
    consumer's other dependencies may pull standalone `click` in alongside a
    vendoring Typer (FastMCP does exactly this). Importing only the first one
    that resolves is therefore not enough: if we catch the standalone class
    while Typer raises the vendored one, usage errors escape the handler and
    exit 1 (internal) instead of 2 (usage), silently breaking the exit-code
    contract and the `usage_exit_2` conformance check. Catch every variant.
    """
    found: list[type[BaseException]] = []
    for module in ("typer._click.exceptions", "click.exceptions"):
        try:
            mod = importlib.import_module(module)
        except ModuleNotFoundError:  # pragma: no cover - depends on packaging
            continue
        exc = getattr(mod, "ClickException", None)
        if isinstance(exc, type) and issubclass(exc, BaseException) and exc not in found:
            found.append(exc)
    return tuple(found)


_CLICK_EXCEPTIONS = _click_exception_types()


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

        from .errors import AxiError, UsageError

        raw = list(sys.argv[1:]) if argv is None else list(argv)
        self.ctx, rest = extract_global_flags(raw)
        if not rest:
            return int(self._run_dashboard())
        try:
            self._typer(args=rest, standalone_mode=False)
            return int(ExitCode.OK)
        except AxiError as e:
            output.render_error(e, self.ctx)
            return int(e.code)
        except _CLICK_EXCEPTIONS as e:  # usage errors: Click RE-RAISES these under
            # `format_message` is Click's API on every ClickException variant, but the
            # tuple above is built at runtime so mypy only knows these are BaseException.
            message = e.format_message()  # type: ignore[attr-defined]
            err = UsageError(message)  # standalone_mode=False (not as SystemExit)
            output.render_error(err, self.ctx)
            return int(err.code)  # USAGE == 2
        except SystemExit as e:  # --help / ctx.exit(): already-clean exits
            return int(e.code) if isinstance(e.code, int) else int(ExitCode.OK)
        except Exception as e:  # truly uncaught -> internal (1)
            internal = AxiError(str(e) or "Internal error")
            internal.type_ = "internal"
            output.render_error(internal, self.ctx)
            return int(ExitCode.INTERNAL)

    def _run_dashboard(self) -> int:
        from . import dashboard

        dashboard.render(self, self.ctx)
        return int(ExitCode.OK)
