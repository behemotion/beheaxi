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
