"""Canonical exit codes and the problem+json error envelope for all BEHEMOTION tools."""
from __future__ import annotations

from enum import IntEnum
from typing import Any


class ExitCode(IntEnum):
    OK = 0
    INTERNAL = 1
    USAGE = 2
    NOT_FOUND = 3
    AUTH = 4
    CONFLICT = 5
    UNAVAILABLE = 6


class AxiError(Exception):
    """Base error. Subclasses set `code` and `type_`; carries problem+json fields."""

    code: ExitCode = ExitCode.INTERNAL
    type_: str = "internal"

    def __init__(
        self,
        title: str,
        *,
        detail: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(title)
        self.title = title
        self.detail = detail
        self.context = context or {}

    def envelope(self) -> dict[str, Any]:
        body: dict[str, Any] = {"type": self.type_, "title": self.title, "code": int(self.code)}
        if self.detail is not None:
            body["detail"] = self.detail
        if self.context:
            body["context"] = self.context
        # stable key order: type, title, detail, code, context
        ordered = {k: body[k] for k in ("type", "title", "detail", "code", "context") if k in body}
        return {"error": ordered}


class UsageError(AxiError):
    code = ExitCode.USAGE
    type_ = "usage"


class NotFound(AxiError):
    code = ExitCode.NOT_FOUND
    type_ = "not_found"


class AuthError(AxiError):
    code = ExitCode.AUTH
    type_ = "auth"


class Conflict(AxiError):
    code = ExitCode.CONFLICT
    type_ = "conflict"


class Unavailable(AxiError):
    code = ExitCode.UNAVAILABLE
    type_ = "unavailable"
