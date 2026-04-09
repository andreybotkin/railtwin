"""Security utilities for authentication and authorization.

This module provides JWT token handling and password hashing utilities
for securing the application.
"""

from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

from app.core.config import settings

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class Token(BaseModel):
    """JWT token response model.

    Attributes:
        access_token: The JWT access token string.
        token_type: Token type (always "bearer").
    """

    access_token: str
    token_type: str = "bearer"


class TokenPayload(BaseModel):
    """JWT token payload model.

    Attributes:
        sub: Subject (typically user ID).
        exp: Expiration timestamp.
    """

    sub: str | None = None
    exp: datetime | None = None


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash.

    Args:
        plain_password: The plain text password to verify.
        hashed_password: The hashed password to compare against.

    Returns:
        bool: True if password matches, False otherwise.
    """
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Generate a hash from a password.

    Args:
        password: The plain text password to hash.

    Returns:
        str: The hashed password.
    """
    return pwd_context.hash(password)


def create_access_token(
    subject: str,
    expires_delta: timedelta | None = None,
) -> str:
    """Create a JWT access token.

    Args:
        subject: The subject to encode in the token (typically user ID).
        expires_delta: Optional custom expiration time delta.

    Returns:
        str: The encoded JWT token.
    """
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta  # noqa: UP017
    else:
        expire = datetime.now(timezone.utc) + timedelta(   # noqa: UP017
            minutes=settings.access_token_expire_minutes
        )  # noqa: UP017

    to_encode = {"exp": expire, "sub": str(subject)}
    encoded_jwt = jwt.encode(
        to_encode,
        settings.secret_key,
        algorithm=settings.algorithm,
    )
    return encoded_jwt


def decode_access_token(token: str) -> TokenPayload | None:
    """Decode and validate a JWT access token.

    Args:
        token: The JWT token to decode.

    Returns:
        TokenPayload | None: The decoded token payload, or None if invalid.
    """
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.algorithm],
        )
        return TokenPayload(**payload)
    except JWTError:
        return None
