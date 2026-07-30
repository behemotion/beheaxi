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
dependencies = ["beheaxi @ git+https://github.com/behemotion/beheaxi@v0.1.1"]

# optional local co-dev override (do not ship):
[tool.uv.sources]
beheaxi = { path = "../beheaxi", editable = true }
```
