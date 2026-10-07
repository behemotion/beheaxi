import json

import pytest

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


def test_literal_flag_after_double_dash_reaches_the_verb(capsys):
    app = BeheaxiApp(name="demo", version="0.0.1", summary="Demo tool.")

    @app.command()
    def echo(word: str) -> None:
        """Echo a word."""
        app.emit({"word": word})

    assert app.main(["echo", "--json", "--", "--quiet"]) == ExitCode.OK
    assert json.loads(capsys.readouterr().out) == {"word": "--quiet"}


def _noop() -> None:
    """No-op."""


@pytest.mark.parametrize(
    "bad", ["Greet", "read_multi", "-x", "x-", "a--b", "9lives", "two words"]
)
def test_invalid_verb_names_are_rejected(bad):
    app = BeheaxiApp(name="demo", version="0.0.1", summary="Demo tool.")
    with pytest.raises(ValueError, match="invalid verb name"):
        app.command(name=bad)(_noop)


def test_private_function_names_are_rejected():
    app = BeheaxiApp(name="demo", version="0.0.1", summary="Demo tool.")

    def _hidden() -> None:
        """Hidden."""

    with pytest.raises(ValueError, match="invalid verb name '-hidden'"):
        app.command()(_hidden)


def test_describe_is_reserved():
    app = BeheaxiApp(name="demo", version="0.0.1", summary="Demo tool.")
    with pytest.raises(ValueError, match="reserved"):
        app.command(name="describe")(_noop)


def test_duplicate_verbs_are_rejected():
    app = BeheaxiApp(name="demo", version="0.0.1", summary="Demo tool.")
    app.command(name="greet")(_noop)
    with pytest.raises(ValueError, match="already registered"):
        app.command(name="greet")(_noop)


@pytest.mark.parametrize("good", ["greet", "registry-lint", "v2", "read-multi"])
def test_valid_verb_names_are_accepted(good):
    app = BeheaxiApp(name="demo", version="0.0.1", summary="Demo tool.")
    app.command(name=good)(_noop)
    assert app._verbs[-1].name == good
