"""A minimal compliant BeheaxiApp, run as a subprocess by conformance tests.

Not collected by pytest (filename is not test_*). Exercised by tests/test_conformance.py
once Tasks 6-8 land (Status, dashboard, error handling).
"""
from beheaxi.app import BeheaxiApp
from beheaxi.dashboard import Status
from beheaxi.errors import NotFound

app = BeheaxiApp(name="demo", version="0.0.1", summary="Demo tool for conformance.")


@app.command(pinned=True, mutating=False)
def greet(who: str):
    """Greet someone."""
    app.emit({"hello": who})


@app.command(pinned=False, mutating=True)
def boom():
    """Always fails with not-found (for exit-code checks)."""
    raise NotFound("Nothing here", detail="boom always 404s")


@app.status()
def status() -> Status:
    return Status(state={"ready": True}, suggest=["demo greet <name>"])


if __name__ == "__main__":
    raise SystemExit(app.main())
