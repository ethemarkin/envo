"""Envelope encryption for variable values.

- A master key (KEK) is supplied from outside the database by a KeyProvider.
- Every environment has its own random data key (DEK), stored wrapped by the
  KEK on the environment row together with the KEK id.
- Values are encrypted with AES-256-GCM under the environment's DEK. The AAD
  binds each ciphertext to its environment, folder and key name, so a ciphertext copied
  to another row fails to decrypt.

Stored value format: version (1 byte) | nonce (12 bytes) | ciphertext + tag.
"""

from app.core.crypto.envelope import (
    CryptoError,
    decrypt_value,
    encrypt_value,
    generate_dek,
)
from app.core.crypto.keys import KeyProvider, LocalKeyProvider, get_key_provider

__all__ = [
    "CryptoError",
    "KeyProvider",
    "LocalKeyProvider",
    "decrypt_value",
    "encrypt_value",
    "generate_dek",
    "get_key_provider",
]
