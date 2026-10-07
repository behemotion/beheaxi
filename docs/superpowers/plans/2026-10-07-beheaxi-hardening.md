# beheaxi v0.2.0 Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the 6 security gaps and 10 contract bugs that the 2026-10-07 review reproduced in beheaxi v0.1.2, harden CI, and release as v0.2.0 without breaking beherouter.

**Architecture:** All fixes live in the existing modules. `output.py` becomes the single choke point for safe human rendering and strict JSON. `BeheaxiApp.main()` becomes one handler that covers every exit path, including the dashboard. Verb signatures are validated and typed once, at registration, in `describe.py`. The conformance runner gets a `ToolRunner` that turns every launch failure into a result, and the checks gain a pseudo-terminal probe.

**Tech Stack:** Python ≥ 3.12, Typer (vendored Click in ≥ 0.26), Rich, jsonschema, `uv`, pytest, ruff (line-length 100), mypy `--strict` over `src/beheaxi`.

**Spec:** `docs/superpowers/specs/2026-10-07-beheaxi-hardening-design.md`. Finding IDs (S1–S6, B1–B10, B3a, I1–I4) are used throughout. Read §2 of the spec before starting any task.

## Global Constraints

- Python `>=3.12`; ruff `line-length = 100`; `mypy --strict` must stay clean over `src/beheaxi`.
- `src/beheaxi/manifest_schema.json` is **not modified**. beherouter validates against it verbatim.
- `ExitCode` members 0–6 are unchanged. The new `DOMAIN_EXIT_FLOOR = 10` lives in `src/beheaxi/errors.py`.
- Error envelope key order stays `type, title, detail, code, context`; type strings use underscores; errors go to stderr.
- In `--json` mode, **at most one** JSON document reaches stdout. Emitting and then raising stays legal, because beherouter's `health --deep` relies on it.
- Debug opt-in env var: exactly `BEHEAXI_DEBUG` (non-empty = on).
- Dependency floor after Task 10: `typer>=0.13.1` (`rich>=13.7`, `jsonschema>=4.21` unchanged).
- Release version: `0.2.0`. **Never push, tag or create a release without explicit user confirmation.**
- Run every command from the repo root (`beheaxi/`). Run tests with `uv run pytest -q`.
- Commit messages: conventional style (`fix:`, `feat:`, `ci:`, `docs:`), ending with
- Do not edit anything under `../beherouter/`. Task 12 only *runs* it.

## File map

| File | Responsibility after this plan | Tasks |
|---|---|---|
| `src/beheaxi/output.py` | `sanitize`, `safe_text`, `make_console`, `to_json`, `emit`, `render_error`: the only place bytes reach a terminal or a JSON stream | 1, 2 |
| `src/beheaxi/context.py` | Global-flag extraction (`--` aware), `NO_COLOR` | 1, 3 |
| `src/beheaxi/dashboard.py` | Dashboard rendering through `output` helpers; JSON via `app.emit` | 1, 2 |
| `src/beheaxi/app.py` | Registration guard, emit-once guard, unified exit handling, redaction | 2, 4, 5, 6 |
| `src/beheaxi/describe.py` | Signature → manifest arg entries (types, names, shape validation) | 6 |
| `src/beheaxi/errors.py`, `__init__.py` | `DOMAIN_EXIT_FLOOR` | 9 |
| `src/beheaxi/conformance/checks.py` | `Runner` protocol, 7 checks | 7, 8 |
| `src/beheaxi/conformance/runner.py` | `ToolRunner` (pipe + pty), env scrubbing, guarded checks | 7, 8 |
| `src/beheaxi/cli.py` | Version from metadata, exit 10, `--inherit-env` | 9 |
| `tests/fake_tool.py` (new) | Hand-rolled CLI whose single defect is chosen by `FAKE_TOOL_MODE` | 7, 8 |
| `tests/test_describe_types.py` (new) | Manifest typing under `from __future__ import annotations` | 6 |
| `tests/test_cli.py` (new) | beheaxi's own CLI | 9 |
| `pyproject.toml`, `uv.lock`, `.github/workflows/ci.yml`, `.github/dependabot.yml` (new) | Floors, CI hardening | 10, 11 |
| `README.md`, the 2026-06-21 design spec, `HARNESS-DIVERGENCES.md` | Docs | 11 |

---

### Task 1: Safe human rendering (S2, S3, B10, NO_COLOR)

**Files:**
- Modify: `src/beheaxi/output.py` (whole file)
- Modify: `src/beheaxi/dashboard.py` (human-render half of `render`)
- Modify: `src/beheaxi/context.py:4,34-35`
- Test: `tests/test_output.py`, `tests/test_dashboard.py`, `tests/test_context.py`

**Interfaces:**
- Produces: `output.sanitize(text: str) -> str`, `output.safe_text(value: Any, style: str = "") -> rich.text.Text`, `output.make_console(ctx: AxiContext, *, stderr: bool = False) -> rich.console.Console`. The private `output._console` is **removed**.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_output.py`, and change its import line to
`from beheaxi.output import emit, make_console, render_error, sanitize`:

```python
def test_human_error_is_not_parsed_as_markup(capsys):
    title = "no such [bold]x[/bold] [link=https://evil.example]y[/link]"
    render_error(NotFound(title, detail="d\x1b[2Jd"), AxiContext())
    err = capsys.readouterr().err
    assert title in err  # brackets survive literally: nothing was interpreted
    assert "\x1b" not in err
    assert "dd" in err  # control sequence stripped from detail too


def test_human_emit_strips_terminal_controls(capsys):
    # OSC 0 title rewrite, CSI colour, carriage return, RTL override (CVE-2021-42574)
    emit("a\x1b]0;pwned\x07b\x1b[31mc\rd‮e", AxiContext())
    assert capsys.readouterr().out.strip() == "a]0;pwnedb[31mcde"


def test_sanitize_keeps_tabs_newlines_and_unicode():
    assert sanitize("a\tb\nc — é ✓") == "a\tb\nc — é ✓"


def test_no_color_console_emits_no_escapes_at_all():
    # Rich's no_color=True still emits bold/dim on a TTY; color_system=None emits nothing.
    assert make_console(AxiContext(no_color=True)).color_system is None
```

Append to `tests/test_dashboard.py`:

```python
def test_dashboard_renders_untrusted_state_literally(capsys):
    app = BeheaxiApp(name="demo", version="0.0.1", summary="Demo tool.")

    @app.status()
    def status() -> Status:
        return Status(state={"note": "[red]x[/red]\x1b[2J"}, suggest=["run [bold]y[/bold]"])

    assert app.main([]) == 0
    out = capsys.readouterr().out
    assert "[red]x[/red]" in out and "run [bold]y[/bold]" in out
    assert "\x1b" not in out
```

Append to `tests/test_context.py` (add `import sys` at the top):

```python
def test_no_color_env_var_disables_color_on_a_tty(monkeypatch):
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    monkeypatch.setenv("NO_COLOR", "1")
    assert extract_global_flags([])[0].no_color is True


def test_tty_without_no_color_keeps_color(monkeypatch):
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    monkeypatch.delenv("NO_COLOR", raising=False)
    assert extract_global_flags([])[0].no_color is False
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest -q tests/test_output.py tests/test_dashboard.py tests/test_context.py`
Expected: `ImportError` for `make_console`/`sanitize` (the whole of `test_output.py` errors). The dashboard markup test FAILs because the brackets were consumed. `test_no_color_env_var_disables_color_on_a_tty` FAILs.

- [ ] **Step 3: Implement — replace `src/beheaxi/output.py` entirely**

```python
"""Output rendering: JSON for machines, Rich for humans; honors --no-color."""
from __future__ import annotations

import json
import re
import sys
from typing import Any

from rich.console import Console
from rich.text import Text

from .context import AxiContext
from .errors import AxiError

# Stripped from every string rendered for a human terminal: C0 controls except \t and \n
# (ESC starts CSI/OSC sequences — title rewrites, OSC 8 hyperlinks, cursor moves; \r
# overwrites the visible line), DEL, C1 controls, and the bidi overrides/isolates that
# reorder what the reader sees (CVE-2021-42574).
_UNSAFE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f‪-‮⁦-⁩]")


def sanitize(text: str) -> str:
    """Remove terminal-control and bidi characters from text bound for a human terminal."""
    return _UNSAFE.sub("", text)


def safe_text(value: Any, style: str = "") -> Text:
    """Untrusted value -> Rich Text: never parsed as markup, control characters removed."""
    return Text(sanitize(str(value)), style=style)


def make_console(ctx: AxiContext, *, stderr: bool = False) -> Console:
    """The one Console factory.

    markup/emoji are off: framework styling is built from Text objects, so no caller-supplied
    string is ever interpreted. Under --no-color, color_system=None rather than
    no_color=True: Rich's no_color drops colours but still emits bold/dim escapes on a TTY.
    """
    return Console(
        color_system=None if ctx.no_color else "auto",
        stderr=stderr,
        highlight=False,
        markup=False,
        emoji=False,
    )


def emit(data: Any, ctx: AxiContext) -> None:
    """Primary success output. One JSON doc to stdout in --json mode, else Rich."""
    if ctx.json:
        sys.stdout.write(json.dumps(data) + "\n")
        return
    if ctx.quiet:
        return
    # Strings are sanitized; containers go through Rich's Pretty, whose repr() already
    # escapes control characters.
    make_console(ctx).print(safe_text(data) if isinstance(data, str) else data)


def render_error(err: AxiError, ctx: AxiContext) -> None:
    """Error output → always stderr. JSON envelope in --json mode, else Rich."""
    if ctx.json:
        sys.stderr.write(json.dumps(err.envelope()) + "\n")
        return
    con = make_console(ctx, stderr=True)
    con.print(Text.assemble(("error:", "red"), " ", safe_text(err.title)))
    if err.detail:
        con.print(safe_text(err.detail))
```

- [ ] **Step 4: Implement — dashboard human half**

In `src/beheaxi/dashboard.py`, replace `from rich.console import Console` with
`from rich.text import Text` and add `from .output import make_console, safe_text` below the
`from .context import AxiContext` line. Then replace everything from
`    con = Console(no_color=ctx.no_color, highlight=False)` to the end of the file with:

```python
    con = make_console(ctx)
    con.print(
        Text.assemble(safe_text(app.name, "bold"), " ", safe_text(f"{app.version} — {app.summary}"))
    )
    if status and status.state:
        t = Table(show_header=False, box=None)
        for k, val in status.state.items():
            t.add_row(safe_text(k), safe_text(val))
        con.print(t)
    if status and status.suggest:
        con.print(Text.assemble("\n", ("Next:", "bold")))
        for s in status.suggest:
            con.print(Text.assemble("  ", safe_text(s)))
    con.print(Text.assemble("\n", ("Commands:", "bold")))
    for v in verbs:
        mark = "*" if v["pinned"] else " "
        con.print(safe_text(f"  {mark} {v['name']:<16} {v['summary']}"))
```

- [ ] **Step 5: Implement — `NO_COLOR` in `src/beheaxi/context.py`**

Add `import os` next to `import sys`, and replace:

```python
    if not sys.stdout.isatty():
        ctx.no_color = True
```

with:

```python
    # NO_COLOR (https://no-color.org): any non-empty value means no colour, like --no-color.
    if not sys.stdout.isatty() or os.environ.get("NO_COLOR"):
        ctx.no_color = True
```

- [ ] **Step 6: Run the full suite plus the gates**

Run: `uv run pytest -q && uv run ruff check . && uv run mypy`
Expected: all pass. The 30 old tests plus 7 new ones.

- [ ] **Step 7: Commit**

```bash
git add src/beheaxi/output.py src/beheaxi/dashboard.py src/beheaxi/context.py tests/
git commit -m "fix: never interpret or pass through untrusted text in human output

Rich markup is disabled framework-wide and terminal control / bidi characters are
stripped from rendered strings (S2, S3). --no-color and NO_COLOR now use
color_system=None: Rich's no_color still emitted bold on a real TTY (B10).

```

---

### Task 2: JSON output integrity (B5, B6, NaN)

**Files:**
- Modify: `src/beheaxi/output.py` (`emit`, `render_error`, new `to_json`)
- Modify: `src/beheaxi/app.py` (imports, `__init__`, `emit`, start of `main`)
- Modify: `src/beheaxi/dashboard.py` (JSON branch, imports)
- Test: `tests/test_output.py`, `tests/test_app_errors.py`

**Interfaces:**
- Consumes: Task 1's `output.make_console`, `safe_text`.
- Produces: `output.to_json(data: Any) -> str`, which raises `ValueError` on NaN, Infinity or cycles. `BeheaxiApp._emitted: bool` is reset at the start of every `main()`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_output.py` (add `from pathlib import Path`, `import pytest` and
`from beheaxi.errors import AxiError` to the imports):

```python
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
```

Append to `tests/test_app_errors.py` (add `from beheaxi.errors import Unavailable` to the imports):

```python
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
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest -q tests/test_output.py tests/test_app_errors.py`
Expected: the context tests FAIL with `TypeError`/`ValueError` from `json.dumps`, the Path test FAILs, the NaN test FAILs (`NaN` is written), and `test_second_emit_in_json_mode_is_an_error` FAILs (two lines, exit 0).

- [ ] **Step 3: Implement `to_json` and use it in `src/beheaxi/output.py`**

Add after `make_console`:

```python
def to_json(data: Any) -> str:
    """The one JSON encoder for stdout/stderr.

    Values json cannot encode natively (Path, datetime, UUID, ...) become strings. NaN and
    Infinity raise ValueError: they are not JSON, and strict parsers on the agent side reject
    the whole document.
    """
    return json.dumps(data, default=str, allow_nan=False)
```

In `emit`, replace `        sys.stdout.write(json.dumps(data) + "\n")` with:

```python
        try:
            text = to_json(data)
        except ValueError as e:  # NaN/Infinity, circular reference
            raise AxiError("Output is not valid JSON", detail=str(e)) from e
        sys.stdout.write(text + "\n")
```

In `render_error`, replace `        sys.stderr.write(json.dumps(err.envelope()) + "\n")` with:

```python
        envelope = err.envelope()
        try:
            text = to_json(envelope)
        except ValueError:  # NaN/Infinity or a cycle in context: keep the error, drop context
            envelope["error"].pop("context", None)
            text = to_json(envelope)
        sys.stderr.write(text + "\n")
```

- [ ] **Step 4: Implement the emit-once guard in `src/beheaxi/app.py`**

1. Change `from .errors import ExitCode` to `from .errors import AxiError, ExitCode, UsageError`, and **delete** the line `        from .errors import AxiError, UsageError` inside `main`.
2. In `__init__`, after `self._status_fn: Callable[[], Any] | None = None`, add `self._emitted = False`.
3. Replace the `emit` method with:

```python
    def emit(self, data: Any) -> None:
        """Command output. In --json mode exactly one document may reach stdout per run.

        Emitting and then raising stays legal (stdout = the result, stderr = the error):
        beherouter's `health --deep` reports which backend died exactly that way.
        """
        if self.ctx.json:
            if self._emitted:
                raise AxiError(
                    "emit() called more than once in --json mode",
                    detail="--json allows exactly one JSON document on stdout; "
                    "collect results and emit them once.",
                )
            self._emitted = True
        output.emit(data, self.ctx)
```

4. In `main`, directly after `self.ctx, rest = extract_global_flags(raw)`, add `self._emitted = False`.

- [ ] **Step 5: Route the dashboard JSON through `app.emit`**

In `src/beheaxi/dashboard.py`, replace `        sys.stdout.write(json.dumps(payload) + "\n")` with
`        app.emit(payload)`, then delete the now-unused `import json` and `import sys` lines.

- [ ] **Step 6: Run the full suite plus the gates**

Run: `uv run pytest -q && uv run ruff check . && uv run mypy`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add src/beheaxi/output.py src/beheaxi/app.py src/beheaxi/dashboard.py tests/
git commit -m "fix: guarantee a single, valid JSON document per --json run

One strict encoder (default=str, allow_nan=False); render_error drops an
unencodable context instead of crashing (B5); a second emit() in --json mode is an
error, while emit-then-raise stays legal for beherouter health --deep (B6).

```

---

### Task 3: `--` ends global-flag extraction (B7)

**Files:**
- Modify: `src/beheaxi/context.py` (`extract_global_flags`)
- Test: `tests/test_context.py`, `tests/test_app.py`

**Interfaces:** No signature change: `extract_global_flags(argv) -> (AxiContext, list[str])`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_context.py`:

```python
def test_flags_after_double_dash_are_literal_arguments():
    ctx, rest = extract_global_flags(["echo", "--", "--json", "--quiet"])
    assert (ctx.json, ctx.quiet) == (False, False)
    assert rest == ["echo", "--", "--json", "--quiet"]


def test_flags_before_double_dash_are_still_extracted():
    ctx, rest = extract_global_flags(["--json", "echo", "--", "x"])
    assert ctx.json is True and rest == ["echo", "--", "x"]
```

Append to `tests/test_app.py` (add `import json` at the top):

```python
def test_literal_flag_after_double_dash_reaches_the_verb(capsys):
    app = BeheaxiApp(name="demo", version="0.0.1", summary="Demo tool.")

    @app.command()
    def echo(word: str) -> None:
        """Echo a word."""
        app.emit({"word": word})

    assert app.main(["echo", "--json", "--", "--quiet"]) == ExitCode.OK
    assert json.loads(capsys.readouterr().out) == {"word": "--quiet"}
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest -q tests/test_context.py tests/test_app.py`
Expected: 3 FAIL (flags after `--` were extracted; the verb gets a usage error).

- [ ] **Step 3: Implement**

Replace the body of `extract_global_flags` in `src/beheaxi/context.py`, from the docstring through the
`for` loop, with:

```python
    """Pull --json/--quiet/--no-color out of argv at any position; return (ctx, remaining).

    Stripping the global flags before Typer/Click parses makes them work in any position
    (before or after the subcommand) — Click's own option parsing is placement-sensitive.
    Extraction stops at `--`: everything after it is a literal argument (POSIX), so a verb
    can receive the string "--json" as data. The `--` itself is kept for Click.
    """
    ctx = AxiContext()
    rest: list[str] = []
    for i, tok in enumerate(argv):
        if tok == "--":
            rest.extend(argv[i:])
            break
        if tok == "--json":
            ctx.json = True
        elif tok == "--quiet":
            ctx.quiet = True
        elif tok == "--no-color":
            ctx.no_color = True
        else:
            rest.append(tok)
```

(Leave the `NO_COLOR`/isatty block from Task 1 and `return ctx, rest` unchanged.)

- [ ] **Step 4: Run the full suite plus the gates**

Run: `uv run pytest -q && uv run ruff check . && uv run mypy`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/beheaxi/context.py tests/
git commit -m "fix: stop global-flag extraction at -- (B7)

```

---

### Task 4: One handler for every exit path (S1, B1, B2, B4, I4)

**Files:**
- Modify: `src/beheaxi/app.py` (imports, the Click-class helper, new `_internal_error`, the `command` wrapper, `main`, new `_system_exit_code`)
- Test: `tests/test_app_errors.py`

**Interfaces:**
- Consumes: Task 2's robust `output.render_error`.
- Produces: `app.DEBUG_ENV = "BEHEAXI_DEBUG"`, `app._click_classes(name: str) -> tuple[type[BaseException], ...]`. `app._click_exception_types()` is kept because an existing test imports it. `BeheaxiApp._system_exit_code(e: SystemExit) -> int`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_app_errors.py` (add `import sys`, `import typer` and
`from beheaxi.dashboard import Status` to the imports):

```python
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
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest -q tests/test_app_errors.py`
Expected: `typer-exit` (got 0), `sys-exit-msg` (got 0), `aborts` (title is `"Internal error"`), both redaction tests and the status-hook test (raw `RuntimeError` escapes `main`) all FAIL. `sys-exit-int` and `returns-value` already pass; they guard against regressions.

- [ ] **Step 3: Implement — imports and the Click helper**

In `src/beheaxi/app.py`, replace the import block (everything from `import importlib` up to and including
`from . import output`) with:

```python
import functools
import importlib
import inspect
import os
import sys
import traceback
from dataclasses import dataclass
from typing import Any, Callable

import typer

from . import output
from .context import AxiContext, extract_global_flags
from .errors import AxiError, ExitCode, UsageError

DEBUG_ENV = "BEHEAXI_DEBUG"
```

Replace the whole `_click_exception_types` function and the `_CLICK_EXCEPTIONS = …` line with:

```python
def _click_classes(name: str) -> tuple[type[BaseException], ...]:
    """Every importable variant of Click's exception class `name`, in this environment.

    Click is a standalone package in older Typer and vendored under
    `typer._click` in >=0.26 — but BOTH can be importable at once, because a
    consumer's other dependencies may pull standalone `click` in alongside a
    vendoring Typer (FastMCP does exactly this). Importing only the first one
    that resolves is therefore not enough: if we catch the standalone class
    while Typer raises the vendored one, usage errors escape the handler and
    exit 1 (internal) instead of 2 (usage), silently breaking the exit-code
    contract and the `usage_exit_2` conformance check. Catch every variant.
    """
    found: list[type[BaseException]] = []
    for module in ("typer._click.exceptions", "click.exceptions"):
        try:
            mod = importlib.import_module(module)
        except ModuleNotFoundError:  # pragma: no cover - depends on packaging
            continue
        exc = getattr(mod, name, None)
        if isinstance(exc, type) and issubclass(exc, BaseException) and exc not in found:
            found.append(exc)
    return tuple(found)


def _click_exception_types() -> tuple[type[BaseException], ...]:
    return _click_classes("ClickException")


_CLICK_EXCEPTIONS = _click_exception_types()
# Click converts Ctrl-C/EOF inside a verb (and a declined confirm(abort=True)) into Abort,
# which is a RuntimeError, not a ClickException.
_CLICK_ABORTS = _click_classes("Abort")


def _internal_error(exc: BaseException) -> AxiError:
    """An uncaught exception -> a redacted `internal` error.

    Exception text from DB drivers and HTTP clients routinely embeds DSNs, credentialed URLs
    and tokens, and stderr is captured into agent transcripts and gateway logs. So only the
    exception CLASS is shown, unless BEHEAXI_DEBUG is set: then the full traceback.
    """
    if os.environ.get(DEBUG_ENV):
        detail = "".join(traceback.format_exception(exc)).rstrip()
    else:
        detail = f"{type(exc).__name__} (set {DEBUG_ENV}=1 for the traceback)"
    return AxiError("Internal error", detail=detail)
```

- [ ] **Step 4: Implement — the None-returning verb wrapper**

In `command`'s inner `deco`, replace `            self._typer.command(name=verb_name)(fn)` with:

```python
            @functools.wraps(fn)
            def invoke(*args: Any, **kwargs: Any) -> None:
                # Discard the verb's return value: under standalone_mode=False Click hands it
                # back to main(), which must only ever see Exit codes there.
                fn(*args, **kwargs)

            self._typer.command(name=verb_name)(invoke)
```

- [ ] **Step 5: Implement — `main` and `_system_exit_code`**

Replace the whole `main` method (including its local `import sys`) with:

```python
    def main(self, argv: list[str] | None = None) -> int:
        raw = list(sys.argv[1:]) if argv is None else list(argv)
        self.ctx, rest = extract_global_flags(raw)
        self._emitted = False
        try:
            if not rest:
                return self._run_dashboard()
            rv = self._typer(args=rest, standalone_mode=False)
            # Verbs run through a None-returning wrapper (`command`), so an int here can only
            # be Click handing back an Exit's code: `raise typer.Exit(3)` must exit 3.
            if isinstance(rv, int) and not isinstance(rv, bool):
                return rv
            return int(ExitCode.OK)
        except AxiError as e:
            output.render_error(e, self.ctx)
            return int(e.code)
        except _CLICK_EXCEPTIONS as e:  # usage errors: Click RE-RAISES these under
            # `format_message` is Click's API on every ClickException variant, but the
            # tuple above is built at runtime so mypy only knows these are BaseException.
            message = e.format_message()  # type: ignore[attr-defined]
            err = UsageError(message)  # standalone_mode=False (not as SystemExit)
            output.render_error(err, self.ctx)
            return int(err.code)  # USAGE == 2
        except _CLICK_ABORTS:
            aborted = AxiError("Aborted")
            output.render_error(aborted, self.ctx)
            return int(aborted.code)
        except SystemExit as e:  # --help / ctx.exit() / sys.exit() inside a verb
            return self._system_exit_code(e)
        except Exception as e:  # truly uncaught -> redacted internal (1)
            output.render_error(_internal_error(e), self.ctx)
            return int(ExitCode.INTERNAL)

    def _system_exit_code(self, e: SystemExit) -> int:
        """Mirror the interpreter: None -> 0, an int -> itself, anything else is printed and
        exits 1 — `sys.exit("fatal")` must never report success."""
        if e.code is None:
            return int(ExitCode.OK)
        if isinstance(e.code, int):
            return e.code
        failure = AxiError(str(e.code))
        output.render_error(failure, self.ctx)
        return int(failure.code)
```

(`_run_dashboard` is unchanged. It now runs inside the `try`, which fixes B4.)

- [ ] **Step 6: Run the full suite plus the gates**

Run: `uv run pytest -q && uv run ruff check . && uv run mypy`
Expected: all pass, including the pre-existing
`test_click_exception_types_covers_every_importable_variant`.

- [ ] **Step 7: Smoke-test the dogfood gate**

Run: `uv run beheaxi conformance "beheaxi" --json`
Expected: `"ok": true` and exit 0.

- [ ] **Step 8: Commit**

```bash
git add src/beheaxi/app.py tests/test_app_errors.py
git commit -m "fix: one handler for every exit path; redact internal errors

typer.Exit(n) and sys.exit('msg') now exit as they should (B1, B2); the
dashboard runs inside the handler (B4); click.Abort reports 'Aborted' (I4);
uncaught exception text is redacted unless BEHEAXI_DEBUG is set (S1).

```

---

### Task 5: Verb-name guard at registration (S4, divergence #5)

**Files:**
- Modify: `src/beheaxi/app.py` (constants, `_check_verb_name`, call in `command`)
- Test: `tests/test_app.py`

**Interfaces:**
- Produces: `app.RESERVED_VERBS: frozenset[str]` (`{"describe"}`), and `BeheaxiApp._check_verb_name(verb_name: str) -> None`, which raises `ValueError`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_app.py` (add `import pytest` at the top):

```python
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
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest -q tests/test_app.py`
Expected: the invalid-name, private-name, reserved and duplicate tests FAIL ("DID NOT RAISE").

- [ ] **Step 3: Implement**

In `src/beheaxi/app.py`, add `import re` to the imports, and below `DEBUG_ENV = "BEHEAXI_DEBUG"` add:

```python
RESERVED_VERBS = frozenset({"describe"})
# Lowercase words joined by single hyphens. No underscores: beherouter flattens verb names
# to `<tool>_<verb>` MCP tools, so `read_multi` and a group `read multi` would collide.
_VERB_NAME = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*")
```

In `command`'s `deco`, directly after `verb_name = name or fn.__name__.replace("_", "-")`, add
`            self._check_verb_name(verb_name)`. Then add this method below `command`:

```python
    def _check_verb_name(self, verb_name: str) -> None:
        """Registration-time guard: a bad name is a programmer error, raised at import."""
        if not _VERB_NAME.fullmatch(verb_name):
            raise ValueError(
                f"invalid verb name {verb_name!r}: use lowercase words joined by single "
                "hyphens, e.g. 'registry-lint'"
            )
        if verb_name in RESERVED_VERBS:
            raise ValueError(f"verb name {verb_name!r} is reserved by beheaxi")
        if any(v.name == verb_name for v in self._verbs):
            raise ValueError(f"verb {verb_name!r} is already registered")
```

- [ ] **Step 4: Run the full suite plus the gates**

Run: `uv run pytest -q && uv run ruff check . && uv run mypy`
Expected: all pass. (`tests/example_app.py`'s `greet`/`boom` and the CLI's `conformance` are valid.)

- [ ] **Step 5: Commit**

```bash
git add src/beheaxi/app.py tests/test_app.py
git commit -m "fix: validate verb names at registration; reserve describe (S4)

Rejects malformed, underscore-bearing (divergence #5), duplicate and reserved
names. @app.command(name='describe') used to silently replace the manifest verb.

```

---

### Task 6: Truthful manifest types and shapes (B3, B3a)

**Files:**
- Modify: `src/beheaxi/describe.py` (whole file)
- Modify: `src/beheaxi/app.py` (`Verb` dataclass, `command`, `describe` wiring)
- Create: `tests/test_describe_types.py`

**Interfaces:**
- Produces: `describe.arg_entries(fn: Callable[..., Any]) -> list[dict[str, Any]]` (raises `ValueError`) and `describe.arg_entry(param: inspect.Parameter, hint: Any) -> dict[str, Any]`. `Verb.params: list[Any]` is **replaced** by `Verb.args: list[dict[str, Any]]`. `build_manifest(app)` keeps its signature.

- [ ] **Step 1: Write the failing tests — create `tests/test_describe_types.py`**

```python
"""describe types under PEP 563 — the harness-wide `from __future__ import annotations`."""
from __future__ import annotations

import enum
import json
from pathlib import Path
from typing import Annotated, Optional

import jsonschema
import pytest
import typer

from beheaxi.app import BeheaxiApp
from beheaxi.describe import build_manifest

SCHEMA = json.loads(Path("src/beheaxi/manifest_schema.json").read_text())


class Color(enum.Enum):
    RED = "red"
    BLUE = "blue"


def make_app() -> BeheaxiApp:
    app = BeheaxiApp(name="future", version="0.0.1", summary="Postponed annotations.")

    @app.command()
    def typed(
        count: int,
        ratio: float = 1.0,
        flag: bool = False,
        maybe: int | None = None,
        legacy: Optional[int] = None,
        tags: list[str] | None = None,
        where: Path = Path("."),
        color: Color = Color.RED,
        top: Annotated[int, typer.Option("--limit", "-n")] = 5,
        old_style: int = typer.Option(3, "--old"),
    ) -> None:
        """Every annotation shape describe must resolve."""
        app.emit({"count": count, "top": top, "old": old_style})

    return app


def args_of(app: BeheaxiApp) -> dict[str, dict]:
    verb = next(v for v in build_manifest(app)["verbs"] if v["name"] == "typed")
    return {a["name"]: a for a in verb["args"]}


def test_postponed_annotations_resolve_to_real_types():
    args = args_of(make_app())
    assert args["count"] == {"name": "count", "type": "integer", "required": True}
    assert args["--ratio"]["type"] == "number"
    assert args["--flag"]["type"] == "boolean"
    assert args["--maybe"]["type"] == "integer"
    assert args["--legacy"]["type"] == "integer"
    assert args["--tags"]["type"] == "array"
    assert args["--where"]["type"] == "string"
    assert args["--color"] == {
        "name": "--color", "type": "string", "required": False, "enum": ["red", "blue"]
    }


def test_custom_option_declarations_name_the_flag():
    args = args_of(make_app())
    assert args["--limit"] == {"name": "--limit", "type": "integer", "required": False}
    assert args["--old"] == {"name": "--old", "type": "integer", "required": False}
    assert "--top" not in args and "--old-style" not in args


def test_manifest_validates_and_the_verb_still_runs(capsys):
    app = make_app()
    jsonschema.validate(build_manifest(app), SCHEMA)
    assert app.main(["typed", "4", "--limit", "2", "--old", "9", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {"count": 4, "top": 2, "old": 9}


def test_required_option_is_rejected():
    app = BeheaxiApp(name="x", version="0", summary="x")

    def must(name: Annotated[str, typer.Option()]) -> None:
        """Required option."""

    with pytest.raises(ValueError, match="required option"):
        app.command()(must)


def test_old_style_required_option_is_rejected():
    app = BeheaxiApp(name="x", version="0", summary="x")

    def strict(level: int = typer.Option(..., "--level")) -> None:
        """Required option, old style."""

    with pytest.raises(ValueError, match="required option"):
        app.command()(strict)


def test_optional_positional_is_rejected():
    app = BeheaxiApp(name="x", version="0", summary="x")

    def opt(target: Annotated[str, typer.Argument()] = "here") -> None:
        """Optional positional."""

    with pytest.raises(ValueError, match="optional positional"):
        app.command()(opt)


def test_unresolvable_annotation_is_rejected():
    app = BeheaxiApp(name="x", version="0", summary="x")

    def broken(x: NoSuchType) -> None:  # noqa: F821 - deliberately undefined
        """Broken."""

    with pytest.raises(ValueError, match="cannot resolve"):
        app.command()(broken)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest -q tests/test_describe_types.py`
Expected: the type and name tests FAIL (everything is reported as `"string"`, with names `--top`/`--old-style`), and all 4 rejection tests FAIL ("DID NOT RAISE"). `test_manifest_validates_and_the_verb_still_runs` may already pass.

- [ ] **Step 3: Implement — replace `src/beheaxi/describe.py` entirely**

```python
"""Introspect verb signatures into describe --json manifest entries.

Arg entries are computed once, at registration (`BeheaxiApp.command`), so a signature the
manifest cannot express truthfully fails at import time instead of shipping a manifest that
lies to beherouter.
"""
from __future__ import annotations

import inspect
import types
import typing
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, get_args, get_origin

from typer.models import ArgumentInfo, ParameterInfo

if TYPE_CHECKING:
    from .app import BeheaxiApp

_SCALARS: dict[Any, str] = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    Path: "string",
}
_ARRAYS = (list, tuple, set, frozenset)


def _unwrap(annotation: Any) -> tuple[Any, ParameterInfo | None]:
    """Strip Annotated[...] (keeping typer Argument/Option metadata) and Optional[...]."""
    info: ParameterInfo | None = None
    if get_origin(annotation) is typing.Annotated:
        base, *meta = get_args(annotation)
        info = next((m for m in meta if isinstance(m, ParameterInfo)), None)
        annotation = base
    if get_origin(annotation) in (typing.Union, types.UnionType):
        members = [a for a in get_args(annotation) if a is not type(None)]
        if len(members) == 1:
            annotation = members[0]
    return annotation, info


def _type_of(annotation: Any) -> tuple[str, list[str] | None]:
    if annotation in _ARRAYS or get_origin(annotation) in _ARRAYS:
        return "array", None
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        return "string", [str(e.value) for e in annotation]
    return _SCALARS.get(annotation, "string"), None


def _option_name(param_name: str, decls: tuple[str, ...]) -> str:
    """The first `--long` declaration (`--force/--no-force` -> `--force`), else Typer's
    default `--param-name`."""
    for decl in decls:
        first = decl.split("/")[0].strip()
        if first.startswith("--"):
            return first
    return f"--{param_name.replace('_', '-')}"


def arg_entry(param: inspect.Parameter, hint: Any) -> dict[str, Any]:
    """One manifest arg entry. Raises ValueError for shapes the manifest cannot express."""
    annotation, info = _unwrap(hint)
    default: Any = param.default
    decls: tuple[str, ...] = ()
    if isinstance(default, ParameterInfo):  # old style: `x: int = typer.Option(5, "--x")`
        info, default = default, default.default
        decls = tuple(getattr(info, "param_decls", None) or ())
    elif info is not None:
        decls = tuple(getattr(info, "param_decls", None) or ())
        # Annotated style: Typer reads a str first argument as a declaration, so
        # Annotated[int, typer.Option("--limit", "-n")] stores "--limit" as `default`.
        if isinstance(info.default, str):
            decls = (info.default, *decls)
    required = default is inspect.Parameter.empty or default is ...
    positional = isinstance(info, ArgumentInfo) or (info is None and required)
    if positional != required:
        shape = "a required option" if required else "an optional positional argument"
        raise ValueError(
            f"parameter {param.name!r} is {shape}: the describe manifest marks required args "
            "as positional and optional args as --flags (beherouter builds argv that way), "
            "so make it a plain positional with no default, or an option with a default"
        )
    name = param.name if positional else _option_name(param.name, decls)
    typ, enum = _type_of(annotation)
    entry: dict[str, Any] = {"name": name, "type": typ, "required": required}
    if enum is not None:
        entry["enum"] = enum
    return entry


def arg_entries(fn: Callable[..., Any]) -> list[dict[str, Any]]:
    """Manifest arg entries for a verb function, in signature order."""
    try:
        # Resolves string annotations: under `from __future__ import annotations` (used
        # across the harness) every annotation is a str that _type_of cannot map.
        hints = typing.get_type_hints(fn, include_extras=True)
    except Exception as e:  # noqa: BLE001 - NameError/TypeError from unresolvable refs
        raise ValueError(
            f"cannot resolve the annotations of verb function {fn.__name__!r}: {e}. "
            "Define referenced types before the verb."
        ) from e
    return [
        arg_entry(p, hints.get(p.name, p.annotation))
        for p in inspect.signature(fn).parameters.values()
        if p.name != "self"
    ]


def build_manifest(app: BeheaxiApp) -> dict[str, Any]:
    verbs = [
        {
            "name": v.name,
            "summary": v.summary,
            "args": v.args,
            "pinned": v.pinned,
            "mutating": v.mutating,
        }
        for v in app._verbs
    ]
    return {"tool": app.name, "version": app.version, "summary": app.summary, "verbs": verbs}
```

- [ ] **Step 4: Implement — wire it into `src/beheaxi/app.py`**

1. Add `from .describe import arg_entries, build_manifest` to the module imports (after the `.context` import). describe imports `app` only under `TYPE_CHECKING`, so there is no import cycle.
2. In the `Verb` dataclass, replace `    params: list[Any]` with `    args: list[dict[str, Any]]`.
3. In `__init__`, delete only the line `        from . import describe as _describe` (keep the comment block above it, which still describes the auto-registered `describe` command). Inside `_describe_cmd`, change `self.emit(_describe.build_manifest(self))` to `self.emit(build_manifest(self))`.
4. In `command`'s `deco`, replace the `self._verbs.append(Verb(...))` call with:

```python
            args = arg_entries(fn)  # raises ValueError for unexpressible shapes (B3a)
            self._verbs.append(Verb(verb_name, summary, args, pinned, mutating))
```

- [ ] **Step 5: Run the full suite plus the gates**

Run: `uv run pytest -q && uv run ruff check . && uv run mypy`
Expected: all pass. The pre-existing `tests/test_describe.py` assertions still hold.

- [ ] **Step 6: Commit**

```bash
git add src/beheaxi/describe.py src/beheaxi/app.py tests/test_describe_types.py
git commit -m "fix: resolve real manifest types and reject shapes it cannot express

describe now resolves postponed annotations, Optional/Union and Annotated, and
honours custom --option declarations (B3). Required options and optional
positionals raise at registration: beherouter renders required => positional,
so the manifest could not describe them truthfully (B3a).

```

---

### Task 7: Conformance runner that never crashes; no inherited secrets (B8, S5)

**Files:**
- Modify: `src/beheaxi/conformance/checks.py` (whole file)
- Modify: `src/beheaxi/conformance/runner.py` (whole file)
- Create: `tests/fake_tool.py`
- Modify: `tests/test_conformance.py`

**Interfaces:**
- Produces: `checks.Runner` (Protocol with `run(args: list[str]) -> tuple[int, str, str]`); every check is now `check(tool: Runner) -> CheckResult`; `checks.BOGUS = "definitely-not-a-command"`. In `runner`: `ToolRunner(cmd: list[str], env: dict[str, str] | None = None, timeout: float = 30.0)` with `.run`; `scrubbed_env(environ: Mapping[str, str]) -> dict[str, str]`; `run_conformance(cmd, *, inherit_env: bool = False, timeout: float = TIMEOUT_S) -> Report`; constants `TIMEOUT_S`, `EXIT_TIMEOUT = 124`, `EXIT_NOT_EXECUTABLE = 126`, `EXIT_NOT_FOUND = 127`, `SECRET_ENV`.

- [ ] **Step 1: Create the fixture `tests/fake_tool.py`**

```python
"""A hand-rolled (non-beheaxi) CLI whose single defect is chosen by FAKE_TOOL_MODE.

Each conformance test sets one mode and asserts that exactly the matching check fails,
proving every check catches its defect without tripping the others. Modes:
  ""               well-behaved: passes every check
  empty_manifest   `describe` prints {}
  hang             sleeps past any timeout
  colorful         colours its dashboard on a TTY even under --no-color   (Task 8)
  plain_error      usage errors are plain text, not a JSON envelope        (Task 8)
"""
import json
import os
import sys
import time

MODE = os.environ.get("FAKE_TOOL_MODE", "")
MANIFEST = {"tool": "fake", "version": "0", "summary": "Fake tool.", "verbs": []}


def main() -> int:
    if MODE == "hang":
        time.sleep(60)
    args = [a for a in sys.argv[1:] if a not in ("--json", "--no-color")]
    if args == ["describe"]:
        print("{}" if MODE == "empty_manifest" else json.dumps(MANIFEST))
        return 0
    if not args:
        colour = MODE == "colorful" and sys.stdout.isatty()
        print("\x1b[1mfake\x1b[0m" if colour else "fake")
        return 0
    if MODE == "plain_error":
        print("error: no such command", file=sys.stderr)
    else:
        envelope = {"error": {"type": "usage", "title": "No such command.", "code": 2}}
        print(json.dumps(envelope), file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Write the failing tests**

Replace `tests/test_conformance.py` with:

```python
import sys

import pytest

from beheaxi.conformance.checks import ALL_CHECKS
from beheaxi.conformance.runner import ToolRunner, run_conformance, scrubbed_env

EXAMPLE = [sys.executable, "tests/example_app.py"]
BROKEN = [sys.executable, "tests/broken_app.py"]
FAKE = [sys.executable, "tests/fake_tool.py"]


def run_fake(monkeypatch, mode, **kwargs):
    monkeypatch.setenv("FAKE_TOOL_MODE", mode)
    return run_conformance(FAKE, **kwargs)


def failed(report):
    return {c.name for c in report.failures}


def test_compliant_app_passes():
    report = run_conformance(EXAMPLE)
    assert report.ok, report.failures
    assert {c.name for c in report.checks} >= {
        "describe_schema", "pinned_verbs", "json_parseable", "no_color",
        "usage_exit_2", "dashboard",
    }


def test_broken_app_fails_the_right_check():
    report = run_conformance(BROKEN)
    assert not report.ok
    assert any(c.name == "describe_schema" and not c.passed for c in report.checks)


def test_well_behaved_fake_tool_passes(monkeypatch):
    report = run_fake(monkeypatch, "")
    assert report.ok, report.failures


def test_malformed_manifest_fails_checks_without_crashing(monkeypatch):
    report = run_fake(monkeypatch, "empty_manifest")
    assert failed(report) == {"describe_schema", "pinned_verbs"}
    pinned = next(c for c in report.checks if c.name == "pinned_verbs")
    assert "no list of verb objects" in pinned.detail


def test_missing_binary_fails_every_check_without_crashing():
    report = run_conformance(["definitely-not-an-installed-binary-xyz"])
    assert not report.ok and len(report.checks) == len(ALL_CHECKS)
    usage = next(c for c in report.checks if c.name == "usage_exit_2")
    assert usage.detail == "got exit 127"


def test_hanging_tool_times_out_per_run(monkeypatch):
    report = run_fake(monkeypatch, "hang", timeout=0.5)
    assert not report.ok
    assert next(c for c in report.checks if c.name == "dashboard").detail == "exit 124"


def test_a_crashing_check_fails_only_itself(monkeypatch):
    def explodes(tool):
        raise RuntimeError("kaboom")

    monkeypatch.setattr("beheaxi.conformance.runner.ALL_CHECKS", [explodes, *ALL_CHECKS])
    report = run_conformance(EXAMPLE)
    assert failed(report) == {"explodes"}
    assert "kaboom" in report.failures[0].detail


def test_secrets_are_scrubbed_from_the_target_env(monkeypatch):
    monkeypatch.setenv("BEHELIB_API_TOKEN", "s3cret")
    seen = []
    real_run = ToolRunner.run

    def spy(self, args):
        seen.append(self.env)
        return real_run(self, args)

    monkeypatch.setattr(ToolRunner, "run", spy)
    run_conformance(EXAMPLE)
    assert seen and all("BEHELIB_API_TOKEN" not in env and "PATH" in env for env in seen)


def test_inherit_env_passes_the_environment_through(monkeypatch):
    seen = []
    real_run = ToolRunner.run

    def spy(self, args):
        seen.append(self.env)
        return real_run(self, args)

    monkeypatch.setattr(ToolRunner, "run", spy)
    run_conformance(EXAMPLE, inherit_env=True)
    assert seen and all(env is None for env in seen)


@pytest.mark.parametrize(
    "name",
    ["GITHUB_TOKEN", "BEHELIB_API_KEY", "db_password", "AWS_SECRET_ACCESS_KEY",
     "BEARER", "SSH_AUTH_SOCK", "BEHEROUTER_PRIVATE_KEY", "OAUTH_CLIENT_CREDENTIALS"],
)
def test_secretish_names_are_scrubbed(name):
    env = scrubbed_env({name: "x", "PATH": "/bin", "HOME": "/h"})
    assert name not in env and env == {"PATH": "/bin", "HOME": "/h"}
```

- [ ] **Step 3: Run them to verify they fail**

Run: `uv run pytest -q tests/test_conformance.py`
Expected: `ImportError` (`ToolRunner`, `scrubbed_env`), so the module errors.

- [ ] **Step 4: Implement — replace `src/beheaxi/conformance/checks.py` entirely**

```python
"""Individual black-box conformance checks.

Each check takes a `Runner` and returns a CheckResult. The checks exercise the tool's REAL
shipped binary as a subprocess, the same surface beherouter uses, so a passing tool is
AXI-compliant by the contract beherouter builds against.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol

import jsonschema

ANSI = re.compile(r"\x1b\[")
SCHEMA = json.loads((Path(__file__).resolve().parents[1] / "manifest_schema.json").read_text())
BOGUS = "definitely-not-a-command"


class Runner(Protocol):
    def run(self, args: list[str]) -> tuple[int, str, str]:
        """(returncode, stdout, stderr), with stdout/stderr piped."""
        ...


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""


def describe_schema(tool: Runner) -> CheckResult:
    code, out, _ = tool.run(["describe", "--json"])
    if code != 0:
        return CheckResult("describe_schema", False, f"exit {code}")
    try:
        jsonschema.validate(json.loads(out), SCHEMA)
    except Exception as e:  # noqa: BLE001
        return CheckResult("describe_schema", False, str(e)[:200])
    return CheckResult("describe_schema", True)


def pinned_verbs(tool: Runner) -> CheckResult:
    _, out, _ = tool.run(["describe", "--json"])
    try:
        manifest: Any = json.loads(out)
    except ValueError:
        return CheckResult("pinned_verbs", False, "describe output not JSON")
    verbs = manifest.get("verbs") if isinstance(manifest, dict) else None
    if not isinstance(verbs, list) or not all(isinstance(v, dict) for v in verbs):
        return CheckResult("pinned_verbs", False, "manifest has no list of verb objects")
    bad = [
        v.get("name", "?")
        for v in verbs
        if v.get("pinned") and (not v.get("summary") or "args" not in v)
    ]
    return CheckResult("pinned_verbs", not bad, f"incomplete: {bad}" if bad else "")


def json_parseable(tool: Runner) -> CheckResult:
    _, out, _ = tool.run(["--json", "describe"])  # flag BEFORE subcommand too
    try:
        json.loads(out)
    except ValueError:
        return CheckResult("json_parseable", False, "stdout not JSON with --json before subcommand")
    return CheckResult("json_parseable", True)


def no_color(tool: Runner) -> CheckResult:
    _, out, _ = tool.run(["--no-color", "describe"])
    has_ansi = bool(ANSI.search(out))
    return CheckResult("no_color", not has_ansi, "ANSI present" if has_ansi else "")


def usage_exit_2(tool: Runner) -> CheckResult:
    code, _, _ = tool.run([BOGUS])
    return CheckResult("usage_exit_2", code == 2, f"got exit {code}")


def dashboard(tool: Runner) -> CheckResult:
    code, out, _ = tool.run([])
    return CheckResult("dashboard", code == 0 and out.strip() != "", f"exit {code}")


ALL_CHECKS: list[Callable[[Runner], CheckResult]] = [
    describe_schema,
    pinned_verbs,
    json_parseable,
    no_color,
    usage_exit_2,
    dashboard,
]
```

- [ ] **Step 5: Implement — replace `src/beheaxi/conformance/runner.py` entirely**

```python
"""Orchestrate the black-box conformance checks against a tool's real binary."""
from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Callable

from .checks import ALL_CHECKS, CheckResult, Runner

TIMEOUT_S = 30.0
# Shell conventions, so a launch failure reads like one in the report.
EXIT_TIMEOUT = 124
EXIT_NOT_EXECUTABLE = 126
EXIT_NOT_FOUND = 127

# Conformance probes structure, never data, so the tool under test gets no credentials.
# Matched case-insensitively against variable NAMES.
SECRET_ENV = re.compile(
    r"TOKEN|SECRET|PASSW(OR)?D|API_?KEY|CREDENTIAL|PRIVATE_?KEY|BEARER|AUTH", re.IGNORECASE
)


def scrubbed_env(environ: Mapping[str, str]) -> dict[str, str]:
    """`environ` minus every variable whose name looks like it holds a credential."""
    return {k: v for k, v in environ.items() if not SECRET_ENV.search(k)}


@dataclass
class Report:
    checks: list[CheckResult]

    @property
    def ok(self) -> bool:
        return all(c.passed for c in self.checks)

    @property
    def failures(self) -> list[CheckResult]:
        return [c for c in self.checks if not c.passed]


@dataclass
class ToolRunner:
    """Runs the tool under test. Every launch failure becomes a result, never an exception."""

    cmd: list[str]
    env: dict[str, str] | None = None
    timeout: float = TIMEOUT_S

    def run(self, args: list[str]) -> tuple[int, str, str]:
        try:
            p = subprocess.run(
                self.cmd + args,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                env=self.env,
                stdin=subprocess.DEVNULL,
            )
        except subprocess.TimeoutExpired:
            return EXIT_TIMEOUT, "", f"timed out after {self.timeout:g}s"
        except FileNotFoundError as e:
            return EXIT_NOT_FOUND, "", f"not found: {e.filename}"
        except OSError as e:  # PermissionError, exec format error, ...
            return EXIT_NOT_EXECUTABLE, "", f"cannot execute: {e}"
        return p.returncode, p.stdout, p.stderr


def _guarded(check: Callable[[Runner], CheckResult], tool: Runner) -> CheckResult:
    try:
        return check(tool)
    except Exception as e:  # noqa: BLE001 - a malformed tool must fail ONE check, not the run
        name = getattr(check, "__name__", "check")
        return CheckResult(name, False, f"check crashed: {type(e).__name__}: {e}"[:200])


def run_conformance(
    cmd: list[str], *, inherit_env: bool = False, timeout: float = TIMEOUT_S
) -> Report:
    env = None if inherit_env else scrubbed_env(os.environ)
    tool = ToolRunner(cmd, env=env, timeout=timeout)
    return Report([_guarded(check, tool) for check in ALL_CHECKS])
```

- [ ] **Step 6: Run the full suite plus the gates**

Run: `uv run pytest -q && uv run ruff check . && uv run mypy && uv run beheaxi conformance "beheaxi" --json`
Expected: all pass, and conformance prints `"ok": true`. The hang test takes about 3–4 s.

- [ ] **Step 7: Commit**

```bash
git add src/beheaxi/conformance/ tests/fake_tool.py tests/test_conformance.py
git commit -m "fix: conformance runner never crashes and never leaks secrets

Launch failures map to 124/126/127 results and each check is guarded, so one
malformed target fails one check instead of the run (B8). The target's env is
scrubbed of credential-named variables (S5).

```

---

### Task 8: Stronger checks: a real-TTY `no_color` and `json_error_envelope` (I2, B10 end-to-end)

**Files:**
- Modify: `src/beheaxi/conformance/checks.py` (`Runner`, `no_color`, new `json_error_envelope`, `ALL_CHECKS`)
- Modify: `src/beheaxi/conformance/runner.py` (`ToolRunner.run_tty`, imports)
- Modify: `tests/test_conformance.py`

**Interfaces:**
- Consumes: Task 7's `ToolRunner`, `Runner`, `BOGUS`, and Task 1's `color_system=None` (otherwise the example app fails on a TTY).
- Produces: `Runner.run_tty(args: list[str]) -> tuple[int, str] | None` (stdout and stderr combined; `None` where ptys don't exist) and a 7th check, `json_error_envelope`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_conformance.py` (add `import os` to the imports), and add `"json_error_envelope"` to the expected set in
`test_compliant_app_passes`:

```python
POSIX_ONLY = pytest.mark.skipif(sys.platform == "win32", reason="needs a pseudo-terminal")


@POSIX_ONLY
def test_colour_on_a_real_tty_is_caught(monkeypatch):
    report = run_fake(monkeypatch, "colorful")
    assert failed(report) == {"no_color"}
    assert "TTY" in report.failures[0].detail


def test_plain_text_usage_errors_fail_the_envelope_check(monkeypatch):
    report = run_fake(monkeypatch, "plain_error")
    assert failed(report) == {"json_error_envelope"}


@POSIX_ONLY
def test_beheaxi_apps_are_escape_free_on_a_tty():
    env = {k: v for k, v in os.environ.items() if k not in ("NO_COLOR", "FORCE_COLOR")}
    tool = ToolRunner(EXAMPLE, env={**env, "TERM": "xterm-256color"})
    for args in (["--no-color"], ["--no-color", "describe"]):
        result = tool.run_tty(args)
        assert result is not None
        code, out = result
        assert code == 0 and out.strip() and "\x1b" not in out
    # ...and the pty is real: without the flag the same dashboard IS styled.
    plain = tool.run_tty([])
    assert plain is not None and "\x1b[" in plain[1]
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest -q tests/test_conformance.py`
Expected: `colorful` FAILs (no failures: the piped check can't see TTY colour), `plain_error` FAILs (no such check), the TTY test errors (`AttributeError: run_tty`), and `test_compliant_app_passes` FAILs (missing `json_error_envelope`).

- [ ] **Step 3: Implement — `run_tty` in `src/beheaxi/conformance/runner.py`**

Add `import time` to the imports, and add this method to `ToolRunner` after `run`:

```python
    def run_tty(self, args: list[str]) -> tuple[int, str] | None:
        """Run with stdout+stderr on a pseudo-terminal: (returncode, combined output).

        A TTY is where colour actually switches on, so it is the only honest place to test
        --no-color — pipes are never TTYs. Returns None where ptys do not exist (Windows).
        """
        try:
            import pty
            import select
        except ImportError:  # pragma: no cover - non-POSIX
            return None
        master, slave = pty.openpty()
        try:
            try:
                proc = subprocess.Popen(
                    self.cmd + args,
                    stdin=subprocess.DEVNULL,
                    stdout=slave,
                    stderr=slave,
                    env=self.env,
                )
            except FileNotFoundError as e:
                return EXIT_NOT_FOUND, f"not found: {e.filename}"
            except OSError as e:
                return EXIT_NOT_EXECUTABLE, f"cannot execute: {e}"
            finally:
                os.close(slave)  # the child holds its own copy
            chunks: list[bytes] = []
            deadline = time.monotonic() + self.timeout
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    proc.kill()
                    proc.wait()
                    return EXIT_TIMEOUT, f"timed out after {self.timeout:g}s"
                ready, _, _ = select.select([master], [], [], min(remaining, 0.25))
                if not ready:
                    continue
                try:
                    data = os.read(master, 4096)
                except OSError:  # EIO: how Linux reports the child closing the pty
                    break
                if not data:  # EOF: how macOS reports it
                    break
                chunks.append(data)
        finally:
            os.close(master)
        return proc.wait(), b"".join(chunks).decode(errors="replace")
```

- [ ] **Step 4: Implement — the checks in `src/beheaxi/conformance/checks.py`**

1. Replace `ANSI = re.compile(r"\x1b\[")` with
   `ESC = re.compile("\x1b")  # any escape byte: CSI colours and OSC titles/hyperlinks alike`.
2. Add to the `Runner` protocol, after `run`:

```python
    def run_tty(self, args: list[str]) -> tuple[int, str] | None:
        """(returncode, combined output) on a pseudo-terminal; None where unsupported."""
        ...
```

3. Replace the whole `no_color` function with:

```python
def no_color(tool: Runner) -> CheckResult:
    """--no-color must yield zero escape bytes, piped AND on a real TTY: the TTY is where
    colour actually switches on (and where Rich's own no_color still emits bold)."""
    for args in (["--no-color"], ["--no-color", "describe"]):
        _, out, err = tool.run(args)
        if ESC.search(out) or ESC.search(err):
            return CheckResult("no_color", False, f"escape codes in piped output of {args}")
        tty = tool.run_tty(args)
        if tty is not None and ESC.search(tty[1]):
            return CheckResult("no_color", False, f"escape codes on a TTY with {args}")
    return CheckResult("no_color", True)
```

4. Add after `dashboard`:

```python
def json_error_envelope(tool: Runner) -> CheckResult:
    """In --json mode an error leaves stdout empty and puts one envelope on stderr whose
    `code` equals the exit code."""
    name = "json_error_envelope"
    code, out, err = tool.run(["--json", BOGUS])
    if out.strip():
        return CheckResult(name, False, "stdout not empty on error")
    try:
        body: Any = json.loads(err)["error"]
    except (ValueError, KeyError, TypeError):
        return CheckResult(name, False, "stderr is not a JSON error envelope")
    if not isinstance(body, dict) or body.get("type") != "usage" or body.get("code") != code:
        return CheckResult(name, False, f"envelope {body!r:.100} does not match exit {code}")
    return CheckResult(name, True)
```

5. Append `json_error_envelope,` to `ALL_CHECKS`.

- [ ] **Step 5: Run the full suite plus the gates**

Run: `uv run pytest -q && uv run ruff check . && uv run mypy && uv run beheaxi conformance "beheaxi" --json`
Expected: all pass, and the conformance report lists 7 checks with `"ok": true`.

- [ ] **Step 6: Commit**

```bash
git add src/beheaxi/conformance/ tests/test_conformance.py
git commit -m "feat: probe --no-color on a real TTY; add json_error_envelope check

no_color now inspects stdout+stderr of the dashboard and describe, piped and
under a pseudo-terminal, where colour actually switches on (I2, B10). The new
json_error_envelope check asserts the --json error contract end to end.

```

---

### Task 9: beheaxi's own CLI: real version, domain exit 10, `--inherit-env` (B9, I1)

**Files:**
- Modify: `src/beheaxi/errors.py` (add a constant after `ExitCode`)
- Modify: `src/beheaxi/__init__.py`
- Modify: `src/beheaxi/cli.py` (whole file)
- Create: `tests/test_cli.py`

**Interfaces:**
- Consumes: Task 7's `run_conformance(cmd, *, inherit_env=...)`.
- Produces: `errors.DOMAIN_EXIT_FLOOR = 10` (also exported from `beheaxi`), `cli.EXIT_NONCONFORMANT = DOMAIN_EXIT_FLOOR`.

- [ ] **Step 1: Write the failing tests — create `tests/test_cli.py`**

```python
import json
import shlex
import sys
from importlib.metadata import version

from beheaxi import DOMAIN_EXIT_FLOOR
from beheaxi.cli import EXIT_NONCONFORMANT, app
from beheaxi.describe import build_manifest


def test_version_comes_from_the_installed_distribution():
    assert app.version == version("beheaxi")


def test_nonconformant_target_exits_with_the_domain_code(capsys):
    target = shlex.join([sys.executable, "tests/broken_app.py"])
    code = app.main(["conformance", target, "--json"])
    assert code == EXIT_NONCONFORMANT == DOMAIN_EXIT_FLOOR == 10
    assert json.loads(capsys.readouterr().out)["ok"] is False


def test_conformant_target_exits_zero(capsys):
    target = shlex.join([sys.executable, "tests/example_app.py"])
    assert app.main(["conformance", target, "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["ok"] is True and len(report["checks"]) == 7


def test_inherit_env_flag_is_advertised():
    verb = next(v for v in build_manifest(app)["verbs"] if v["name"] == "conformance")
    assert {"name": "--inherit-env", "type": "boolean", "required": False} in verb["args"]
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest -q tests/test_cli.py`
Expected: `ImportError` (`DOMAIN_EXIT_FLOOR`, `EXIT_NONCONFORMANT`).

- [ ] **Step 3: Implement**

In `src/beheaxi/errors.py`, directly after the `ExitCode` class, add:

```python
# beheaxi owns exit codes 0-9 (ExitCode uses 0-6; 7-9 are held for future framework
# classes). A tool's own domain codes start here — CONVENTIONS.md §2.
DOMAIN_EXIT_FLOOR = 10
```

In `src/beheaxi/__init__.py`, add `DOMAIN_EXIT_FLOOR,` to the `from .errors import (...)` list and
`"DOMAIN_EXIT_FLOOR",` to `__all__` (after `"ExitCode"`).

Replace `src/beheaxi/cli.py` entirely with:

```python
"""beheaxi's own CLI, built on BeheaxiApp (dogfooding the standard)."""
from __future__ import annotations

import shlex
from importlib.metadata import version

from .app import BeheaxiApp
from .conformance.runner import run_conformance
from .errors import DOMAIN_EXIT_FLOOR

# Domain exit code (CONVENTIONS §2: beheaxi owns 0-9, tools own >= 10): the target ran and
# failed checks. Distinct from 1, which means the conformance run itself crashed.
EXIT_NONCONFORMANT = DOMAIN_EXIT_FLOOR

app = BeheaxiApp(
    name="beheaxi",
    version=version("beheaxi"),
    summary="Shared CLI/AXI framework for the BEHEMOTION harness.",
)


@app.command(pinned=True, mutating=False)
def conformance(target: str, inherit_env: bool = False) -> None:
    """Run the AXI conformance suite against a tool command (e.g. 'behelib' or 'python app.py')."""
    report = run_conformance(shlex.split(target), inherit_env=inherit_env)
    rows = [{"check": c.name, "passed": c.passed, "detail": c.detail} for c in report.checks]
    app.emit({"target": target, "ok": report.ok, "checks": rows})
    if not report.ok:
        raise SystemExit(EXIT_NONCONFORMANT)


def main() -> None:
    raise SystemExit(app.main())


if __name__ == "__main__":  # enables `python -m beheaxi.cli` for the dogfood gate
    main()
```

- [ ] **Step 4: Run the full suite plus the gates**

Run: `uv run pytest -q && uv run ruff check . && uv run mypy && uv run beheaxi conformance "beheaxi" --json`
Expected: all pass; `describe` now reports `"version": "0.1.2"`.
Also run: `uv run beheaxi conformance "python tests/broken_app.py" --json; echo "exit $?"`
Expected: `exit 10`.

- [ ] **Step 5: Commit**

```bash
git add src/beheaxi/errors.py src/beheaxi/__init__.py src/beheaxi/cli.py tests/test_cli.py
git commit -m "feat: conformance exits 10 on failed checks; version from metadata

Adds DOMAIN_EXIT_FLOOR = 10 (CONVENTIONS §2, divergence #1) and uses it for a
nonconformant target, so 1 keeps meaning 'the runner crashed' (I1). The CLI
version is read from package metadata instead of a drifted literal (B9).
Adds --inherit-env to opt out of secret scrubbing.

```

---

### Task 10: Dependency floor and CI hardening (I3, S6)

**Files:**
- Modify: `pyproject.toml` (`dependencies`)
- Modify: `uv.lock` (regenerated)
- Modify: `.github/workflows/ci.yml` (whole file)
- Create: `.github/dependabot.yml`

**Interfaces:** None in code. The floor becomes `typer>=0.13.1`.

- [ ] **Step 1: Prove the current floor is broken (the "failing test")**

```bash
S="$(mktemp -d)"
uv venv -q --python 3.12 "$S/min"
uv pip install -q --python "$S/min" --resolution lowest-direct -e . "pytest>=8"
"$S/min/bin/python" -m pytest -q -p no:cacheprovider
```

Expected: FAIL. With typer 0.12.0 and click 8.5, bool flags raise "Secondary flag is not valid for non-boolean flag". If it unexpectedly passes, note the resolved versions (`uv pip list --python "$S/min"`) in the commit message and continue.

- [ ] **Step 2: Raise the floor**

In `pyproject.toml`, change `"typer>=0.12"` to `"typer>=0.13.1"`, then run `uv lock`.
Re-run Step 1's install and test commands in a fresh `mktemp -d`.
Expected: all tests PASS at the floors (typer 0.13.1, rich 13.7.0, jsonschema 4.21.0). Also run
`"$S/min/bin/beheaxi" conformance "$S/min/bin/beheaxi" --json`. Expected: `"ok": true`.

If typer 0.13.1 fails a test added by Tasks 1–9 (for example the `functools.wraps` wrapper or `typer.models` imports), bisect upward (`0.14.0`, `0.15.0`, …) with `uv pip install --python "$S/min" "typer==X"`, set the floor to the first passing version, and update the spec's Global Constraints and I3 to match.

- [ ] **Step 3: Replace `.github/workflows/ci.yml`**

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:

# Least privilege: no job writes anything.
permissions:
  contents: read

jobs:
  check:
    name: check (py${{ matrix.python }})
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        python: ["3.12", "3.13"]
    env:
      UV_PYTHON: ${{ matrix.python }}
      UV_LOCKED: "1"  # fail on a stale uv.lock instead of silently re-resolving
    steps:
      # Actions are pinned to full commit SHAs: tags are mutable. Dependabot bumps them.
      - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4.4.0
        with:
          persist-credentials: false

      - name: Install uv
        uses: astral-sh/setup-uv@d4b2f3b6ecc6e67c4457f6d3e41ec42d3d0fcb86 # v5.4.2

      - name: Sync dependencies
        run: uv sync

      - name: Lint (ruff)
        run: uv run ruff check .

      - name: Type-check (mypy --strict)
        run: uv run mypy

      - name: Test (pytest)
        run: uv run pytest -q

      - name: Self-conformance (dogfood)
        # Exits 10 if any AXI check fails, failing this step.
        run: uv run beheaxi conformance "beheaxi" --json

  lowest-deps:
    # The declared floors must really work: typer 0.12 + current click broke every
    # boolean flag while pyproject still claimed typer>=0.12.
    name: lowest direct dependencies (py3.12)
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4.4.0
        with:
          persist-credentials: false

      - name: Install uv
        uses: astral-sh/setup-uv@d4b2f3b6ecc6e67c4457f6d3e41ec42d3d0fcb86 # v5.4.2

      - name: Install at the declared floors
        run: |
          uv venv --python 3.12 .venv-min
          uv pip install --python .venv-min --resolution lowest-direct -e . "pytest>=8"

      - name: Test
        run: .venv-min/bin/python -m pytest -q

      - name: Self-conformance
        run: .venv-min/bin/beheaxi conformance ".venv-min/bin/beheaxi" --json

  audit:
    name: dependency audit
    runs-on: ubuntu-latest
    env:
      UV_LOCKED: "1"
    steps:
      - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4.4.0
        with:
          persist-credentials: false

      - name: Install uv
        uses: astral-sh/setup-uv@d4b2f3b6ecc6e67c4457f6d3e41ec42d3d0fcb86 # v5.4.2

      - name: Export the locked dependency set
        run: uv export --no-hashes --no-emit-project --format requirements-txt -o requirements-audit.txt

      - name: pip-audit
        run: uvx pip-audit==2.10.1 --strict --disable-pip --no-deps -r requirements-audit.txt
```

- [ ] **Step 4: Create `.github/dependabot.yml`**

```yaml
version: 2
updates:
  - package-ecosystem: github-actions
    directory: /
    schedule:
      interval: weekly
  - package-ecosystem: uv
    directory: /
    schedule:
      interval: weekly
```

- [ ] **Step 5: Verify every CI command locally**

```bash
UV_LOCKED=1 uv sync && uv run ruff check . && uv run mypy && uv run pytest -q \
  && uv run beheaxi conformance "beheaxi" --json
UV_PYTHON=3.13 UV_LOCKED=1 uv run --isolated pytest -q
A="$(mktemp -d)"
UV_LOCKED=1 uv export --no-hashes --no-emit-project --format requirements-txt -o "$A/req.txt"
uvx pip-audit==2.10.1 --strict --disable-pip --no-deps -r "$A/req.txt"
uvx --from actionlint-py actionlint .github/workflows/ci.yml
```

Expected: everything passes, and pip-audit reports `No known vulnerabilities found`. If pip-audit reports a real vulnerability, **stop and report it to the user** rather than suppressing it. If the `uvx --from actionlint-py` download is unavailable, skip that line and say so in the task report.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock .github/
git commit -m "ci: pin actions by SHA, least privilege, locked syncs, floor + audit jobs

typer>=0.12 was a false floor: 0.12.x with current click breaks every boolean
flag. Raise it to 0.13.1 and add a lowest-direct job so it cannot drift (I3).
Pin actions to commit SHAs, set contents: read, persist-credentials: false,
UV_LOCKED, a py3.12/3.13 matrix, pip-audit, and Dependabot (S6).

```

---

### Task 11: Docs and version 0.2.0

**Files:**
- Modify: `pyproject.toml` (`version`), `uv.lock`
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-06-21-beheaxi-design.md` (§6, §7, §9, §10, §11)
- Modify: `HARNESS-DIVERGENCES.md` (gitignored: edit it but it is **not** committed)
- Modify: `../docs/HARNESS-PLAN.md` (umbrella repo: edit in-tree and leave it for the umbrella owner to commit)

- [ ] **Step 1: Bump the version**

In `pyproject.toml`, set `version = "0.2.0"`. Run `uv lock && uv sync`, then:
`uv run beheaxi --json describe | python -c 'import json,sys; print(json.load(sys.stdin)["version"])'`
Expected: `0.2.0`. This proves B9 end to end. The editable install's metadata only refreshes on `uv sync`.

- [ ] **Step 2: README**

1. Change the dependency example to `beheaxi @ git+https://github.com/behemotion/beheaxi@v0.2.0`.
2. After the `v0.1.2 is the first release carrying LICENSE…` paragraph, add:

```markdown
### Upgrading to 0.2.0

0.2.0 is a hardening release (spec: `docs/superpowers/specs/2026-10-07-beheaxi-hardening-design.md`).
Things you may notice:

- **Registration is stricter.** `@app.command` raises `ValueError` at import for invalid,
  duplicate or reserved (`describe`) verb names, unresolvable annotations, required options
  and optional positionals — the manifest marks required ⇔ positional, and beherouter builds
  argv from that.
- **The manifest reports real types** (`integer`, `boolean`, `array`, enums) even under
  `from __future__ import annotations`, and uses custom `--option` names.
- **Human output is literal.** Rich markup in emitted strings, error titles and dashboard
  state is no longer interpreted, and terminal control characters are stripped.
- **One JSON document per `--json` run.** A second `app.emit()` is an error; emitting a result
  and then raising an `AxiError` is still fine.
- **Internal errors are redacted.** An uncaught exception reports only its class name; set
  `BEHEAXI_DEBUG=1` to get the traceback in `detail`.
- **Exit codes are honoured.** `typer.Exit(n)` exits `n`; `sys.exit("msg")` exits 1.
- **`beheaxi conformance`** runs 7 checks (adds `json_error_envelope`, and `no_color` now
  probes a real TTY), exits **10** when checks fail, and strips credential-named env vars from
  the target (`--inherit-env` opts out).
- **Domain exit codes** start at `beheaxi.DOMAIN_EXIT_FLOOR` (10); 0–9 belong to beheaxi.

Tags are mutable; for byte-for-byte reproducible builds rely on your `uv.lock`, which records
the resolved commit SHA of the git dependency.
```

- [ ] **Step 3: Amend the original design spec** (`docs/superpowers/specs/2026-06-21-beheaxi-design.md`)

1. **§6, type mapping:** after the sentence ending `` `required` = the
parameter has no default. ``, add:
   "Annotations are resolved with `typing.get_type_hints` (so `from __future__ import annotations` works); `Optional`/`X | None` and `Annotated[...]` are unwrapped; a custom `typer.Option("--name")` declaration names the flag. Because consumers render `required ⇔ positional`, registration rejects required options and optional positionals (hardening spec 2026-10-07, B3a)."
2. **§7, exit-code table:** change `not-found` to `not_found` in the `| 3 |` row (divergence #4). Directly below the table, add:
   "**Domain codes.** beheaxi owns 0–9 (7–9 are held for future framework classes). A tool's own codes start at `DOMAIN_EXIT_FLOOR = 10` (`beheaxi.errors`); CONVENTIONS §2. **Redaction.** Uncaught exceptions render as `internal` with only the exception class name in `detail`; `BEHEAXI_DEBUG=1` adds the traceback. **Verb names** match `^[a-z][a-z0-9]*(-[a-z0-9]+)*$`; `describe` is reserved."
3. **§7, output contract:** after `` `app.emit(data)` serializes-or-renders based on the active `AxiContext`. ``, add: "In `--json` mode a second `emit()` in one run is an error; emit-then-raise is allowed (stdout = result, stderr = envelope). Human output never interprets Rich markup in data and strips terminal control characters; `--no-color`/`NO_COLOR` emit no escape codes at all."
4. **§9:** replace items 3–5 with:
   "3. `<tool> --json describe` is parseable JSON; `<tool> --no-color` (dashboard) and `<tool> --no-color describe` contain zero escape bytes on stdout/stderr, piped **and on a pseudo-terminal**;
   4. no-arg invocation exits 0 and prints non-empty output (the dashboard);
   5. a bogus command exits 2 (usage);
   6. `<tool> --json <bogus>` leaves stdout empty and writes a `usage` envelope to stderr whose `code` equals the exit code (`json_error_envelope`)."
   Then **delete** the `**Optional deeper checks:**` paragraph (divergence #7), and replace `The runner exits 0 (all pass) or non-zero (with a per-check PASS/FAIL report).` with `The runner exits 0 (all pass) or 10 (some check failed), always with a per-check report; credential-named env vars are stripped from the target unless \`--inherit-env\`.`
5. **§10:** change `@v0.1.0` to `@v0.2.0` in the dependency bullet.
6. **§11:** replace the `conformance.scenarios.toml` bullet with: "- Per-tool category checks (`conformance.scenarios.toml`, struck from §9 on 2026-10-07): add only when the first tool needs not-found/auth/conflict/unavailable verification."

- [ ] **Step 4: `HARNESS-DIVERGENCES.md` (local only, gitignored)**

Delete entries **4**, **5** and **7**. Replace entry **1**'s text with:
"1. **Domain exit-code rule — specced, adoption pending.** `DOMAIN_EXIT_FLOOR = 10` is in `src/beheaxi/errors.py` and the design spec §7 (2026-10-07), and `beheaxi conformance` itself uses 10. Remaining: behecheck still reuses `1` for 'findings present'."
Renumber nothing. The numbers are cited elsewhere.

- [ ] **Step 5: Umbrella plan note (`../docs/HARNESS-PLAN.md`, Phase 1 item 3)**

At the end of item 3's paragraph (around line 70–73), append:
"*Progress 2026-10-07:* beheaxi v0.2.0 specs the domain exit-code rule (`DOMAIN_EXIT_FLOOR = 10`) and hardens the CLI profile (spec `beheaxi/docs/superpowers/specs/2026-10-07-beheaxi-hardening-design.md`); the service profile (§3–§6) is still open."
Do **not** commit in the umbrella repo.

- [ ] **Step 6: Full gate, then commit (beheaxi only)**

Run: `uv run ruff check . && uv run mypy && uv run pytest -q && uv run beheaxi conformance "beheaxi" --json`
Expected: all pass.

```bash
git add pyproject.toml uv.lock README.md docs/superpowers/specs/2026-06-21-beheaxi-design.md
git commit -m "docs: release notes and spec amendments for v0.2.0

```

---

### Task 12: Verify beherouter compatibility, then prepare the release

**Files:** none modified in beheaxi or beherouter.

- [ ] **Step 1: Run beherouter's suite against this tree as an overlay (no edits to beherouter)**

```bash
cd ../beherouter
uv run --with-editable ../beheaxi python -c \
  "import beheaxi, importlib.metadata as m; print(beheaxi.__file__, m.version('beheaxi'))"
```

Expected: a path under `.../beheaxi/src/beheaxi/` and `0.2.0`. If it shows beherouter's own `.venv`
copy instead, the overlay did not take precedence. In that case use a throwaway venv:

```bash
V="$(mktemp -d)/br"
uv venv -q "$V" && uv pip install -q --python "$V" -e . && uv pip install -q --python "$V" -e ../beheaxi
uv export --only-group dev --no-hashes --format requirements-txt | uv pip install -q --python "$V" -r -
```

and replace `uv run --with-editable ../beheaxi` with `"$V/bin/"` in the commands below.

- [ ] **Step 2: beherouter tests and conformance**

```bash
uv run --with-editable ../beheaxi pytest -q
uv run --with-editable ../beheaxi beheaxi conformance "beherouter" --json
```

Expected: beherouter's suite passes and conformance is `"ok": true` over 7 checks. Any failure is a
**compatibility break**. Do not patch beherouter. Record the failing test and its output and stop
for the user; the fix belongs in beheaxi or in a `/handoff beherouter`.

- [ ] **Step 3: Return and confirm a clean tree**

```bash
cd ../beheaxi && git status --short && git log --oneline bf19287..HEAD
```

Expected: a clean tree (plus the uncommitted, gitignored `HARNESS-DIVERGENCES.md`) and the 11 task
commits (Tasks 1–11). Task 12 adds no commit.

- [ ] **Step 4: STOP: ask the user before anything outward-facing**

Report the results and ask whether to:
(a) push `main`, (b) create and push tag `v0.2.0`, (c) hand off to beherouter (`/handoff beherouter`)
to bump its pin from `@v0.1.2` to `@v0.2.0`. Do none of these without an explicit yes.

---

## Self-review (done at authoring time)

- **Spec coverage:** S1→T4 · S2,S3→T1 · S4→T5 · S5→T7 · S6→T10 · B1,B2,B4→T4 · B3,B3a→T6 · B5,B6→T2 · B7→T3 · B8→T7 · B9→T9 (+T11 step 1) · B10→T1 (unit) + T8 (TTY e2e) · I1→T9 · I2→T8 · I3→T10 · I4→T4 · divergences #1,#4,#5,#7→T9/T11/T5/T11 · spec §6 acceptance→T11 step 6 + T12.
- **Types and names are consistent across tasks:** `make_console`/`safe_text`/`sanitize` (T1) are used in T1 and T2; `to_json` (T2); `_emitted` (T2) is reset in T4's `main`; `Verb.args` (T6) is read by `build_manifest` (T6); `Runner.run` (T7) + `Runner.run_tty` (T8) are implemented by `ToolRunner`; `run_conformance(..., inherit_env=, timeout=)` (T7) is called by `cli.conformance` (T9); `DOMAIN_EXIT_FLOOR` (T9).
- **Ordering hazards:** T8's TTY test needs T1's `color_system=None`. T6's wrapper interplay was verified with Typer 0.26.7 (`functools.wraps` + postponed annotations + `typer.Exit` all behave). T10 re-verifies everything at the floor.
