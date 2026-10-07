"""Orchestrate the black-box conformance checks against a tool's real binary."""
from __future__ import annotations

import os
import re
import subprocess
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from .checks import ALL_CHECKS, CheckResult, Runner

TIMEOUT_S = 30.0
# Shell conventions, so a launch failure reads like one in the report.
EXIT_TIMEOUT = 124
EXIT_NOT_EXECUTABLE = 126
EXIT_NOT_FOUND = 127

# Conformance probes structure, never data, so the tool under test gets no credentials.
# Matched case-insensitively against variable NAMES only — values are never inspected, so a
# secret in an innocuously named variable still passes through (use a clean shell).
# URLs: only the database/broker names that conventionally embed `user:password@`; a plain
# `*_URL` (an API endpoint a dashboard may need) is kept. `--inherit-env` bypasses all this.
SECRET_ENV = re.compile(
    r"TOKEN|SECRET|PASSW(OR)?D|PASSPHRASE|API_?KEY|CREDENTIAL|PRIVATE_?KEY|BEARER|AUTH"
    r"|COOKIE|SESSION|DSN"
    r"|(DATABASE|DB|REDIS|AMQP|RABBITMQ|BROKER|MONGO(DB)?|POSTGRES(QL)?|PG|MYSQL)_UR[LI]",
    re.IGNORECASE,
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
                errors="replace",  # non-UTF-8 output is a defect to report, not a crash
                timeout=self.timeout,
                env=self.env,
                stdin=subprocess.DEVNULL,
                check=False,  # a non-zero exit is the result under test, not an error
            )
        except subprocess.TimeoutExpired:
            return EXIT_TIMEOUT, "", f"timed out after {self.timeout:g}s"
        except FileNotFoundError as e:
            return EXIT_NOT_FOUND, "", f"not found: {e.filename}"
        except OSError as e:  # PermissionError, exec format error, ...
            return EXIT_NOT_EXECUTABLE, "", f"cannot execute: {e}"
        return p.returncode, p.stdout, p.stderr

    def run_tty(self, args: list[str]) -> tuple[int, str] | None:
        """Run with stdout+stderr on a pseudo-terminal: (returncode, combined output).

        A TTY is where colour actually switches on, so it is the only honest place to test
        --no-color — pipes are never TTYs. Returns None where ptys do not exist (Windows).
        """
        try:
            import pty
            import select
        except ImportError:  # pragma: no cover - non-POSIX
            return None
        master, slave = pty.openpty()
        try:
            try:
                proc = subprocess.Popen(
                    self.cmd + args,
                    stdin=subprocess.DEVNULL,
                    stdout=slave,
                    stderr=slave,
                    env=self.env,
                )
            except FileNotFoundError as e:
                return EXIT_NOT_FOUND, f"not found: {e.filename}"
            except OSError as e:
                return EXIT_NOT_EXECUTABLE, f"cannot execute: {e}"
            finally:
                os.close(slave)  # the child holds its own copy
            chunks: list[bytes] = []
            deadline = time.monotonic() + self.timeout
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    proc.kill()
                    proc.wait()
                    return EXIT_TIMEOUT, f"timed out after {self.timeout:g}s"
                ready, _, _ = select.select([master], [], [], min(remaining, 0.25))
                if not ready:
                    continue
                try:
                    data = os.read(master, 4096)
                except OSError:  # EIO: how Linux reports the child closing the pty
                    break
                if not data:  # EOF: how macOS reports it
                    break
                chunks.append(data)
            try:  # the child may close the pty and keep running: still bounded by the timeout
                code = proc.wait(timeout=max(deadline - time.monotonic(), 0))
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
                return EXIT_TIMEOUT, f"timed out after {self.timeout:g}s"
        finally:
            os.close(master)
        return code, b"".join(chunks).decode(errors="replace")


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
