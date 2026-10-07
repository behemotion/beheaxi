"""describe types under PEP 563 — the harness-wide `from __future__ import annotations`."""
from __future__ import annotations

import enum
import json
from pathlib import Path
from typing import Annotated, Optional

import jsonschema
import pytest
import typer

try:  # the base class, not typer's subclass: vendored in typer >= 0.26, standalone before
    from typer._click.core import Context as ClickContext
except ModuleNotFoundError:  # pragma: no cover - lowest-deps job
    from click import Context as ClickContext

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
        legacy: Optional[int] = None,  # noqa: UP045 - the pre-PEP 604 spelling, on purpose
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


def test_short_only_options_are_named_by_their_declaration(capsys):
    app = BeheaxiApp(name="x", version="0", summary="x")

    @app.command()
    def ann(top: Annotated[int, typer.Option("-n")] = 5) -> None:
        """Annotated short-only."""
        app.emit({"top": top})

    @app.command()
    def old(top: int = typer.Option(5, "-n")) -> None:
        """Old-style short-only."""
        app.emit({"top": top})

    for verb in build_manifest(app)["verbs"]:
        assert verb["args"] == [{"name": "-n", "type": "integer", "required": False}]
    for v in ("ann", "old"):
        assert app.main([v, "-n", "2", "--json"]) == 0
        assert json.loads(capsys.readouterr().out) == {"top": 2}


def test_context_parameters_are_not_manifest_args(capsys):
    app = BeheaxiApp(name="x", version="0", summary="x")

    @app.command()
    def with_ctx(ctx: typer.Context, name: str) -> None:
        """Typer context."""
        app.emit({"verb": ctx.info_name, "name": name})

    @app.command()
    def with_click_ctx(ctx: ClickContext, n: int = 1) -> None:
        """Base click context."""

    verbs = {v["name"]: v["args"] for v in build_manifest(app)["verbs"]}
    assert verbs["with-ctx"] == [{"name": "name", "type": "string", "required": True}]
    assert verbs["with-click-ctx"] == [{"name": "--n", "type": "integer", "required": False}]
    assert app.main(["with-ctx", "bob", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {"verb": "with-ctx", "name": "bob"}


def test_default_factory_options_are_optional(capsys):
    app = BeheaxiApp(name="x", version="0", summary="x")

    @app.command()
    def ann(top: Annotated[int, typer.Option(default_factory=lambda: 5)]) -> None:
        """Annotated default_factory."""
        app.emit({"top": top})

    @app.command()
    def old(top: int = typer.Option(default_factory=lambda: 6)) -> None:
        """Old-style default_factory."""
        app.emit({"top": top})

    verbs = {v["name"]: v["args"] for v in build_manifest(app)["verbs"]}
    assert verbs["ann"] == [{"name": "--top", "type": "integer", "required": False}]
    assert verbs["old"] == [{"name": "--top", "type": "integer", "required": False}]
    assert app.main(["ann", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {"top": 5}
    assert app.main(["old", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {"top": 6}


def test_default_factory_positional_is_still_rejected():
    app = BeheaxiApp(name="x", version="0", summary="x")

    def opt(target: Annotated[str, typer.Argument(default_factory=lambda: "here")]) -> None:
        """Optional positional via default_factory."""

    with pytest.raises(ValueError, match="optional positional"):
        app.command()(opt)
