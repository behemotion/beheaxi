import json

from beheaxi.app import BeheaxiApp
from beheaxi.errors import NotFound, ExitCode


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
