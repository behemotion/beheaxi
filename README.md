# beheaxi

The shared CLI / AXI framework for the [BEHEMOTION](../) harness. Every tool's CLI is built on
beheaxi, so the AXI standard is enforced **by construction** rather than re-implemented per tool:
standard global flags (`--json` / `--quiet` / `--no-color`), a no-arg live dashboard, token-efficient
machine output, a structured problem+json error envelope with categorized exit codes, a
`describe --json` registration manifest generated from the command tree, and a black-box conformance
runner.

beheaxi is a **build-time library**, not a deployed service: no `deploy.md`, no port, no database.
Tools consume it as a versioned git dependency.

See `docs/superpowers/specs/2026-06-21-beheaxi-design.md` for the design and
`docs/superpowers/plans/2026-06-21-beheaxi.md` for the implementation plan.

## Using beheaxi

A tool's CLI is a `BeheaxiApp`; the standard is wired in at construction.

```python
from beheaxi import BeheaxiApp, Status

app = BeheaxiApp(name="behelib", version="1.0.0",
                 summary="Knowledge layer — agentic + graph RAG.")

@app.command(pinned=True, mutating=False)
def search(query: str, shelf: str = None):
    """Ranked semantic+graph search over indexed knowledge."""
    app.emit(results)            # JSON in --json mode, Rich otherwise

@app.status()                    # feeds the no-arg dashboard
def status() -> Status:
    return Status(state={"shelves": 3, "indexed_docs": 1240},
                  suggest=["behelib search <query>", "behelib fill <box>"])

def main() -> None:
    raise SystemExit(app.main())
```

You get for free: `--json` / `--quiet` / `--no-color` (any argv position), a `describe --json`
registration manifest, a problem+json error envelope with categorized exit codes, and a no-arg
dashboard. Verify compliance with `beheaxi conformance "<your-tool>"`.

## Depending on beheaxi

Tools pin a tagged version; no PyPI publish needed.

**Pin v0.1.1 or newer.** v0.1.0 catches only one of the two importable
`ClickException` classes, so wherever standalone `click` is installed alongside
Typer's vendored copy (FastMCP causes exactly that), usage errors exit 1 instead
of 2 — and the consumer fails its own `usage_exit_2` conformance check.

```toml
# pyproject.toml
dependencies = ["beheaxi @ git+https://github.com/behemotion/beheaxi@v0.2.1"]
```

v0.1.2 is the first release carrying `LICENSE` and `NOTICE`, which Apache 2.0
§4(d) requires to reach downstream consumers; the exit-code fix above landed in
v0.1.1, so the floor still holds.

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
- **typer ≥ 0.16.0 is required.** The old `typer>=0.12` floor was false (0.12.x with current
  click breaks every boolean flag), and 0.13–0.15 mis-parse custom option declarations; CI now
  tests the declared floors.

### 0.2.1

A patch release; no contract changes.

- **typer 0.27 support.** typer 0.27 moved `Exit`/`Abort` into `typer.exceptions`; 0.2.0 missed
  them there, so `typer.Abort` reported "Internal error" instead of "Aborted".
- **`typer.Exit(n)` in a `status()` hook** exits `n` instead of 1.
- **`ctx: typer.Context`** is no longer listed as a manifest arg, and
  `typer.Option(default_factory=...)` counts as optional rather than a rejected required option.
- **Human `emit()`** strips control and bidi characters from every rendered value, including a
  custom `__repr__` inside a container.
- **`beheaxi conformance`** also strips `*PASSPHRASE*`, `*COOKIE*`, `*SESSION*`, `*DSN*` and
  database/broker URL variables (`DATABASE_URL`, `REDIS_URL`, `MONGODB_URI`, …; a plain `*_URL`
  is kept). It no longer hangs on a target that closes the pty but keeps running, and reports
  non-UTF-8 output instead of crashing the check.

Tags are mutable; for byte-for-byte reproducible builds rely on your `uv.lock`, which records
the resolved commit SHA of the git dependency.

⚠️ **Do not ship a `[tool.uv.sources]` override.** A local co-dev override —

```toml
[tool.uv.sources]
beheaxi = { path = "../beheaxi", editable = true }
```

— makes `git clone && uv sync` fail for anyone without a sibling `../beheaxi`
checkout, including your own CI. And it is **two** edits to undo, not one:
`uv.lock` records the path independently as `source = { editable = "../beheaxi" }`,
so removing it from `pyproject.toml` alone leaves a clean clone still broken.
Keep such an override out of the committed tree entirely.

## Attribution

beheaxi is licensed under the Apache License 2.0 — see [`LICENSE`](LICENSE).

Apache 2.0 §4(d) requires the attribution notices in [`NOTICE`](NOTICE) to be
reproduced in any redistribution or derivative work, including wherever your
product displays third-party notices.

We additionally **request** — this is a request, not a licence term — that
products built on beheaxi credit **Behemotion — https://behemotion.com** and
**Aleksandr Mezin** in their user-facing credits or terms of service.
