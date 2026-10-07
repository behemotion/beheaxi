import json
import sys

import typer

from beheaxi.app import BeheaxiApp
from beheaxi.dashboard import Status
from beheaxi.errors import ExitCode, NotFound, Unavailable


def make_app():
    app = BeheaxiApp(name="demo", version="0.0.1", summary="Demo.")

    @app.command()
    def boom():
        """Boom."""
        raise NotFound("Nothing here", detail="404")

    @app.command()
    def crash():
        """Crash."""
        raise ValueError("unexpected")

    return app


def test_axi_error_maps_to_code_and_envelope(capsys):
    code = make_app().main(["boom", "--json"])
    cap = capsys.readouterr()
    assert code == ExitCode.NOT_FOUND
    assert cap.out == ""  # stdout clean
    assert json.loads(cap.err)["error"]["type"] == "not_found"


def test_uncaught_exception_maps_to_internal(capsys):
    code = make_app().main(["crash", "--json"])
    assert code == ExitCode.INTERNAL
    assert json.loads(capsys.readouterr().err)["error"]["type"] == "internal"


def test_bogus_command_is_usage_exit_2():
    assert make_app().main(["nope-not-a-cmd"]) == ExitCode.USAGE


def test_click_exception_types_covers_every_importable_variant():
    """Regression: catching only ONE ClickException packaging breaks exit codes.

    Typer >=0.26 vendors Click under `typer._click`, but a consumer can have
    standalone `click` installed alongside it (FastMCP does, so beherouter does).
    If we catch the standalone class while Typer raises the vendored one, usage
    errors escape the handler and exit 1 instead of 2 — which silently fails the
    `usage_exit_2` conformance check for every such consumer.
    """
    import importlib

    from beheaxi.app import _click_exception_types

    caught = _click_exception_types()
    assert caught, "no ClickException class found at all"

    expected = []
    for module in ("typer._click.exceptions", "click.exceptions"):
        try:
            mod = importlib.import_module(module)
        except ModuleNotFoundError:
            continue
        expected.append(mod.ClickException)

    for exc in expected:
        assert exc in caught, f"{exc!r} would not be caught"


def test_unknown_command_exits_usage_2():
    """The exit-code contract: an unknown verb is a usage error (2), not internal (1)."""
    from beheaxi.app import BeheaxiApp
    from beheaxi.errors import ExitCode

    app = BeheaxiApp(name="demo", version="0.0.1", summary="Demo tool.")

    @app.command()
    def real() -> None:
        """A real verb."""
        app.emit({"ok": True})

    assert app.main(["definitely-not-a-command"]) == ExitCode.USAGE


def make_emit_app():
    app = BeheaxiApp(name="demo", version="0.0.1", summary="Demo.")

    @app.command()
    def twice() -> None:
        """Emits twice."""
        app.emit({"a": 1})
        app.emit({"b": 2})

    @app.command()
    def emit_then_raise() -> None:
        """beherouter `health --deep` shape: records to stdout, verdict as an error."""
        app.emit({"ok": False})
        raise Unavailable("backend down")

    return app


def test_second_emit_in_json_mode_is_an_error(capsys):
    code = make_emit_app().main(["twice", "--json"])
    cap = capsys.readouterr()
    assert code == ExitCode.INTERNAL
    assert [json.loads(line) for line in cap.out.splitlines()] == [{"a": 1}]
    assert "more than once" in json.loads(cap.err)["error"]["title"]


def test_second_emit_in_human_mode_is_fine():
    assert make_emit_app().main(["twice"]) == ExitCode.OK


def test_emit_then_raise_keeps_both_result_and_error(capsys):
    code = make_emit_app().main(["emit-then-raise", "--json"])
    cap = capsys.readouterr()
    assert code == ExitCode.UNAVAILABLE
    assert json.loads(cap.out) == {"ok": False}
    assert json.loads(cap.err)["error"]["code"] == 6


def test_emit_guard_resets_between_runs(capsys):
    app = make_emit_app()
    app.main(["emit-then-raise", "--json"])
    capsys.readouterr()
    assert app.main(["emit-then-raise", "--json"]) == ExitCode.UNAVAILABLE


def test_direct_verb_calls_after_a_json_run_are_not_guarded(capsys):
    app = BeheaxiApp(name="demo", version="0.0.1", summary="Demo.")

    @app.command()
    def emit_then_raise() -> None:
        """Emits then raises."""
        app.emit({"ok": False})
        raise Unavailable("backend down")

    @app.command()
    def once() -> None:
        """Emits once."""
        app.emit({"a": 1})

    assert app.main(["emit-then-raise", "--json"]) == ExitCode.UNAVAILABLE
    capsys.readouterr()
    once()
    once()  # no run in progress: no guard, neither call raises


def make_exits_app():
    app = BeheaxiApp(name="demo", version="0.0.1", summary="Demo.")

    @app.command()
    def typer_exit() -> None:
        """typer.Exit(3)."""
        raise typer.Exit(code=3)

    @app.command()
    def sys_exit_msg() -> None:
        """sys.exit with a message."""
        sys.exit("fatal: disk full")

    @app.command()
    def sys_exit_int() -> None:
        """sys.exit(12)."""
        sys.exit(12)

    @app.command()
    def returns_value() -> int:
        """Returns 7, which must NOT become the exit code."""
        return 7

    @app.command()
    def aborts() -> None:
        """typer.Abort (what Click raises on Ctrl-C inside a verb)."""
        raise typer.Abort()

    @app.command()
    def leak() -> None:
        """Leaks a DSN in its exception text."""
        raise RuntimeError("connect failed: postgres://admin:hunter2@db/prod")

    return app


def test_typer_exit_code_is_propagated():
    assert make_exits_app().main(["typer-exit"]) == 3


def test_sys_exit_with_a_message_is_a_failure(capsys):
    assert make_exits_app().main(["sys-exit-msg", "--json"]) == ExitCode.INTERNAL
    assert json.loads(capsys.readouterr().err)["error"]["title"] == "fatal: disk full"


def test_sys_exit_int_is_propagated():
    assert make_exits_app().main(["sys-exit-int"]) == 12


def test_command_return_value_is_not_an_exit_code():
    assert make_exits_app().main(["returns-value"]) == ExitCode.OK


def test_click_abort_is_reported_as_aborted(capsys):
    assert make_exits_app().main(["aborts", "--json"]) == ExitCode.INTERNAL
    assert json.loads(capsys.readouterr().err)["error"]["title"] == "Aborted"


def test_internal_error_redacts_exception_text(capsys, monkeypatch):
    monkeypatch.delenv("BEHEAXI_DEBUG", raising=False)
    assert make_exits_app().main(["leak", "--json"]) == ExitCode.INTERNAL
    err = capsys.readouterr().err
    assert "hunter2" not in err
    body = json.loads(err)["error"]
    assert body["title"] == "Internal error"
    assert body["detail"].startswith("RuntimeError")


def test_debug_env_reveals_the_traceback(capsys, monkeypatch):
    monkeypatch.setenv("BEHEAXI_DEBUG", "1")
    make_exits_app().main(["leak", "--json"])
    detail = json.loads(capsys.readouterr().err)["error"]["detail"]
    assert "Traceback" in detail and "hunter2" in detail


def test_failing_status_hook_renders_an_envelope(capsys):
    app = BeheaxiApp(name="demo", version="0.0.1", summary="Demo.")

    @app.status()
    def status() -> Status:
        raise RuntimeError("status backend down")

    assert app.main(["--json"]) == ExitCode.INTERNAL
    cap = capsys.readouterr()
    assert cap.out == ""
    assert json.loads(cap.err)["error"]["type"] == "internal"


def test_nan_in_status_state_is_an_internal_envelope(capsys):
    app = BeheaxiApp(name="demo", version="0.0.1", summary="Demo.")

    @app.status()
    def status() -> Status:
        return Status(state={"v": float("nan")})

    assert app.main(["--json"]) == ExitCode.INTERNAL
    cap = capsys.readouterr()
    assert cap.out == ""
    assert json.loads(cap.err)["error"]["title"] == "Output is not valid JSON"


class _Bad:
    def __str__(self):
        raise RuntimeError("postgres://u:hunter2@h")


def _leak_app():
    app = BeheaxiApp(name="demo", version="0.0.1", summary="Demo.")

    @app.command()
    def bad_context():
        """Raise with an unstringifiable context value."""
        from beheaxi.errors import AxiError

        raise AxiError("t", context={"k": _Bad()})

    @app.command()
    def bad_emit():
        """Emit an unstringifiable value."""
        app.emit({"k": _Bad()})

    @app.command()
    def exit_obj():
        """sys.exit with an exception object."""
        try:
            raise RuntimeError("postgres://u:hunter2@h")
        except RuntimeError as e:
            sys.exit(e)

    return app


def test_unstringifiable_context_keeps_envelope_without_leak(capsys):
    from beheaxi.errors import AxiError

    code = _leak_app().main(["bad-context", "--json"])
    err = capsys.readouterr().err
    assert code == AxiError("t").code
    doc = json.loads(err)
    assert doc["error"]["title"] == "t"
    assert "context" not in doc["error"]
    assert "hunter2" not in err


def test_unstringifiable_emit_does_not_leak(capsys):
    code = _leak_app().main(["bad-emit", "--json"])
    cap = capsys.readouterr()
    assert code == ExitCode.INTERNAL
    assert cap.out == ""
    assert "hunter2" not in cap.err
    assert json.loads(cap.err)["error"]["title"] == "Output is not valid JSON"


def test_sys_exit_with_exception_object_does_not_leak(capsys):
    code = _leak_app().main(["exit-obj", "--json"])
    err = capsys.readouterr().err
    assert code == ExitCode.INTERNAL
    assert json.loads(err)["error"]["title"] == "Internal error"
    assert "hunter2" not in err


def _status_exit_app(code: int) -> BeheaxiApp:
    app = BeheaxiApp(name="demo", version="0.0.1", summary="Demo.")

    @app.status()
    def status() -> Status:
        raise typer.Exit(code=code)

    return app


def test_typer_exit_in_a_status_hook_is_its_exit_code(capsys):
    """No Click runs on the dashboard path, so main() must honour Exit itself."""
    assert _status_exit_app(3).main([]) == 3
    assert _status_exit_app(0).main(["--json"]) == 0
    assert capsys.readouterr().err == ""


def test_every_exit_variant_is_honoured_on_the_dashboard_path():
    from beheaxi.app import _click_classes

    for exit_cls in _click_classes("Exit"):
        app = BeheaxiApp(name="demo", version="0.0.1", summary="Demo.")

        @app.status()
        def status() -> Status:
            raise exit_cls(4)  # noqa: B023 - called within this iteration

        assert app.main([]) == 4, exit_cls


def test_typers_own_exit_and_abort_are_caught():
    """Regression: typer 0.27 moved Exit/Abort out of `_click.exceptions` into
    `typer.exceptions`, which silently emptied both tuples (`except ():` catches nothing)."""
    from beheaxi.app import _CLICK_ABORTS, _CLICK_EXITS

    assert typer.Abort in _CLICK_ABORTS
    assert typer.Exit in _CLICK_EXITS
