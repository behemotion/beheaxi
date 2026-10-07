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
