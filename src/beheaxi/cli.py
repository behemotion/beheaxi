"""beheaxi's own CLI, built on BeheaxiApp (dogfooding the standard)."""
from __future__ import annotations

import shlex

from .app import BeheaxiApp
from .conformance.runner import run_conformance
from .errors import ExitCode

app = BeheaxiApp(
    name="beheaxi",
    version="0.1.0",
    summary="Shared CLI/AXI framework for the BEHEMOTION harness.",
)


@app.command(pinned=True, mutating=False)
def conformance(target: str) -> None:
    """Run the AXI conformance suite against a tool command (e.g. 'behelib' or 'python app.py')."""
    report = run_conformance(shlex.split(target))
    rows = [{"check": c.name, "passed": c.passed, "detail": c.detail} for c in report.checks]
    app.emit({"target": target, "ok": report.ok, "checks": rows})
    if not report.ok:
        raise SystemExit(int(ExitCode.INTERNAL))


def main() -> None:
    raise SystemExit(app.main())


if __name__ == "__main__":  # enables `python -m beheaxi.cli` for the dogfood gate
    main()
