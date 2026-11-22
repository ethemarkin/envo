"""The single .env dialect shared by the web importer and the CLI.

Accepted syntax:
    # comment                  full-line comments and blank lines are ignored
    KEY=value                  unquoted; trimmed; " #" starts an inline comment
    export KEY=value           optional "export " prefix
    KEY = value                whitespace around "=" is allowed
    KEY='literal $value'       single quotes: literal, may span lines
    KEY="a\nb \"q\""           double quotes: \\n \\r \\t \\" \\\\ escapes, may span lines
    KEY=                       empty value

`${VAR}` is not expanded; values are stored exactly as written.
Duplicate or invalid keys make the whole document invalid.
"""

import re
from dataclasses import dataclass

KEY_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
MAX_KEY_LENGTH = 255
MAX_VALUE_LENGTH = 64 * 1024
MAX_DOCUMENT_SIZE = 1024 * 1024
MAX_ENTRIES = 1000

_ESCAPES = {"n": "\n", "r": "\r", "t": "\t", '"': '"', "\\": "\\"}
_SAFE_UNQUOTED = re.compile(r"[A-Za-z0-9_./:@+,=%^~-]+")


@dataclass(frozen=True)
class Entry:
    key: str
    value: str
    line: int


@dataclass(frozen=True)
class ParseError:
    line: int
    code: str
    message: str


@dataclass
class ParseResult:
    entries: list[Entry]
    errors: list[ParseError]

    @property
    def ok(self) -> bool:
        return not self.errors


def valid_key(key: str) -> bool:
    return len(key) <= MAX_KEY_LENGTH and KEY_PATTERN.fullmatch(key) is not None


def parse(text: str) -> ParseResult:
    entries: list[Entry] = []
    errors: list[ParseError] = []

    if len(text.encode()) > MAX_DOCUMENT_SIZE:
        return ParseResult([], [ParseError(0, "too_large", "Document exceeds 1 MiB")])

    text = text.removeprefix("﻿").replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    seen: dict[str, int] = {}
    i = 0
    while i < len(lines):
        lineno = i + 1
        line = lines[i].strip()
        i += 1
        if not line or line.startswith("#"):
            continue
        if line.startswith("export ") or line.startswith("export\t"):
            line = line[len("export") :].lstrip()

        key, sep, rest = line.partition("=")
        key = key.strip()
        if not sep:
            errors.append(ParseError(lineno, "missing_equals", f"Expected KEY=value: {key[:40]}"))
            continue
        if not valid_key(key):
            errors.append(ParseError(lineno, "invalid_key", f"Invalid key: {key[:40]}"))
            continue

        rest = rest.lstrip()
        if rest[:1] in ('"', "'"):
            quote = rest[0]
            body = rest[1:]
            value_parts: list[str] = []
            closed = False
            while True:
                end = _find_closing(body, quote)
                if end is not None:
                    value_parts.append(body[:end])
                    trailing = body[end + 1 :].strip()
                    closed = True
                    break
                value_parts.append(body)
                if i >= len(lines):
                    break
                body = lines[i]
                i += 1
            if not closed:
                errors.append(ParseError(lineno, "unterminated_quote", f"Unclosed quote: {key}"))
                continue
            if trailing and not trailing.startswith("#"):
                errors.append(
                    ParseError(lineno, "trailing_characters", f"Text after closing quote: {key}")
                )
                continue
            raw = "\n".join(value_parts)
            value = _unescape(raw) if quote == '"' else raw
        else:
            value = re.split(r"\s+#", rest, maxsplit=1)[0].strip()

        if len(value) > MAX_VALUE_LENGTH:
            errors.append(ParseError(lineno, "value_too_long", f"Value too long: {key}"))
            continue
        if key in seen:
            errors.append(
                ParseError(lineno, "duplicate_key", f"{key} is already defined on line {seen[key]}")
            )
            continue
        seen[key] = lineno
        entries.append(Entry(key, value, lineno))

    if len(entries) > MAX_ENTRIES:
        errors.append(ParseError(0, "too_many_entries", f"More than {MAX_ENTRIES} variables"))
    return ParseResult(entries, errors)


def _find_closing(s: str, quote: str) -> int | None:
    i = 0
    while i < len(s):
        c = s[i]
        if quote == '"' and c == "\\":
            i += 2
            continue
        if c == quote:
            return i
        i += 1
    return None


def _unescape(s: str) -> str:
    out: list[str] = []
    i = 0
    while i < len(s):
        c = s[i]
        if c == "\\" and i + 1 < len(s) and s[i + 1] in _ESCAPES:
            out.append(_ESCAPES[s[i + 1]])
            i += 2
            continue
        out.append(c)
        i += 1
    return "".join(out)


def format_value(value: str) -> str:
    if value == "" or _SAFE_UNQUOTED.fullmatch(value):
        return value
    if "'" not in value and "\n" not in value and "\r" not in value:
        return f"'{value}'"
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )
    return f'"{escaped}"'


def render(items: list[tuple[str, str]]) -> str:
    """Render key/value pairs as a .env document that `parse` reads back exactly."""
    return "".join(f"{key}={format_value(value)}\n" for key, value in items)
