import json
import shlex
import sys
from importlib.metadata import version
from pathlib import Path

from beheaxi import DOMAIN_EXIT_FLOOR
from beheaxi.cli import EXIT_NONCONFORMANT, app
from beheaxi.describe import build_manifest

HERE = Path(__file__).parent  # not the working directory: pytest may run from anywhere


def test_version_comes_from_the_installed_distribution():
    assert app.version == version("beheaxi")


def test_nonconformant_target_exits_with_the_domain_code(capsys):
    target = shlex.join([sys.executable, str(HERE / "broken_app.py")])
    code = app.main(["conformance", target, "--json"])
    assert code == EXIT_NONCONFORMANT == DOMAIN_EXIT_FLOOR == 10
    assert json.loads(capsys.readouterr().out)["ok"] is False


def test_conformant_target_exits_zero(capsys):
    target = shlex.join([sys.executable, str(HERE / "example_app.py")])
    assert app.main(["conformance", target, "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["ok"] is True and len(report["checks"]) == 7


def test_inherit_env_flag_is_advertised():
    verb = next(v for v in build_manifest(app)["verbs"] if v["name"] == "conformance")
    assert {"name": "--inherit-env", "type": "boolean", "required": False} in verb["args"]
