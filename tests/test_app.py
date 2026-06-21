from beheaxi.app import BeheaxiApp
from beheaxi.errors import ExitCode


def make_app():
    app = BeheaxiApp(name="demo", version="0.0.1", summary="Demo tool.")

    @app.command(pinned=True, mutating=False)
    def greet(who: str, loud: bool = False):
        """Greet someone."""
        app.emit({"hello": who, "loud": loud})

    return app


def test_command_runs_and_emits_json(capsys):
    code = make_app().main(["greet", "world", "--json"])
    out = capsys.readouterr().out
    assert code == ExitCode.OK
    assert '"hello": "world"' in out


def test_pinned_metadata_recorded():
    app = make_app()
    verb = next(v for v in app._verbs if v.name == "greet")
    assert verb.pinned is True and verb.mutating is False
    assert verb.summary == "Greet someone."


def test_global_flag_after_subcommand(capsys):
    make_app().main(["greet", "world", "--json"])  # --json AFTER subcommand
    assert '"hello"' in capsys.readouterr().out
