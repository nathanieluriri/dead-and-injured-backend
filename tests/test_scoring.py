"""Unit tests for the real scoring engine and input validator.

These exercise ``Player.guess_result`` (the bulls & cows evaluator the whole game
is built on) and ``validate_code`` (the secret/guess input rule) directly.
"""
from __future__ import annotations

import pytest

from schemas.imports import Player
from schemas.validators import validate_code


def _result(secret: str, guess: str):
    r = Player(code=secret).guess_result(guess=guess)
    return r.dead, r.injured, r.game_over


@pytest.mark.parametrize(
    "secret,guess,expected",
    [
        ("1234", "1234", (4, 0, True)),    # perfect
        ("1234", "5678", (0, 0, False)),   # nothing
        ("1234", "4321", (0, 4, False)),   # full permutation
        ("1234", "1259", (2, 0, False)),   # two in place
        ("1234", "1356", (1, 1, False)),   # one dead, one injured
        ("1234", "3490", (0, 2, False)),   # two injured
        ("1234", "1239", (3, 0, False)),   # three dead
        ("0123", "0123", (4, 0, True)),    # leading zero
        ("1234", "1111", (1, 0, False)),   # duplicate digits not double counted
    ],
)
def test_guess_result(secret, guess, expected):
    assert _result(secret, guess) == expected


def test_game_over_only_on_full_match():
    assert Player(code="1234").guess_result(guess="1243").game_over is False
    assert Player(code="1234").guess_result(guess="1234").game_over is True


@pytest.mark.parametrize("code", ["0246", "9081", "1234"])
def test_validate_code_accepts_valid(code):
    assert validate_code(code) == code


@pytest.mark.parametrize("code", ["123", "12345", "12a4", "1123", "1111", ""])
def test_validate_code_rejects_invalid(code):
    with pytest.raises(ValueError):
        validate_code(code)
