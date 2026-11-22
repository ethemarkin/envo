import re
import secrets
import unicodedata
from collections.abc import Awaitable, Callable

SLUG_PATTERN = r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$"
_TR = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")


def slugify(value: str, fallback: str = "item") -> str:
    value = unicodedata.normalize("NFKD", value.translate(_TR))
    value = value.encode("ascii", "ignore").decode().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value[:50].strip("-") or fallback


async def unique_slug(base: str, exists: Callable[[str], Awaitable[bool]]) -> str:
    """Return `base`, or `base-<suffix>` if it is already taken."""
    if not await exists(base):
        return base
    for _ in range(10):
        candidate = f"{base}-{secrets.token_hex(3)}"
        if not await exists(candidate):
            return candidate
    raise RuntimeError("could not allocate a unique slug")
