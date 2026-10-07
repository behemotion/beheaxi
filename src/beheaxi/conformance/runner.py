"""Orchestrate the black-box conformance checks against a tool's real binary."""
from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Callable

from .checks import ALL_CHECKS, CheckResult, Runner

TIMEOUT_S = 30.0
# Shell conventions, so a launch failure reads like one in the report.
EXIT_TIMEOUT = 124
EXIT_NOT_EXECUTABLE = 126
EXIT_NOT_FOUND = 127

# Conformance probes structure, never data, so the tool under test gets no credentials.
# Matched case-insensitively against variable NAMES.
SECRET_ENV = re.compile(
    r"TOKEN|SECRET|PASSW(OR)?D|API_?KEY|CREDENTIAL|PRIVATE_?KEY|BEARER|AUTH", re.IGNORECASE
)


def scrubbed_env(environ: Mapping[str, str]) -> dict[str, str]:
    """`environ` minus every variable whose name looks like it holds a credential."""
    return {k: v for k, v in environ.items() if not SECRET_ENV.search(k)}


@dataclass
class Report:
    checks: list[CheckResult]

    @property
    def ok(self) -> bool:
        return all(c.passed for c in self.checks)

    @property
    def failures(self) -> list[CheckResult]:
        return [c for c in self.checks if not c.passed]


@dataclass
class ToolRunner:
    """Runs the tool under test. Every launch failure becomes a result, never an exception."""

    cmd: list[str]
    env: dict[str, str] | None = None
    timeout: float = TIMEOUT_S

    def run(self, args: list[str]) -> tuple[int, str, str]:
        try:
            p = subprocess.run(
                self.cmd + args,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                env=self.env,
                stdin=subprocess.DEVNULL,
            )
        except subprocess.TimeoutExpired:
            return EXIT_TIMEOUT, "", f"timed out after {self.timeout:g}s"
        except FileNotFoundError as e:
            return EXIT_NOT_FOUND, "", f"not found: {e.filename}"
        except OSError as e:  # PermissionError, exec format error, ...
            return EXIT_NOT_EXECUTABLE, "", f"cannot execute: {e}"
        return p.returncode, p.stdout, p.stderr


def _guarded(check: Callable[[Runner], CheckResult], tool: Runner) -> CheckResult:
    try:
        return check(tool)
    except Exception as e:  # noqa: BLE001 - a malformed tool must fail ONE check, not the run
        name = getattr(check, "__name__", "check")
        return CheckResult(name, False, f"check crashed: {type(e).__name__}: {e}"[:200])


def run_conformance(
    cmd: list[str], *, inherit_env: bool = False, timeout: float = TIMEOUT_S
) -> Report:
    env = None if inherit_env else scrubbed_env(os.environ)
    tool = ToolRunner(cmd, env=env, timeout=timeout)
    return Report([_guarded(check, tool) for check in ALL_CHECKS])
