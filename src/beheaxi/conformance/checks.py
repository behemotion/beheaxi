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

ANSI = re.compile(r"\x1b\[")
SCHEMA = json.loads((Path(__file__).resolve().parents[1] / "manifest_schema.json").read_text())
BOGUS = "definitely-not-a-command"


class Runner(Protocol):
    def run(self, args: list[str]) -> tuple[int, str, str]:
        """(returncode, stdout, stderr), with stdout/stderr piped."""
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
    _, out, _ = tool.run(["--no-color", "describe"])
    has_ansi = bool(ANSI.search(out))
    return CheckResult("no_color", not has_ansi, "ANSI present" if has_ansi else "")


def usage_exit_2(tool: Runner) -> CheckResult:
    code, _, _ = tool.run([BOGUS])
    return CheckResult("usage_exit_2", code == 2, f"got exit {code}")


def dashboard(tool: Runner) -> CheckResult:
    code, out, _ = tool.run([])
    return CheckResult("dashboard", code == 0 and out.strip() != "", f"exit {code}")


ALL_CHECKS: list[Callable[[Runner], CheckResult]] = [
    describe_schema,
    pinned_verbs,
    json_parseable,
    no_color,
    usage_exit_2,
    dashboard,
]
