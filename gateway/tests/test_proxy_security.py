"""Tests for gateway proxy security improvements."""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute

from app.main import ALLOWED_HEADERS, SENSITIVE_HEADERS, _validate_path, app


class TestValidatePath:
    """Tests for path validation to prevent SSRF attacks."""

    def test_valid_path_passes(self) -> None:
        """Normal API paths should pass validation."""
        _validate_path("stations")
        _validate_path("trains/123/trajectory")
        _validate_path("routes/1/stations")

    def test_path_with_scheme_raises(self) -> None:
        """Paths containing URL schemes should be rejected."""
        with pytest.raises(HTTPException) as exc_info:
            _validate_path("http://internal-service/admin")
        assert exc_info.value.status_code == 400

    def test_path_with_double_slash_raises(self) -> None:
        """Paths starting with // should be rejected (SSRF attempt)."""
        with pytest.raises(HTTPException) as exc_info:
            _validate_path("//internal-service/admin")
        assert exc_info.value.status_code == 400

    def test_path_with_null_byte_raises(self) -> None:
        """Paths containing null bytes should be rejected."""
        with pytest.raises(HTTPException) as exc_info:
            _validate_path("stations\0admin")
        assert exc_info.value.status_code == 400

    def test_empty_path_passes(self) -> None:
        """Empty path should be allowed."""
        _validate_path("")


class TestHeaderFiltering:
    """Tests for header filtering in proxy."""

    def test_sensitive_headers_are_blocked(self) -> None:
        """Sensitive headers must never enter the forwarding allowlist."""
        assert {
            "authorization",
            "cookie",
            "x-api-key",
            "x-auth-token",
        } <= SENSITIVE_HEADERS
        assert SENSITIVE_HEADERS.isdisjoint(ALLOWED_HEADERS)

    def test_allowed_headers_are_whitelisted(self) -> None:
        """Only safe headers should be forwarded."""
        assert "accept" in ALLOWED_HEADERS
        assert "content-type" in ALLOWED_HEADERS
        assert "if-none-match" in ALLOWED_HEADERS
        assert "authorization" not in ALLOWED_HEADERS
        assert "cookie" not in ALLOWED_HEADERS


class TestPublicProxyMethods:
    """Regression tests for the internet-facing read-only API contract."""

    def test_catch_all_proxy_is_read_only(self) -> None:
        route = next(
            candidate
            for candidate in app.routes
            if isinstance(candidate, APIRoute)
            and candidate.path == "/api/v1/{path:path}"
        )

        assert route.methods == {"GET", "HEAD", "OPTIONS"}
        assert not ({"POST", "PUT", "PATCH", "DELETE"} & route.methods)
