import json
from pathlib import Path

import pytest

from beheaxi.context import AxiContext
from beheaxi.errors import AxiError, NotFound
from beheaxi.output import emit, make_console, render_error, sanitize


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
    emit("a\x1b]0;pwned\x07b\x1b[31mc\rd\u202ee", AxiContext())
    assert capsys.readouterr().out.strip() == "a]0;pwnedb[31mcde"


def test_sanitize_keeps_tabs_newlines_and_unicode():
    assert sanitize("a\tb\nc — é ✓") == "a\tb\nc — é ✓"


def test_no_color_console_emits_no_escapes_at_all():
    # Rich's no_color=True still emits bold/dim on a TTY; color_system=None emits nothing.
    assert make_console(AxiContext(no_color=True)).color_system is None


def test_non_serializable_context_still_renders_an_envelope(capsys):
    render_error(
        NotFound("x", context={"obj": object(), "path": Path("/tmp/a")}), AxiContext(json=True)
    )
    err = json.loads(capsys.readouterr().err)["error"]
    assert err["type"] == "not_found" and err["context"]["path"] == "/tmp/a"


def test_nan_context_is_dropped_but_the_error_survives(capsys):
    render_error(NotFound("x", context={"v": float("nan")}), AxiContext(json=True))
    err = json.loads(capsys.readouterr().err)["error"]
    assert err["title"] == "x" and "context" not in err


def test_emit_serializes_paths_as_strings(capsys):
    emit({"p": Path("/tmp/a")}, AxiContext(json=True))
    assert json.loads(capsys.readouterr().out) == {"p": "/tmp/a"}


def test_emit_rejects_nan_with_an_axi_error(capsys):
    with pytest.raises(AxiError, match="not valid JSON"):
        emit({"v": float("nan")}, AxiContext(json=True))
    assert capsys.readouterr().out == ""


class _EvilRepr:
    """A custom __repr__ (which Rich's Pretty copies verbatim) carrying controls."""

    def __repr__(self) -> str:
        return "x\u202ey\x1b]0;pwned\x07z"


def test_human_emit_sanitizes_custom_reprs_inside_containers(capsys):
    emit({"k": [_EvilRepr()]}, AxiContext())
    out = capsys.readouterr().out
    assert "\u202e" not in out and "\x1b" not in out and "\x07" not in out
    assert "xy" in out and "pwnedz" in out  # the printable text survives


def test_sanitize_strips_every_bidi_override_and_isolate():
    bidi = "".join(map(chr, [*range(0x202A, 0x202F), *range(0x2066, 0x206A)]))
    assert sanitize(f"a{bidi}b") == "ab"
