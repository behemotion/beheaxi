"""Individual black-box conformance checks.

Each check takes a `Runner` and returns a CheckResult. The checks exercise the tool's REAL
shipped binary as a subprocess, the same surface beherouter uses, so a passing tool is
AXI-compliant by the contract beherouter builds against.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol

import jsonschema

ESC = re.compile("\x1b")  # any escape byte: CSI colours and OSC titles/hyperlinks alike
SCHEMA = json.loads((Path(__file__).resolve().parents[1] / "manifest_schema.json").read_text())
BOGUS = "definitely-not-a-command"


class Runner(Protocol):
    def run(self, args: list[str]) -> tuple[int, str, str]:
        """(returncode, stdout, stderr), with stdout/stderr piped."""
        ...

    def run_tty(self, args: list[str]) -> tuple[int, str] | None:
        """(returncode, combined output) on a pseudo-terminal; None where unsupported."""
        ...


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""


def describe_schema(tool: Runner) -> CheckResult:
    code, out, _ = tool.run(["describe", "--json"])
    if code != 0:
        return CheckResult("describe_schema", False, f"exit {code}")
    try:
        jsonschema.validate(json.loads(out), SCHEMA)
    except Exception as e:  # noqa: BLE001
        return CheckResult("describe_schema", False, str(e)[:200])
    return CheckResult("describe_schema", True)


def pinned_verbs(tool: Runner) -> CheckResult:
    _, out, _ = tool.run(["describe", "--json"])
    try:
        manifest: Any = json.loads(out)
    except ValueError:
        return CheckResult("pinned_verbs", False, "describe output not JSON")
    verbs = manifest.get("verbs") if isinstance(manifest, dict) else None
    if not isinstance(verbs, list) or not all(isinstance(v, dict) for v in verbs):
        return CheckResult("pinned_verbs", False, "manifest has no list of verb objects")
    bad = [
        v.get("name", "?")
        for v in verbs
        if v.get("pinned") and (not v.get("summary") or "args" not in v)
    ]
    return CheckResult("pinned_verbs", not bad, f"incomplete: {bad}" if bad else "")


def json_parseable(tool: Runner) -> CheckResult:
    _, out, _ = tool.run(["--json", "describe"])  # flag BEFORE subcommand too
    try:
        json.loads(out)
    except ValueError:
        return CheckResult("json_parseable", False, "stdout not JSON with --json before subcommand")
    return CheckResult("json_parseable", True)


def no_color(tool: Runner) -> CheckResult:
    """--no-color must yield zero escape bytes, piped AND on a real TTY: the TTY is where
    colour actually switches on (and where Rich's own no_color still emits bold)."""
    for args in (["--no-color"], ["--no-color", "describe"]):
        _, out, err = tool.run(args)
        if ESC.search(out) or ESC.search(err):
            return CheckResult("no_color", False, f"escape codes in piped output of {args}")
        tty = tool.run_tty(args)
        if tty is not None and ESC.search(tty[1]):
            return CheckResult("no_color", False, f"escape codes on a TTY with {args}")
    return CheckResult("no_color", True)


def usage_exit_2(tool: Runner) -> CheckResult:
    code, _, _ = tool.run([BOGUS])
    return CheckResult("usage_exit_2", code == 2, f"got exit {code}")


def dashboard(tool: Runner) -> CheckResult:
    code, out, _ = tool.run([])
    return CheckResult("dashboard", code == 0 and out.strip() != "", f"exit {code}")


def json_error_envelope(tool: Runner) -> CheckResult:
    """In --json mode an error leaves stdout empty and puts one envelope on stderr whose
    `code` equals the exit code."""
    name = "json_error_envelope"
    code, out, err = tool.run(["--json", BOGUS])
    if out.strip():
        return CheckResult(name, False, "stdout not empty on error")
    try:
        body: Any = json.loads(err)["error"]
    except (ValueError, KeyError, TypeError):
        return CheckResult(name, False, "stderr is not a JSON error envelope")
    if not isinstance(body, dict) or body.get("type") != "usage" or body.get("code") != code:
        return CheckResult(name, False, f"envelope {body!r:.100} does not match exit {code}")
    return CheckResult(name, True)


ALL_CHECKS: list[Callable[[Runner], CheckResult]] = [
    describe_schema,
    pinned_verbs,
    json_parseable,
    no_color,
    usage_exit_2,
    dashboard,
    json_error_envelope,
]
