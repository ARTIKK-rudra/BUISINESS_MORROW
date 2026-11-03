from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from pwdlib import PasswordHash

from app.core.config import get_settings
from app.core.errors import UnauthorizedError

password_hash = PasswordHash.recommended()
ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, encoded: str) -> bool:
    try:
        return password_hash.verify(password, encoded)
    except (ValueError, TypeError):
        return False


def create_access_token(user_id: UUID, business_id: UUID) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    claims = {
        "sub": str(user_id),
        "business_id": str(business_id),
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_minutes),
        "type": "access",
    }
    return jwt.encode(claims, settings.secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str) -> tuple[UUID, UUID]:
    try:
        claims = jwt.decode(token, get_settings().secret_key, algorithms=[ALGORITHM])
        if claims.get("type") != "access":
            raise ValueError("wrong token type")
        return UUID(claims["sub"]), UUID(claims["business_id"])
    except (jwt.PyJWTError, KeyError, TypeError, ValueError) as exc:
        raise UnauthorizedError("Invalid or expired access token") from exc
