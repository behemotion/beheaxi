"""BeheaxiApp — the one object that auto-wires the AXI standard."""
from __future__ import annotations

import functools
import importlib
import inspect
import os
import sys
import traceback
from dataclasses import dataclass
from typing import Any, Callable

import typer

from . import output
from .context import AxiContext, extract_global_flags
from .errors import AxiError, ExitCode, UsageError

DEBUG_ENV = "BEHEAXI_DEBUG"


def _click_classes(name: str) -> tuple[type[BaseException], ...]:
    """Every importable variant of Click's exception class `name`, in this environment.

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
        exc = getattr(mod, name, None)
        if isinstance(exc, type) and issubclass(exc, BaseException) and exc not in found:
            found.append(exc)
    return tuple(found)


def _click_exception_types() -> tuple[type[BaseException], ...]:
    return _click_classes("ClickException")


_CLICK_EXCEPTIONS = _click_exception_types()
# Click converts Ctrl-C/EOF inside a verb (and a declined confirm(abort=True)) into Abort,
# which is a RuntimeError, not a ClickException.
_CLICK_ABORTS = _click_classes("Abort")


def _internal_error(exc: BaseException) -> AxiError:
    """An uncaught exception -> a redacted `internal` error.

    Exception text from DB drivers and HTTP clients routinely embeds DSNs, credentialed URLs
    and tokens, and stderr is captured into agent transcripts and gateway logs. So only the
    exception CLASS is shown, unless BEHEAXI_DEBUG is set: then the full traceback.
    """
    if os.environ.get(DEBUG_ENV):
        detail = "".join(traceback.format_exception(exc)).rstrip()
    else:
        detail = f"{type(exc).__name__} (set {DEBUG_ENV}=1 for the traceback)"
    return AxiError("Internal error", detail=detail)


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
        self._emitted = False
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
            @functools.wraps(fn)
            def invoke(*args: Any, **kwargs: Any) -> None:
                # Discard the verb's return value: under standalone_mode=False Click hands it
                # back to main(), which must only ever see Exit codes there.
                fn(*args, **kwargs)

            self._typer.command(name=verb_name)(invoke)
            return fn

        return deco

    def status(self) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
            self._status_fn = fn
            return fn

        return deco

    # --- output helper (read by command bodies) -----------------------------
    def emit(self, data: Any) -> None:
        """Command output. In --json mode exactly one document may reach stdout per run.

        Emitting and then raising stays legal (stdout = the result, stderr = the error):
        beherouter's `health --deep` reports which backend died exactly that way.
        """
        if self.ctx.json:
            if self._emitted:
                raise AxiError(
                    "emit() called more than once in --json mode",
                    detail="--json allows exactly one JSON document on stdout; "
                    "collect results and emit them once.",
                )
            self._emitted = True
        output.emit(data, self.ctx)

    # --- entrypoint ---------------------------------------------------------
    def main(self, argv: list[str] | None = None) -> int:
        raw = list(sys.argv[1:]) if argv is None else list(argv)
        self.ctx, rest = extract_global_flags(raw)
        self._emitted = False
        try:
            if not rest:
                return self._run_dashboard()
            rv = self._typer(args=rest, standalone_mode=False)
            # Verbs run through a None-returning wrapper (`command`), so an int here can only
            # be Click handing back an Exit's code: `raise typer.Exit(3)` must exit 3.
            if isinstance(rv, int) and not isinstance(rv, bool):
                return rv
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
        except _CLICK_ABORTS:
            aborted = AxiError("Aborted")
            output.render_error(aborted, self.ctx)
            return int(aborted.code)
        except SystemExit as e:  # --help / ctx.exit() / sys.exit() inside a verb
            return self._system_exit_code(e)
        except Exception as e:  # truly uncaught -> redacted internal (1)
            output.render_error(_internal_error(e), self.ctx)
            return int(ExitCode.INTERNAL)

    def _system_exit_code(self, e: SystemExit) -> int:
        """Mirror the interpreter: None -> 0, an int -> itself, anything else is printed and
        exits 1 — `sys.exit("fatal")` must never report success."""
        if e.code is None:
            return int(ExitCode.OK)
        if isinstance(e.code, int):
            return e.code
        failure = AxiError(str(e.code))
        output.render_error(failure, self.ctx)
        return int(failure.code)

    def _run_dashboard(self) -> int:
        from . import dashboard

        dashboard.render(self, self.ctx)
        return int(ExitCode.OK)
