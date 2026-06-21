"""Individual black-box conformance checks.

Each check takes a `run` callable — `run(args) -> (returncode, stdout, stderr)` — and returns a
CheckResult. The checks exercise the tool's REAL shipped binary as a subprocess, the same surface
behemcp uses, so a passing tool is AXI-compliant by the contract behemcp builds against.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import jsonschema

ANSI = re.compile(r"\x1b\[")
SCHEMA = json.loads((Path(__file__).resolve().parents[1] / "manifest_schema.json").read_text())
# run(args) -> (returncode, stdout, stderr)
Runner = Callable[[list[str]], tuple[int, str, str]]


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""


def describe_schema(run: Runner) -> CheckResult:
    code, out, _ = run(["describe", "--json"])
    if code != 0:
        return CheckResult("describe_schema", False, f"exit {code}")
    try:
        jsonschema.validate(json.loads(out), SCHEMA)
    except Exception as e:  # noqa: BLE001
        return CheckResult("describe_schema", False, str(e)[:200])
    return CheckResult("describe_schema", True)


def pinned_verbs(run: Runner) -> CheckResult:
    _, out, _ = run(["describe", "--json"])
    try:
        m = json.loads(out)
    except Exception:  # noqa: BLE001
        return CheckResult("pinned_verbs", False, "describe output not JSON")
    pinned = [v for v in m["verbs"] if v["pinned"]]
    bad = [v["name"] for v in pinned if not v["summary"] or "args" not in v]
    return CheckResult("pinned_verbs", not bad, f"incomplete: {bad}" if bad else "")


def json_parseable(run: Runner) -> CheckResult:
    _, out, _ = run(["--json", "describe"])  # flag BEFORE subcommand too
    try:
        json.loads(out)
    except Exception:  # noqa: BLE001
        return CheckResult("json_parseable", False, "stdout not JSON with --json before subcommand")
    return CheckResult("json_parseable", True)


def no_color(run: Runner) -> CheckResult:
    _, out, _ = run(["--no-color", "describe"])
    has_ansi = bool(ANSI.search(out))
    return CheckResult("no_color", not has_ansi, "ANSI present" if has_ansi else "")


def usage_exit_2(run: Runner) -> CheckResult:
    code, _, _ = run(["definitely-not-a-command"])
    return CheckResult("usage_exit_2", code == 2, f"got exit {code}")


def dashboard(run: Runner) -> CheckResult:
    code, out, _ = run([])
    return CheckResult("dashboard", code == 0 and out.strip() != "", f"exit {code}")


ALL_CHECKS = [describe_schema, pinned_verbs, json_parseable, no_color, usage_exit_2, dashboard]
