"""Tests for core configuration and utilities."""

import pytest
from datetime import timedelta

from app.core.config import Settings, get_settings
from app.core.security import (
    create_access_token,
    decode_access_token,
    get_password_hash,
    verify_password,
)


def test_settings_defaults() -> None:
    """Test default settings values."""
    settings = Settings()
    assert settings.app_name == "Thailand Railway Digital Twin"
    assert settings.debug is False
    assert settings.api_v1_prefix == "/api/v1"


def test_settings_cors_parsing() -> None:
    """Test CORS origins can be parsed from string."""
    settings = Settings(cors_origins="http://localhost:3000,http://localhost:8080")
    assert len(settings.cors_origins) == 2
    assert "http://localhost:3000" in settings.cors_origins
    assert "http://localhost:8080" in settings.cors_origins


def test_get_settings_cached() -> None:
    """Test settings are cached."""
    settings1 = get_settings()
    settings2 = get_settings()
    assert settings1 is settings2


def test_password_hashing() -> None:
    """Test password hashing and verification."""
    password = "test_password_123"
    hashed = get_password_hash(password)

    assert hashed != password
    assert verify_password(password, hashed)
    assert not verify_password("wrong_password", hashed)


def test_create_access_token() -> None:
    """Test JWT token creation."""
    subject = "user_123"
    token = create_access_token(subject)

    assert token is not None
    assert isinstance(token, str)
    assert len(token) > 0


def test_decode_access_token() -> None:
    """Test JWT token decoding."""
    subject = "user_456"
    token = create_access_token(subject)
    payload = decode_access_token(token)

    assert payload is not None
    assert payload.sub == subject


def test_decode_invalid_token() -> None:
    """Test decoding invalid token returns None."""
    payload = decode_access_token("invalid_token")
    assert payload is None


def test_token_with_custom_expiry() -> None:
    """Test token creation with custom expiration."""
    subject = "user_789"
    expires = timedelta(hours=1)
    token = create_access_token(subject, expires_delta=expires)
    payload = decode_access_token(token)

    assert payload is not None
    assert payload.sub == subject
