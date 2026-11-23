"""Folder paths inside a project, e.g. "" (the project root), "backend",
"services/api", and the names of the files placed in them.

Paths are stored normalized: forward slashes, no leading or trailing slash,
no "." or ".." segments.

A folder can hold a .env (a set of variables) and any number of config files
(e.g. application.properties, config.json) whose whole text is the value.
Config files are stored like variables of their folder, under the key
"file:<name>": dotenv keys never contain ":", so the two cannot collide, and
history, rollback and folder moves treat both alike.
"""

import re

MAX_PATH_LENGTH = 255
MAX_DEPTH = 16
ROOT = ""

_SEGMENT = re.compile(r"[A-Za-z0-9._-]+")


ENV_FILE = ".env"
FILE_KEY_PREFIX = "file:"


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


def normalize_name(raw: str) -> str:
    """A file name: one path segment; raises InvalidPath. ".env" is allowed
    here; callers that only accept config files reject it themselves."""
    name = raw.strip()
    if name in ("", ".", "..") or not _SEGMENT.fullmatch(name):
        raise InvalidPath(raw)
    return name


def file_key(name: str) -> str:
    """The key a config file's content is stored under."""
    return FILE_KEY_PREFIX + name


def file_name(key: str) -> str | None:
    """The config file a stored key belongs to, or None for a variable."""
    return key[len(FILE_KEY_PREFIX) :] if key.startswith(FILE_KEY_PREFIX) else None


def owner(key: str) -> str:
    """The file in its folder that a stored key belongs to: ".env" or a
    config file's name."""
    return file_name(key) or ENV_FILE


def join(path: str, name: str) -> str:
    return f"{path}/{name}" if path else name


def label(path: str, key: str) -> str:
    """How a variable or config file is named in results, history and audit
    events: "KEY", "folder/KEY" or "folder/application.properties"."""
    return join(path, file_name(key) or key)
