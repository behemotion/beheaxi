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
