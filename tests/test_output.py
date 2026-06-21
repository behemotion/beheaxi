import json

from beheaxi.context import AxiContext
from beheaxi.output import emit, render_error
from beheaxi.errors import NotFound


def test_emit_json_mode_is_parseable(capsys):
    emit({"a": 1, "b": [2, 3]}, AxiContext(json=True))
    out = capsys.readouterr().out
    assert json.loads(out) == {"a": 1, "b": [2, 3]}


def test_emit_human_mode_renders_text(capsys):
    emit({"shelves": 3}, AxiContext(json=False))
    out = capsys.readouterr().out
    assert "shelves" in out and out.strip() != ""


def test_error_envelope_json_goes_to_stderr(capsys):
    render_error(NotFound("Shelf not found", detail="x"), AxiContext(json=True))
    cap = capsys.readouterr()
    assert cap.out == ""  # stdout stays clean
    assert json.loads(cap.err)["error"]["type"] == "not_found"


def test_no_color_strips_ansi(capsys):
    emit({"k": "v"}, AxiContext(json=False, no_color=True))
    out = capsys.readouterr().out
    assert "\x1b[" not in out  # no ANSI escapes
