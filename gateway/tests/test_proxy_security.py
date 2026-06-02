"""Tests for gateway proxy security improvements."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.main import ALLOWED_HEADERS, SENSITIVE_HEADERS, _validate_path


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
        """Sensitive headers should be in the blocked list."""
        assert "authorization" in SENSITIVE_HEADERS
        assert "cookie" in SENSITIVE_HEADERS
<<<<<<< ours
<<<<<<< ours
        assert "x-api-key" in SENSITIVE_HEADERS
=======
        # Headers in SENSITIVE_HEADERS preserve original case - check lowercase version
        assert any("x-api-key" == h.lower() for h in SENSITIVE_HEADERS)
        assert any("x-auth-token" == h.lower() for h in SENSITIVE_HEADERS)
>>>>>>> theirs
=======
        # Headers in SENSITIVE_HEADERS preserve original case - check lowercase version
        assert any(h.lower() == "x-api-key" for h in SENSITIVE_HEADERS)
        assert any(h.lower() == "x-auth-token" for h in SENSITIVE_HEADERS)
>>>>>>> theirs

    def test_allowed_headers_are_whitelisted(self) -> None:
        """Only safe headers should be forwarded."""
        assert "accept" in ALLOWED_HEADERS
        assert "content-type" in ALLOWED_HEADERS
        assert "if-none-match" in ALLOWED_HEADERS
        assert "authorization" not in ALLOWED_HEADERS
<<<<<<< ours
<<<<<<< ours
        assert "cookie" not in ALLOWED_HEADERS
=======
        assert "cookie" not in ALLOWED_HEADERS
>>>>>>> theirs
=======
        assert "cookie" not in ALLOWED_HEADERS
>>>>>>> theirs
