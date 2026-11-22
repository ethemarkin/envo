import pytest

from app.modules.variables.dotenv import parse, render


def values(text: str) -> dict[str, str]:
    result = parse(text)
    assert result.ok, result.errors
    return {e.key: e.value for e in result.entries}


def test_basic_syntax():
    text = """
# comment
PLAIN=value
export EXPORTED=yes
SPACED = around equals
EMPTY=
INLINE=value # comment
HASH=abc#def
URL=postgres://u:p@host:5432/db?sslmode=require
"""
    assert values(text) == {
        "PLAIN": "value",
        "EXPORTED": "yes",
        "SPACED": "around equals",
        "EMPTY": "",
        "INLINE": "value",
        "HASH": "abc#def",
        "URL": "postgres://u:p@host:5432/db?sslmode=require",
    }


def test_quotes_escapes_and_multiline():
    text = (
        "SINGLE='literal $HOME \\n # not a comment'\n"
        'DOUBLE="tab\\there \\"quoted\\" back\\\\slash" # trailing comment\n'
        'MULTI="line one\nline two"\n'
        "PEM='-----BEGIN KEY-----\nabc\n-----END KEY-----'\n"
        "NOEXPAND=${OTHER}\n"
    )
    assert values(text) == {
        "SINGLE": "literal $HOME \\n # not a comment",
        "DOUBLE": 'tab\there "quoted" back\\slash',
        "MULTI": "line one\nline two",
        "PEM": "-----BEGIN KEY-----\nabc\n-----END KEY-----",
        "NOEXPAND": "${OTHER}",
    }


def test_windows_line_endings_and_bom():
    assert values("﻿A=1\r\nB=2\r\n") == {"A": "1", "B": "2"}


@pytest.mark.parametrize(
    ("text", "code", "line"),
    [
        ("1BAD=x", "invalid_key", 1),
        ("BAD-KEY=x", "invalid_key", 1),
        ("A=1\nNOEQUALS", "missing_equals", 2),
        ("A=1\nA=2", "duplicate_key", 2),
        ('A="unterminated', "unterminated_quote", 1),
        ("A='x' junk", "trailing_characters", 1),
    ],
)
def test_errors_report_line_numbers(text, code, line):
    result = parse(text)
    assert not result.ok
    assert (result.errors[0].code, result.errors[0].line) == (code, line)


def test_all_errors_are_collected():
    result = parse("1A=x\nB=1\nB=2\nC")
    assert [e.code for e in result.errors] == ["invalid_key", "duplicate_key", "missing_equals"]


@pytest.mark.parametrize(
    "value",
    [
        "",
        "simple",
        "with spaces",
        " leading and trailing ",
        "it's",
        'say "hi"',
        "multi\nline\r\nvalue",
        "tab\tand \\ backslash",
        "#starts-with-hash",
        "has # hash",
        "${NOT_EXPANDED}",
        "ünïcödé ✓",
        "'\"",
    ],
)
def test_render_roundtrip(value):
    assert values(render([("KEY", value)])) == {"KEY": value}
