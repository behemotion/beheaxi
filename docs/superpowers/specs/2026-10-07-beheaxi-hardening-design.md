# beheaxi v0.2.0 — Hardening Design (security + contract fixes)

> **Status:** approved for implementation · **Date:** 2026-10-07 · **Base:** v0.1.2 (`bf19287`)
> **Implements against:** `2026-06-21-beheaxi-design.md` (amends §5, §7, §9, §11) and
> `../../../../docs/CONVENTIONS.md` §2 (CLI profile).
> **Plan:** `docs/superpowers/plans/2026-10-07-beheaxi-hardening.md`

## 1. Why

A review of v0.1.2 on 2026-10-07 reproduced 6 security gaps and 10 contract bugs. Each one
below was reproduced with a probe app. All of them are silent: the 30-test suite passes and
`beheaxi conformance "beheaxi"` is green. beheaxi is the shared base for every layer CLI and for
beherouter's `cli` backend, so each defect exists in every consumer.

The core problem is that **beheaxi's output is a trust boundary**. beherouter and agents act on
exit codes, parse stdout as exactly one JSON document, and copy stderr into transcripts and logs.
Humans read the Rich rendering in a terminal. At present each of these channels can be corrupted
or made to leak.

## 2. Findings → decisions

IDs are kept stable across the review, this spec, the plan and the handoff.

### Security

| ID | Defect (reproduced) | Decision |
|---|---|---|
| S1 | Uncaught exceptions are rendered as `str(e)`, so `RuntimeError("…postgres://admin:hunter2@…")` reaches stderr in both modes. | Redact. The title is `"Internal error"` and the detail is the exception **class name** plus a hint. The full traceback goes in `detail` only when `BEHEAXI_DEBUG` is set (non-empty). `AxiError` titles and details are author-controlled and stay verbatim. |
| S2 | `err.title`, dashboard state, suggestions and `emit(str)` are parsed as Rich markup, which lets a crafted string inject `[link=…]` (OSC 8 hyperlinks) or restyle output. | Every framework console uses `markup=False, emoji=False`. Framework styling is built from `rich.text.Text` objects, never from markup strings. |
| S3 | Raw control sequences such as OSC 0 (title rewrite), CSI and `\r` pass straight through human output. | `output.sanitize()` strips C0 controls except `\t`/`\n`, DEL, C1, and the bidi overrides/isolates (`U+202A–202E`, `U+2066–2069`, CVE-2021-42574) from every **string** rendered for humans. ~~Containers rendered with Rich `Pretty` are already safe because `repr()` escapes these characters.~~ *Amended in 0.2.1:* `Pretty` copies a custom `__repr__` verbatim, so `emit()` now sanitizes the rendered segments of every non-string value too. |
| S4 | `@app.command(name="describe")` silently replaces the manifest verb. Duplicate and malformed verb names are also accepted. | Validate at registration and raise `ValueError` (a programmer error at import time). A name must match `^[a-z][a-z0-9]*(-[a-z0-9]+)*$`, which forbids underscores and so closes divergence #5. `describe` is reserved, and duplicates are rejected. |
| S5 | `beheaxi conformance` passes the operator's whole environment, tokens included, to the tool under test. | Remove env vars whose **name** matches `TOKEN\|SECRET\|PASSW(OR)?D\|API_?KEY\|CREDENTIAL\|PRIVATE_?KEY\|BEARER\|AUTH` (case-insensitive). Conformance tests structure, not data. Add an `--inherit-env` opt-out. |
| S6 | CI: actions pinned by mutable tag, no `permissions:` block, `uv sync` not `--locked`, no vulnerability audit, no Dependabot. | Pin actions to commit SHAs, set `permissions: contents: read`, use `persist-credentials: false` and `UV_LOCKED=1`, add a `pip-audit` job, and add Dependabot for `github-actions` and `uv`. |

### Contract bugs

| ID | Defect (reproduced) | Decision |
|---|---|---|
| B1 | `raise typer.Exit(code=3)` exits **0**. With `standalone_mode=False`, Click *returns* the code and `main()` discards it. | Register every verb through a wrapper that returns `None`, so any integer that `self._typer(...)` returns can only be an Exit code. `main()` returns that integer. |
| B2 | `sys.exit("fatal")` exits **0** (a non-integer `SystemExit.code` is mapped to OK). | Follow the interpreter: `None` → 0, an `int` → itself, anything else → render as an `internal` error and exit 1. |
| B3 | Every argument is reported as `"string"` under `from __future__ import annotations`, which the whole harness uses. `int \| None`, `Optional`, `Annotated[…, typer.Option("--x")]` and old-style `= typer.Option(…)` are also misreported, and custom option names are ignored. | Resolve types with `typing.get_type_hints(fn, include_extras=True)` **at registration**. Unwrap `Annotated` (keeping any typer `ParameterInfo`) and `Optional`. Honour the first `--long` declaration as the option name. Map list/tuple/set to `array`. If annotations cannot be resolved, raise `ValueError` at registration. Typer would fail the same way at run time anyway. |
| B3a | **The manifest cannot express two parameter shapes.** beherouter renders `required ⇒ positional` (`beherouter/backends/cli.py:48-89`), so a required *option* or an optional *positional* would be invoked with the wrong argv. | **Reject both shapes at registration** with a `ValueError` that explains the rule. This needs no schema change. Making the manifest richer is deferred (§5). |
| B4 | The `status()` hook runs outside `main()`'s `try` block, so a failing hook produces a raw traceback with no envelope. | The dashboard runs inside the same handler as the verbs. |
| B5 | `AxiError(context=…)` with a value that can't be serialised to JSON crashes `render_error`, causing a double traceback and no envelope. | One encoder, `output.to_json()`: `default=str` and `allow_nan=False`. If `render_error` cannot encode `context` (NaN or a circular reference), it drops `context` and keeps the envelope. In `emit()`, NaN raises `AxiError("Output is not valid JSON")`. |
| B6 | Two `emit()` calls in `--json` mode put two documents on stdout. | `BeheaxiApp.emit` raises `AxiError` (internal) on the **second** call in JSON mode, before writing anything. **Emitting and then raising stays legal**: beherouter's `health --deep` and `context-cost` emit records and then raise `Unavailable` so the operator can see which backend failed. |
| B7 | Global flags are removed even after `--`, so a literal `--json` can't be passed as an argument. | Flag extraction stops at the first `--`. The `--` and everything after it pass through unchanged. |
| B8 | One malformed target crashes the whole conformance run: `{}` manifest → `KeyError`, missing binary → `FileNotFoundError`, hang → `TimeoutExpired`. | Every launch failure becomes a result: 124 (timeout), 126 (not executable) or 127 (not found), with a stderr message. Each check runs inside its own guard, so a crash fails **that** check only. `pinned_verbs` validates the shape of the manifest before using it. |
| B9 | `beheaxi describe` reports `0.1.1`. The version is hard-coded and has drifted from the package's 0.1.2. | `version=importlib.metadata.version("beheaxi")`. |
| B10 | **On a real TTY, `--no-color` still emits bold/dim ANSI.** Rich's `no_color=True` drops colour but not styles. Reproduced under a pty: `\x1b[1mdemo\x1b[0m`. The conformance check missed it because subprocess pipes are never TTYs. | Under `--no-color` (or `NO_COLOR` set and non-empty), consoles use `color_system=None`, which emits no escapes at all. |

### Improvements

| ID | Decision |
|---|---|
| I1 | Make `conformance` exit with domain code **10** (`EXIT_NONCONFORMANT`) when checks fail, so "the target was checked and failed" is distinguishable from 1 = "the runner itself crashed". Add the constant `DOMAIN_EXIT_FLOOR = 10` to `errors.py` and export it. This is the code-level half of divergence #1 and matches beherouter's existing `DOMAIN_EXIT_FLOOR`. |
| I2 | Strengthen the conformance suite. `no_color` checks stdout **and** stderr of the dashboard and of `describe`, both piped **and under a pseudo-terminal** (POSIX only; pty runs are skipped where ptys don't exist). It flags any ESC byte. A new check, `json_error_envelope`, verifies that `--json definitely-not-a-command` gives empty stdout and a stderr envelope with `type == "usage"` and `code == exit code`. The suite goes from 6 checks to 7. |
| I3 | Raise the dependency floor to `typer>=0.16.0`. typer 0.12.x with current click (8.5) breaks **every boolean flag** ("Secondary flag is not valid for non-boolean flag"), and `typer>=0.12` is what we declare today. (0.13.1 to 0.15.4 also fail a Task 1-9 test: `test_manifest_validates_and_the_verb_still_runs` exits 2 on `typed 4 --limit 2 --old 9`; 0.16.0 is the first passing version.) Add a CI job that installs `--resolution lowest-direct` so the floor can't drift again, and a Python 3.12/3.13 matrix. |
| I4 | Map `click.Abort` to `internal` with the title `"Aborted"` instead of an empty `"Internal error"`, which matches Click's own exit 1 and message. Click raises `Abort` for Ctrl-C or EOF *anywhere inside a verb*, because its `main()` converts `KeyboardInterrupt`/`EOFError`, and for a declined `confirm(abort=True)`. |

### Housekeeping (from `HARNESS-DIVERGENCES.md`)

- **#4:** Use the underscore spelling (`not_found`) in the original spec's exit-code table. The code is canonical.
- **#5:** Closed by S4.
- **#7:** Remove `conformance.scenarios.toml` from the original spec's §9 and move it to §11 as deferred. Nothing reads it.
- **#1:** Record the 0–9 / ≥10 rule in the original spec's §7 and in `errors.py` (I1). Divergence #1 stays open only for behecheck's adoption.

## 3. Public surface after v0.2.0

```python
# beheaxi/__init__.py — additions
from .errors import DOMAIN_EXIT_FLOOR          # == 10

# beheaxi/output.py — new helpers (consumers may use them for their own human output)
def sanitize(text: str) -> str: ...
def safe_text(value: object, style: str = "") -> rich.text.Text: ...
def make_console(ctx: AxiContext, *, stderr: bool = False) -> rich.console.Console: ...
def to_json(data: object) -> str: ...

# beheaxi/app.py
RESERVED_VERBS: frozenset[str]                 # {"describe"}
DEBUG_ENV = "BEHEAXI_DEBUG"

# beheaxi/conformance/runner.py
def run_conformance(cmd: list[str], *, inherit_env: bool = False,
                    timeout: float = 30.0) -> Report: ...
def scrubbed_env(environ: Mapping[str, str]) -> dict[str, str]: ...
class ToolRunner: run(args) -> (rc, out, err); run_tty(args) -> (rc, combined) | None
```

The manifest schema (`manifest_schema.json`) is **unchanged**, so beherouter's verbatim
validation keeps working.

## 4. Behaviour changes that consumers will notice (hence 0.1.2 → 0.2.0)

1. Registration raises `ValueError` for invalid, duplicate or reserved verb names, unresolvable
   annotations, required options and optional positionals.
2. `emit("some [bold]string[/bold]")` now prints the brackets literally. Markup is never parsed.
3. A second `emit()` in `--json` mode is an error (exit 1).
4. Internal error text is redacted unless `BEHEAXI_DEBUG=1`.
5. The manifest now reports real types (`integer`, `boolean`, …), so beherouter-generated tool
   schemas get more precise.
6. `typer.Exit(n)` and `sys.exit("msg")` now produce the exit codes they should.
7. `beheaxi conformance` exits 10 (not 1) on failing checks, scrubs secrets from the environment,
   and runs 7 checks.

## 5. Out of scope (explicitly deferred)

- **A health field in the manifest (divergence #3)** and **richer arg metadata** (a positional
  flag, defaults, descriptions). Both are versioned schema changes that beherouter validates
  verbatim, so they need a cross-repo handoff first.
- **The service profile (divergence #2, CONVENTIONS §3–§6).** This is a separate spec.
- **`KeyboardInterrupt` → 130.** 130 falls in the domain range (≥ 10) under CONVENTIONS §2, so
  reserving it is an umbrella-level rule change. Inside a verb, Click already turns Ctrl-C into
  `Abort` (I4). During the dashboard it keeps Python's default behaviour.
- **Signed tags and commit-SHA pinning for consumers.** This is release-process work. The README
  gets a note.

## 6. Acceptance

- Every ID in §2 has a regression test that fails on v0.1.2 and passes on v0.2.0. CI and the
  pyproject edit cover S6 and I3.
- `uv run ruff check . && uv run mypy && uv run pytest -q` pass, and
  `uv run beheaxi conformance "beheaxi" --json` reports `"ok": true` over 7 checks.
- The lowest-direct resolution job passes.
- beherouter's test suite and `beheaxi conformance "beherouter"` pass against this tree, run as
  an overlay with **no edits to beherouter**.
