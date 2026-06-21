from beheaxi.errors import (
    ExitCode, NotFound, AuthError, Conflict, Unavailable, UsageError,
)


def test_exit_codes_are_canonical():
    assert (ExitCode.OK, ExitCode.INTERNAL, ExitCode.USAGE, ExitCode.NOT_FOUND,
            ExitCode.AUTH, ExitCode.CONFLICT, ExitCode.UNAVAILABLE) == (0, 1, 2, 3, 4, 5, 6)


def test_subclasses_carry_codes():
    assert NotFound("x").code == ExitCode.NOT_FOUND
    assert AuthError("x").code == ExitCode.AUTH
    assert Conflict("x").code == ExitCode.CONFLICT
    assert Unavailable("x").code == ExitCode.UNAVAILABLE
    assert UsageError("x").code == ExitCode.USAGE


def test_envelope_shape():
    err = NotFound("Shelf not found", detail="No shelf 'foo'.", context={"shelf": "foo"})
    assert err.envelope() == {"error": {
        "type": "not_found", "title": "Shelf not found",
        "detail": "No shelf 'foo'.", "code": 3, "context": {"shelf": "foo"}}}


def test_envelope_omits_empty_context():
    assert "context" not in AuthError("Nope").envelope()["error"]
