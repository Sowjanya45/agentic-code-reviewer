from cryptography.fernet import Fernet

from server import crypto


def test_encrypt_decrypt_roundtrip(monkeypatch):
    monkeypatch.setenv("ENCRYPTION_KEY", Fernet.generate_key().decode())
    ciphertext = crypto.encrypt("hello secret")
    assert ciphertext != "hello secret"
    assert crypto.decrypt(ciphertext) == "hello secret"


def test_different_keys_cannot_decrypt_each_others_ciphertext(monkeypatch):
    monkeypatch.setenv("ENCRYPTION_KEY", Fernet.generate_key().decode())
    ciphertext = crypto.encrypt("hello secret")

    monkeypatch.setenv("ENCRYPTION_KEY", Fernet.generate_key().decode())
    try:
        crypto.decrypt(ciphertext)
        assert False, "decrypting with the wrong key should raise"
    except Exception:
        pass
