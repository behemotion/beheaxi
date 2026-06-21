import json
from pathlib import Path

import jsonschema

from beheaxi.app import BeheaxiApp
from beheaxi.describe import build_manifest

SCHEMA = json.loads((Path("src/beheaxi/manifest_schema.json")).read_text())


def make_app():
    app = BeheaxiApp(name="demo", version="0.0.1", summary="Demo.")

    @app.command(pinned=True, mutating=False)
    def search(query: str, shelf: str = None, top: int = 5):
        """Search things."""
        app.emit([])

    return app


def test_manifest_validates_against_schema():
    jsonschema.validate(build_manifest(make_app()), SCHEMA)


def test_manifest_captures_args_and_types_and_required():
    m = build_manifest(make_app())
    verb = next(v for v in m["verbs"] if v["name"] == "search")
    args = {a["name"]: a for a in verb["args"]}
    assert args["query"] == {"name": "query", "type": "string", "required": True}
    assert args["--shelf"]["required"] is False  # has default -> optional, flag form
    assert args["--top"]["type"] == "integer"
    assert verb["pinned"] is True and verb["mutating"] is False


def test_describe_command_emits_valid_json(capsys):
    code = make_app().main(["describe", "--json"])
    jsonschema.validate(json.loads(capsys.readouterr().out), SCHEMA)
    assert code == 0


def test_describe_flag_before_or_after(capsys):
    make_app().main(["--json", "describe"])
    a = capsys.readouterr().out
    make_app().main(["describe", "--json"])
    b = capsys.readouterr().out
    assert json.loads(a) == json.loads(b)
