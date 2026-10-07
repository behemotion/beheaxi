"""A hand-rolled (non-beheaxi) CLI whose single defect is chosen by FAKE_TOOL_MODE.

Each conformance test sets one mode and asserts that exactly the matching check fails,
proving every check catches its defect without tripping the others. Modes:
  ""               well-behaved: passes every check
  empty_manifest   `describe` prints {}
  hang             sleeps past any timeout
  colorful         colours its dashboard on a TTY even under --no-color   (Task 8)
  plain_error      usage errors are plain text, not a JSON envelope        (Task 8)
"""
import json
import os
import sys
import time

MODE = os.environ.get("FAKE_TOOL_MODE", "")
MANIFEST = {"tool": "fake", "version": "0", "summary": "Fake tool.", "verbs": []}


def main() -> int:
    if MODE == "hang":
        time.sleep(60)
    args = [a for a in sys.argv[1:] if a not in ("--json", "--no-color")]
    if args == ["describe"]:
        print("{}" if MODE == "empty_manifest" else json.dumps(MANIFEST))
        return 0
    if not args:
        colour = MODE == "colorful" and sys.stdout.isatty()
        print("\x1b[1mfake\x1b[0m" if colour else "fake")
        return 0
    if MODE == "plain_error":
        print("error: no such command", file=sys.stderr)
    else:
        envelope = {"error": {"type": "usage", "title": "No such command.", "code": 2}}
        print(json.dumps(envelope), file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
