"""Orchestrate the black-box conformance checks against a tool's real binary."""
from __future__ import annotations

import subprocess
from dataclasses import dataclass

from .checks import ALL_CHECKS, CheckResult


@dataclass
class Report:
    checks: list[CheckResult]

    @property
    def ok(self) -> bool:
        return all(c.passed for c in self.checks)

    @property
    def failures(self) -> list[CheckResult]:
        return [c for c in self.checks if not c.passed]


def run_conformance(cmd: list[str]) -> Report:
    def run(args: list[str]) -> tuple[int, str, str]:
        p = subprocess.run(cmd + args, capture_output=True, text=True, timeout=30)
        return p.returncode, p.stdout, p.stderr

    return Report([check(run) for check in ALL_CHECKS])
