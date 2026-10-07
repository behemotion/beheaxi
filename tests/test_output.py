import json

from beheaxi.context import AxiContext
from beheaxi.output import emit, make_console, render_error, sanitize
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


def test_human_error_is_not_parsed_as_markup(capsys):
    title = "no such [bold]x[/bold] [link=https://evil.example]y[/link]"
    render_error(NotFound(title, detail="d\x1b[2Jd"), AxiContext())
    err = capsys.readouterr().err
    assert title in err  # brackets survive literally: nothing was interpreted
    assert "\x1b" not in err
    assert "d[2Jd" in err  # the ESC byte is stripped; printable remnants stay


def test_human_emit_strips_terminal_controls(capsys):
    # OSC 0 title rewrite, CSI colour, carriage return, RTL override (CVE-2021-42574)
    emit("a\x1b]0;pwned\x07b\x1b[31mc\rd‮e", AxiContext())
    assert capsys.readouterr().out.strip() == "a]0;pwnedb[31mcde"


def test_sanitize_keeps_tabs_newlines_and_unicode():
    assert sanitize("a\tb\nc — é ✓") == "a\tb\nc — é ✓"


def test_no_color_console_emits_no_escapes_at_all():
    # Rich's no_color=True still emits bold/dim on a TTY; color_system=None emits nothing.
    assert make_console(AxiContext(no_color=True)).color_system is None
