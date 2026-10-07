"""Output rendering: JSON for machines, Rich for humans; honors --no-color."""
from __future__ import annotations

import json
import re
import sys
from typing import Any

from rich.console import Console
from rich.text import Text

from .context import AxiContext
from .errors import AxiError

# Stripped from every string rendered for a human terminal: C0 controls except \t and \n
# (ESC starts CSI/OSC sequences — title rewrites, OSC 8 hyperlinks, cursor moves; \r
# overwrites the visible line), DEL, C1 controls, and the bidi overrides/isolates that
# reorder what the reader sees (CVE-2021-42574).
_UNSAFE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f‪-‮⁦-⁩]")


def sanitize(text: str) -> str:
    """Remove terminal-control and bidi characters from text bound for a human terminal."""
    return _UNSAFE.sub("", text)


def safe_text(value: Any, style: str = "") -> Text:
    """Untrusted value -> Rich Text: never parsed as markup, control characters removed."""
    return Text(sanitize(str(value)), style=style)


def make_console(ctx: AxiContext, *, stderr: bool = False) -> Console:
    """The one Console factory.

    markup/emoji are off: framework styling is built from Text objects, so no caller-supplied
    string is ever interpreted. Under --no-color, color_system=None rather than
    no_color=True: Rich's no_color drops colours but still emits bold/dim escapes on a TTY.
    """
    return Console(
        color_system=None if ctx.no_color else "auto",
        stderr=stderr,
        highlight=False,
        markup=False,
        emoji=False,
    )


def to_json(data: Any) -> str:
    """The one JSON encoder for stdout/stderr.

    Values json cannot encode natively (Path, datetime, UUID, ...) become strings. NaN and
    Infinity raise ValueError: they are not JSON, and strict parsers on the agent side reject
    the whole document.
    """
    return json.dumps(data, default=str, allow_nan=False)


def emit(data: Any, ctx: AxiContext) -> None:
    """Primary success output. One JSON doc to stdout in --json mode, else Rich."""
    if ctx.json:
        try:
            text = to_json(data)
        except ValueError as e:  # NaN/Infinity, circular reference: messages are safe
            raise AxiError("Output is not valid JSON", detail=str(e)) from e
        except Exception as e:  # e.g. a value whose __str__ raises: class name only
            raise AxiError(
                "Output is not valid JSON",
                detail=f"{type(e).__name__} while encoding output",
            ) from e
        sys.stdout.write(text + "\n")
        return
    if ctx.quiet:
        return
    # Strings are sanitized; containers go through Rich's Pretty, whose repr() already
    # escapes control characters.
    make_console(ctx).print(safe_text(data) if isinstance(data, str) else data)


def render_error(err: AxiError, ctx: AxiContext) -> None:
    """Error output → always stderr. JSON envelope in --json mode, else Rich."""
    if ctx.json:
        envelope = err.envelope()
        try:
            text = to_json(envelope)
        except Exception:  # unencodable context (NaN, cycle, raising __str__): drop context
            envelope["error"].pop("context", None)
            text = to_json(envelope)
        sys.stderr.write(text + "\n")
        return
    con = make_console(ctx, stderr=True)
    con.print(Text.assemble(("error:", "red"), " ", safe_text(err.title)))
    if err.detail:
        con.print(safe_text(err.detail))
