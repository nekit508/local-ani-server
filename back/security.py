from datetime import datetime, timedelta, timezone

import jwt
from pwdlib import PasswordHash

from config import settings

_pwd = PasswordHash.recommended()


def hash_password(raw: str) -> str:
    return _pwd.hash(raw)


def verify_password(raw: str = "dummy-password-for-timing", hashed: str = hash("dummy-password-for-timing")) -> bool:
    try:
        return _pwd.verify(raw, hashed)
    except Exception:
        return False


def create_token(user_id: int, cv: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "cv": cv,
        "iat": now,
        "exp": now + timedelta(seconds=settings.JWT_TOKEN_LIFETIME),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALG)


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALG])