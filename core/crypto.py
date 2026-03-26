"""
Шифрование токенов перед сохранением в БД.
Использует Fernet (AES-128-CBC + HMAC-SHA256).

Если DB_ENCRYPTION_KEY не задан — возвращает строку как есть
(plain text, небезопасно, только для локальной разработки).
"""
from loguru import logger

try:
    from cryptography.fernet import Fernet, InvalidToken
    _CRYPTO_AVAILABLE = True
except ImportError:
    _CRYPTO_AVAILABLE = False

from config import settings

_fernet = None


def _get_fernet():
    global _fernet
    if _fernet is not None:
        return _fernet
    key = settings.db_encryption_key.strip()
    if not key:
        return None
    if not _CRYPTO_AVAILABLE:
        logger.warning("cryptography не установлена — токены хранятся plain text")
        return None
    try:
        _fernet = Fernet(key.encode())
        return _fernet
    except Exception as e:
        logger.error(f"Неверный DB_ENCRYPTION_KEY: {e}")
        return None


def encrypt_token(token: str) -> str:
    """Шифрует токен для хранения в БД. Возвращает base64-строку."""
    f = _get_fernet()
    if f is None:
        return token
    return f.encrypt(token.encode()).decode()


def decrypt_token(value: str) -> str:
    """Расшифровывает токен из БД. Если ключа нет или значение пустое — возвращает как есть."""
    f = _get_fernet()
    if f is None:
        return value
    if not value:
        return value
    try:
        return f.decrypt(value.encode()).decode()
    except Exception:
        logger.error("Не удалось расшифровать токен — ключ сменился или токен повреждён")
        raise ValueError("Token decryption failed")
