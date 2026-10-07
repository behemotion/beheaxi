import os
import sys

import pytest

from beheaxi.conformance.checks import ALL_CHECKS
from beheaxi.conformance.runner import ToolRunner, run_conformance, scrubbed_env

EXAMPLE = [sys.executable, "tests/example_app.py"]
BROKEN = [sys.executable, "tests/broken_app.py"]
FAKE = [sys.executable, "tests/fake_tool.py"]


def run_fake(monkeypatch, mode, **kwargs):
    monkeypatch.setenv("FAKE_TOOL_MODE", mode)
    return run_conformance(FAKE, **kwargs)


def failed(report):
    return {c.name for c in report.failures}


def test_compliant_app_passes():
    report = run_conformance(EXAMPLE)
    assert report.ok, report.failures
    assert {c.name for c in report.checks} >= {
        "describe_schema", "pinned_verbs", "json_parseable", "no_color",
        "usage_exit_2", "dashboard", "json_error_envelope",
    }


def test_broken_app_fails_the_right_check():
    report = run_conformance(BROKEN)
    assert not report.ok
    assert any(c.name == "describe_schema" and not c.passed for c in report.checks)


def test_well_behaved_fake_tool_passes(monkeypatch):
    report = run_fake(monkeypatch, "")
    assert report.ok, report.failures


def test_malformed_manifest_fails_checks_without_crashing(monkeypatch):
    report = run_fake(monkeypatch, "empty_manifest")
    assert failed(report) == {"describe_schema", "pinned_verbs"}
    pinned = next(c for c in report.checks if c.name == "pinned_verbs")
    assert "no list of verb objects" in pinned.detail


def test_missing_binary_fails_every_check_without_crashing():
    report = run_conformance(["definitely-not-an-installed-binary-xyz"])
    assert not report.ok and len(report.checks) == len(ALL_CHECKS)
    usage = next(c for c in report.checks if c.name == "usage_exit_2")
    assert usage.detail == "got exit 127"


def test_hanging_tool_times_out_per_run(monkeypatch):
    report = run_fake(monkeypatch, "hang", timeout=0.5)
    assert not report.ok
    assert next(c for c in report.checks if c.name == "dashboard").detail == "exit 124"


def test_a_crashing_check_fails_only_itself(monkeypatch):
    def explodes(tool):
        raise RuntimeError("kaboom")

    monkeypatch.setattr("beheaxi.conformance.runner.ALL_CHECKS", [explodes, *ALL_CHECKS])
    report = run_conformance(EXAMPLE)
    assert failed(report) == {"explodes"}
    assert "kaboom" in report.failures[0].detail


def test_secrets_are_scrubbed_from_the_target_env(monkeypatch):
    monkeypatch.setenv("BEHELIB_API_TOKEN", "s3cret")
    seen = []
    real_run = ToolRunner.run

    def spy(self, args):
        seen.append(self.env)
        return real_run(self, args)

    monkeypatch.setattr(ToolRunner, "run", spy)
    run_conformance(EXAMPLE)
    assert seen and all("BEHELIB_API_TOKEN" not in env and "PATH" in env for env in seen)


def test_inherit_env_passes_the_environment_through(monkeypatch):
    seen = []
    real_run = ToolRunner.run

    def spy(self, args):
        seen.append(self.env)
        return real_run(self, args)

    monkeypatch.setattr(ToolRunner, "run", spy)
    run_conformance(EXAMPLE, inherit_env=True)
    assert seen and all(env is None for env in seen)


@pytest.mark.parametrize(
    "name",
    ["GITHUB_TOKEN", "BEHELIB_API_KEY", "db_password", "AWS_SECRET_ACCESS_KEY",
     "BEARER", "SSH_AUTH_SOCK", "BEHEROUTER_PRIVATE_KEY", "OAUTH_CLIENT_CREDENTIALS"],
)
def test_secretish_names_are_scrubbed(name):
    env = scrubbed_env({name: "x", "PATH": "/bin", "HOME": "/h"})
    assert name not in env and env == {"PATH": "/bin", "HOME": "/h"}


POSIX_ONLY = pytest.mark.skipif(sys.platform == "win32", reason="needs a pseudo-terminal")


@POSIX_ONLY
def test_colour_on_a_real_tty_is_caught(monkeypatch):
    report = run_fake(monkeypatch, "colorful")
    assert failed(report) == {"no_color"}
    assert "TTY" in report.failures[0].detail


def test_plain_text_usage_errors_fail_the_envelope_check(monkeypatch):
    report = run_fake(monkeypatch, "plain_error")
    assert failed(report) == {"json_error_envelope"}


@POSIX_ONLY
def test_beheaxi_apps_are_escape_free_on_a_tty():
    env = {k: v for k, v in os.environ.items() if k not in ("NO_COLOR", "FORCE_COLOR")}
    tool = ToolRunner(EXAMPLE, env={**env, "TERM": "xterm-256color"})
    for args in (["--no-color"], ["--no-color", "describe"]):
        result = tool.run_tty(args)
        assert result is not None
        code, out = result
        assert code == 0 and out.strip() and "\x1b" not in out
    # ...and the pty is real: without the flag the same dashboard IS styled.
    plain = tool.run_tty([])
    assert plain is not None and "\x1b[" in plain[1]
