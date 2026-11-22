"""Master key (KEK) access. Only this module touches the KEK.

LocalKeyProvider reads keys from settings; a KMS- or Vault-backed provider can
implement the same interface later.
"""

import base64
import binascii
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Protocol

from app.core.config import Settings, get_settings
from app.core.crypto.envelope import KEY_SIZE, CryptoError, dek_aad, open_sealed, seal


class KeyProvider(Protocol):
    @property
    def current_kek_id(self) -> str: ...

    def wrap_dek(self, environment_id: uuid.UUID, dek: bytes) -> tuple[str, bytes]: ...

    def unwrap_dek(self, environment_id: uuid.UUID, kek_id: str, wrapped: bytes) -> bytes: ...


class KeyConfigError(RuntimeError):
    pass


def _decode_key(kek_id: str, encoded: str) -> bytes:
    try:
        key = base64.b64decode(encoded.strip(), validate=True)
    except binascii.Error:
        raise KeyConfigError(f"master key {kek_id!r} is not valid base64") from None
    if len(key) != KEY_SIZE:
        raise KeyConfigError(f"master key {kek_id!r} must be {KEY_SIZE} bytes")
    return key


class LocalKeyProvider:
    def __init__(self, current_id: str, keys: dict[str, bytes]) -> None:
        if current_id not in keys:
            raise KeyConfigError("current master key is missing")
        self._current_id = current_id
        self._keys = keys

    @classmethod
    def from_settings(cls, settings: Settings) -> "LocalKeyProvider":
        encoded = settings.master_key
        if settings.master_key_file:
            encoded = Path(settings.master_key_file).read_text().strip()
        if not encoded:
            raise KeyConfigError(
                "ENVO_MASTER_KEY or ENVO_MASTER_KEY_FILE must be set to store variables"
            )
        keys = {settings.master_key_id: _decode_key(settings.master_key_id, encoded)}
        for item in filter(None, (s.strip() for s in settings.retired_master_keys.split(","))):
            kek_id, _, value = item.partition(":")
            if not kek_id or not value:
                raise KeyConfigError("ENVO_RETIRED_MASTER_KEYS must look like 'id:base64,...'")
            keys.setdefault(kek_id, _decode_key(kek_id, value))
        return cls(settings.master_key_id, keys)

    @property
    def current_kek_id(self) -> str:
        return self._current_id

    def wrap_dek(self, environment_id: uuid.UUID, dek: bytes) -> tuple[str, bytes]:
        kek = self._keys[self._current_id]
        return self._current_id, seal(kek, dek, dek_aad(environment_id))

    def unwrap_dek(self, environment_id: uuid.UUID, kek_id: str, wrapped: bytes) -> bytes:
        kek = self._keys.get(kek_id)
        if kek is None:
            raise CryptoError(f"master key {kek_id!r} is not available")
        return open_sealed(kek, wrapped, dek_aad(environment_id))


@lru_cache
def get_key_provider() -> KeyProvider:
    return LocalKeyProvider.from_settings(get_settings())
