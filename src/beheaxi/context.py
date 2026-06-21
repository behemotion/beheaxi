"""Run-mode context and argv-level global-flag extraction (placement-independent)."""
from __future__ import annotations

import sys
from dataclasses import dataclass

GLOBAL_FLAGS = {"--json", "--quiet", "--no-color"}


@dataclass
class AxiContext:
    json: bool = False
    quiet: bool = False
    no_color: bool = False


def extract_global_flags(argv: list[str]) -> tuple[AxiContext, list[str]]:
    """Pull --json/--quiet/--no-color out of argv at any position; return (ctx, remaining).

    Stripping the global flags before Typer/Click parses makes them work in any position
    (before or after the subcommand) — Click's own option parsing is placement-sensitive.
    """
    ctx = AxiContext()
    rest: list[str] = []
    for tok in argv:
        if tok == "--json":
            ctx.json = True
        elif tok == "--quiet":
            ctx.quiet = True
        elif tok == "--no-color":
            ctx.no_color = True
        else:
            rest.append(tok)
    if not sys.stdout.isatty():
        ctx.no_color = True
    return ctx, rest
