import json

from beheaxi.app import BeheaxiApp
from beheaxi.dashboard import Status


def make_app(with_status=True):
    app = BeheaxiApp(name="demo", version="0.0.1", summary="Demo tool.")

    @app.command(pinned=True)
    def search(q: str):
        """Search."""
        app.emit([])

    if with_status:
        @app.status()
        def status() -> Status:
            return Status(state={"shelves": 3}, suggest=["demo search <q>"])

    return app


def test_dashboard_shows_state_suggest_and_verbs(capsys):
    code = make_app().main([])  # no args -> dashboard
    out = capsys.readouterr().out
    assert code == 0
    assert "demo" in out and "0.0.1" in out  # header
    assert "shelves" in out and "3" in out  # state
    assert "demo search <q>" in out  # suggestions
    assert "search" in out  # verb menu


def test_dashboard_without_status_hook_still_renders(capsys):
    make_app(with_status=False).main([])
    out = capsys.readouterr().out
    assert "demo" in out and "search" in out  # header + menu, no crash


def test_dashboard_json_mode_is_structured(capsys):
    make_app().main(["--json"])
    data = json.loads(capsys.readouterr().out)
    assert data["tool"] == "demo" and "verbs" in data and data["state"]["shelves"] == 3
