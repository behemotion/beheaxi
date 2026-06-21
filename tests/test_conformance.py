import sys

from beheaxi.conformance.runner import run_conformance

EXAMPLE = [sys.executable, "tests/example_app.py"]
BROKEN = [sys.executable, "tests/broken_app.py"]


def test_compliant_app_passes():
    report = run_conformance(EXAMPLE)
    assert report.ok, report.failures
    assert {c.name for c in report.checks} >= {
        "describe_schema", "pinned_verbs", "json_parseable", "no_color",
        "usage_exit_2", "dashboard",
    }


def test_broken_app_fails_the_right_check():
    report = run_conformance(BROKEN)
    assert not report.ok
    assert any(c.name == "describe_schema" and not c.passed for c in report.checks)
