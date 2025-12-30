from passlib.context import CryptContext
from fastapi import Request
from typing import Optional

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

SESSION_COOKIE = "xz_session_user_id"


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def get_current_user_id(request: Request) -> Optional[int]:
    v = request.cookies.get(SESSION_COOKIE)
    if not v:
        return None
    try:
        return int(v)
    except Exception:
        return None
