import os
import uuid

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

FORMAT_V1 = 1
NONCE_SIZE = 12
KEY_SIZE = 32


class CryptoError(Exception):
    """Decryption failed: wrong key, wrong context or tampered data."""


def generate_dek() -> bytes:
    return os.urandom(KEY_SIZE)


def value_aad(environment_id: uuid.UUID, key: str) -> bytes:
    return f"envo:v1:{environment_id}:{key}".encode()


def dek_aad(environment_id: uuid.UUID) -> bytes:
    return f"envo:dek:v1:{environment_id}".encode()


def seal(key: bytes, plaintext: bytes, aad: bytes) -> bytes:
    nonce = os.urandom(NONCE_SIZE)
    return bytes([FORMAT_V1]) + nonce + AESGCM(key).encrypt(nonce, plaintext, aad)


def open_sealed(key: bytes, sealed: bytes, aad: bytes) -> bytes:
    if len(sealed) < 1 + NONCE_SIZE + 16 or sealed[0] != FORMAT_V1:
        raise CryptoError("unsupported ciphertext format")
    nonce, ciphertext = sealed[1 : 1 + NONCE_SIZE], sealed[1 + NONCE_SIZE :]
    try:
        return AESGCM(key).decrypt(nonce, ciphertext, aad)
    except InvalidTag:
        raise CryptoError("decryption failed") from None


def encrypt_value(dek: bytes, environment_id: uuid.UUID, key: str, value: str) -> bytes:
    return seal(dek, value.encode(), value_aad(environment_id, key))


def decrypt_value(dek: bytes, environment_id: uuid.UUID, key: str, sealed: bytes) -> str:
    return open_sealed(dek, sealed, value_aad(environment_id, key)).decode()
