"""Token encryption + password hashing."""
import os
import bcrypt
from cryptography.fernet import Fernet, InvalidToken


def _fernet() -> Fernet:
    key = os.environ.get("TOKEN_ENC_KEY", "").strip()
    if not key:
        raise RuntimeError("TOKEN_ENC_KEY env missing")
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_token(raw: str) -> str:
    return _fernet().encrypt(raw.encode("utf-8")).decode("utf-8")


def decrypt_token(token_enc: str) -> str:
    try:
        return _fernet().decrypt(token_enc.encode("utf-8")).decode("utf-8")
    except InvalidToken as e:
        raise ValueError("token decrypt failed") from e


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except Exception:
        return False
