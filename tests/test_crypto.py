"""Unit tests for core/crypto.py."""
import pytest
from unittest.mock import MagicMock, patch

import core.crypto as crypto_mod
from core.crypto import decrypt_token, encrypt_token


@pytest.fixture(autouse=True)
def reset_fernet():
    """Reset cached Fernet instance before/after each test to avoid cross-test state."""
    original = crypto_mod._fernet
    crypto_mod._fernet = None
    yield
    crypto_mod._fernet = original


def _mock_settings(key: str) -> MagicMock:
    s = MagicMock()
    s.db_encryption_key = key
    return s


# ---------------------------------------------------------------------------
# Basic encrypt / decrypt
# ---------------------------------------------------------------------------

def test_encrypt_decrypt_roundtrip():
    from cryptography.fernet import Fernet
    key = Fernet.generate_key().decode()

    with patch("core.crypto.settings", _mock_settings(key)):
        original = "my_secret_token_abc123"
        encrypted = encrypt_token(original)

        assert encrypted != original  # ciphertext differs from plaintext
        assert decrypt_token(encrypted) == original


def test_encrypt_produces_different_ciphertexts_each_call():
    """Fernet uses random IV → same plaintext produces different ciphertexts."""
    from cryptography.fernet import Fernet
    key = Fernet.generate_key().decode()

    with patch("core.crypto.settings", _mock_settings(key)):
        t1 = encrypt_token("token")
        crypto_mod._fernet = None  # force re-init between calls
        t2 = encrypt_token("token")
    # Different ciphertexts (different random IVs)
    assert t1 != t2


# ---------------------------------------------------------------------------
# No key → passthrough
# ---------------------------------------------------------------------------

def test_no_key_encrypt_passthrough():
    with patch("core.crypto.settings", _mock_settings("")):
        token = "plain_token"
        assert encrypt_token(token) == token


def test_no_key_decrypt_passthrough():
    with patch("core.crypto.settings", _mock_settings("")):
        token = "plain_token"
        assert decrypt_token(token) == token


# ---------------------------------------------------------------------------
# Graceful fallback on invalid / plain-text stored token
# ---------------------------------------------------------------------------

def test_decrypt_invalid_token_raises():
    """An invalid/corrupt token should raise ValueError (not silently pass through)."""
    from cryptography.fernet import Fernet
    key = Fernet.generate_key().decode()

    with patch("core.crypto.settings", _mock_settings(key)):
        with pytest.raises(ValueError, match="Token decryption failed"):
            decrypt_token("not_a_fernet_token")


def test_decrypt_empty_string_returns_empty():
    """Empty string means no token stored — return as-is without attempting decryption."""
    from cryptography.fernet import Fernet
    key = Fernet.generate_key().decode()

    with patch("core.crypto.settings", _mock_settings(key)):
        result = decrypt_token("")
    assert result == ""


# ---------------------------------------------------------------------------
# Invalid key in settings → graceful degradation
# ---------------------------------------------------------------------------

def test_invalid_key_falls_back_to_passthrough():
    with patch("core.crypto.settings", _mock_settings("not_a_valid_fernet_key")):
        token = "raw"
        assert encrypt_token(token) == token
        assert decrypt_token(token) == token


# ---------------------------------------------------------------------------
# Different keys cannot cross-decrypt
# ---------------------------------------------------------------------------

def test_different_keys_cannot_cross_decrypt():
    from cryptography.fernet import Fernet
    key_a = Fernet.generate_key().decode()
    key_b = Fernet.generate_key().decode()

    with patch("core.crypto.settings", _mock_settings(key_a)):
        encrypted = encrypt_token("secret")

    crypto_mod._fernet = None
    with patch("core.crypto.settings", _mock_settings(key_b)):
        # Decrypting with wrong key should raise ValueError
        with pytest.raises(ValueError, match="Token decryption failed"):
            decrypt_token(encrypted)
