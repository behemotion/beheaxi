from beheaxi.context import AxiContext, extract_global_flags


def test_defaults():
    ctx = AxiContext()
    assert (ctx.json, ctx.quiet, ctx.no_color) == (False, False, False)


def test_extract_before_subcommand():
    ctx, rest = extract_global_flags(["--json", "describe"])
    assert ctx.json is True and rest == ["describe"]


def test_extract_after_subcommand():
    ctx, rest = extract_global_flags(["describe", "--json"])
    assert ctx.json is True and rest == ["describe"]


def test_extract_interleaved_multiple():
    ctx, rest = extract_global_flags(["search", "--no-color", "foo", "--quiet"])
    assert ctx.no_color and ctx.quiet
    assert rest == ["search", "foo"]


def test_no_color_forced_when_not_tty(monkeypatch):
    monkeypatch.setattr("sys.stdout.isatty", lambda: False)
    ctx, _ = extract_global_flags(["describe"])
    assert ctx.no_color is True
