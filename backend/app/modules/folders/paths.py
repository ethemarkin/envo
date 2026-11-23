"""Folder paths inside a project, e.g. "" (the project root), "backend",
"services/api". Each folder holds one .env per environment.

Paths are stored normalized: forward slashes, no leading or trailing slash,
no "." or ".." segments.
"""

import re

MAX_PATH_LENGTH = 255
MAX_DEPTH = 16
ROOT = ""

_SEGMENT = re.compile(r"[A-Za-z0-9._-]+")


class InvalidPath(ValueError):
    pass


def normalize(raw: str | None) -> str:
    """Normalize a user-supplied path; raises InvalidPath."""
    if raw is None:
        return ROOT
    text = raw.strip().replace("\\", "/")
    segments = [s for s in text.split("/") if s not in ("", ".")]
    if len(segments) > MAX_DEPTH:
        raise InvalidPath(raw)
    for s in segments:
        if s == ".." or not _SEGMENT.fullmatch(s):
            raise InvalidPath(raw)
    path = "/".join(segments)
    if len(path) > MAX_PATH_LENGTH:
        raise InvalidPath(raw)
    return path


def within(path: str, folder: str) -> bool:
    """Whether `path` is `folder` or below it. Everything is within the root."""
    return folder == ROOT or path == folder or path.startswith(folder + "/")


def moved(path: str, old: str, new: str) -> str:
    """`path` (within `old`) relocated under `new`."""
    assert within(path, old) and old != ROOT
    return new + path[len(old) :]


def ancestors(path: str) -> list[str]:
    """Proper ancestors of `path`, excluding the root: "a/b/c" -> ["a", "a/b"]."""
    parts = path.split("/") if path else []
    return ["/".join(parts[:i]) for i in range(1, len(parts))]


def label(path: str, key: str) -> str:
    """How a variable is named in results, history and audit events."""
    return f"{path}/{key}" if path else key
