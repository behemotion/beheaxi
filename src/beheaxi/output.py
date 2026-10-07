"""Output rendering: JSON for machines, Rich for humans; honors --no-color."""
from __future__ import annotations

import json
import re
import sys
from collections.abc import Iterator
from typing import Any

from rich.console import Console, ConsoleOptions
from rich.pretty import Pretty
from rich.protocol import is_renderable, rich_cast
from rich.segment import Segment
from rich.text import Text

from .context import AxiContext
from .errors import AxiError

# Stripped from every string rendered for a human terminal: C0 controls except \t and \n
# (ESC starts CSI/OSC sequences — title rewrites, OSC 8 hyperlinks, cursor moves; \r
# overwrites the visible line), DEL, C1 controls, and the bidi overrides/isolates that
# reorder what the reader sees (CVE-2021-42574).
_UNSAFE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f\u202a-\u202e\u2066-\u2069]")


def sanitize(text: str) -> str:
    """Remove terminal-control and bidi characters from text bound for a human terminal."""
    return _UNSAFE.sub("", text)


def safe_text(value: Any, style: str = "") -> Text:
    """Untrusted value -> Rich Text: never parsed as markup, control characters removed."""
    return Text(sanitize(str(value)), style=style)


class _Sanitized:
    """Wraps any renderable and strips unsafe characters from the text it renders to.

    Rich's Pretty escapes control characters only in the reprs it builds itself; a custom
    `__repr__` inside a container is copied verbatim, ESC and bidi overrides included.
    Filtering the rendered segments covers every renderable whatever produced the text.
    Control segments are Rich's own cursor/style codes, not caller text, and pass through.
    """

    def __init__(self, data: Any) -> None:
        cast = rich_cast(data)  # the same promotion Console.print applies
        self.renderable = cast if is_renderable(cast) else Pretty(cast)

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> Iterator[Segment]:
        for seg in console.render(self.renderable, options):
            yield seg if seg.control else seg._replace(text=sanitize(seg.text))


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
    # Strings become literal Text; everything else (containers -> Pretty) is sanitized
    # after rendering, because Pretty copies a custom __repr__ verbatim.
    make_console(ctx).print(safe_text(data) if isinstance(data, str) else _Sanitized(data))


def render_error(err: AxiError, ctx: AxiContext) -> None:
    """Error output → always stderr. JSON envelope in --json mode, else Rich."""
    if ctx.json:
        envelope = err.envelope()
        try:
            text = to_json(envelope)
        except Exception:  # noqa: BLE001 - unencodable context (NaN, cycle, raising __str__)
            envelope["error"].pop("context", None)
            text = to_json(envelope)
        sys.stderr.write(text + "\n")
        return
    con = make_console(ctx, stderr=True)
    con.print(Text.assemble(("error:", "red"), " ", safe_text(err.title)))
    if err.detail:
        con.print(safe_text(err.detail))
