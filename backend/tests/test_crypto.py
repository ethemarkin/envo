import base64
import os
import uuid

import pytest

from app.core.crypto import CryptoError, LocalKeyProvider, decrypt_value, encrypt_value
from app.core.crypto.envelope import generate_dek
from app.core.crypto.keys import KeyConfigError

ENV = uuid.uuid4()


def test_roundtrip_and_random_nonce():
    dek = generate_dek()
    a = encrypt_value(dek, ENV, "API_KEY", "s3cr3t ✓")
    b = encrypt_value(dek, ENV, "API_KEY", "s3cr3t ✓")
    assert a != b
    assert b"s3cr3t" not in a
    assert decrypt_value(dek, ENV, "API_KEY", a) == "s3cr3t ✓"


@pytest.mark.parametrize(
    ("env_id", "key"),
    [(uuid.uuid4(), "API_KEY"), (ENV, "OTHER_KEY")],
    ids=["other-environment", "other-key"],
)
def test_ciphertext_is_bound_to_environment_and_key(env_id, key):
    dek = generate_dek()
    sealed = encrypt_value(dek, ENV, "API_KEY", "value")
    with pytest.raises(CryptoError):
        decrypt_value(dek, env_id, key, sealed)


def test_tampering_and_wrong_key_are_detected():
    dek = generate_dek()
    sealed = bytearray(encrypt_value(dek, ENV, "K", "value"))
    sealed[-1] ^= 1
    with pytest.raises(CryptoError):
        decrypt_value(dek, ENV, "K", bytes(sealed))
    with pytest.raises(CryptoError):
        decrypt_value(generate_dek(), ENV, "K", encrypt_value(dek, ENV, "K", "value"))


def provider(current: str, **keys: bytes) -> LocalKeyProvider:
    return LocalKeyProvider(current, keys)


def test_dek_wrapping_is_bound_to_environment():
    p = provider("k1", k1=os.urandom(32))
    dek = generate_dek()
    kek_id, wrapped = p.wrap_dek(ENV, dek)
    assert kek_id == "k1"
    assert p.unwrap_dek(ENV, kek_id, wrapped) == dek
    with pytest.raises(CryptoError):
        p.unwrap_dek(uuid.uuid4(), kek_id, wrapped)


def test_rotation_keeps_old_keys_for_unwrapping():
    old, new = os.urandom(32), os.urandom(32)
    dek = generate_dek()
    _, wrapped = provider("k1", k1=old).wrap_dek(ENV, dek)
    rotated = provider("k2", k2=new, k1=old)
    assert rotated.unwrap_dek(ENV, "k1", wrapped) == dek
    assert rotated.wrap_dek(ENV, dek)[0] == "k2"
    with pytest.raises(CryptoError):
        provider("k2", k2=new).unwrap_dek(ENV, "k1", wrapped)


def test_settings_validation():
    from app.core.config import Settings

    def settings(**kw):
        return Settings(secret_key="x" * 40, **kw)

    with pytest.raises(KeyConfigError):
        LocalKeyProvider.from_settings(settings(master_key=None))
    with pytest.raises(KeyConfigError):
        LocalKeyProvider.from_settings(settings(master_key=base64.b64encode(b"short").decode()))
    good = base64.b64encode(os.urandom(32)).decode()
    old = base64.b64encode(os.urandom(32)).decode()
    p = LocalKeyProvider.from_settings(
        settings(master_key=good, master_key_id="k2", retired_master_keys=f"k1:{old}")
    )
    assert p.current_kek_id == "k2"
