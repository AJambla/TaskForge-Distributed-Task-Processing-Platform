"""Unit tests for SSRF protection."""
import pytest

from app.core.ssrf import validate_url_ssrf_safe


def test_valid_public_url():
    validate_url_ssrf_safe("https://example.com/image.png")


def test_valid_http_url():
    validate_url_ssrf_safe("http://httpbin.org/get")


def test_loopback_rejected():
    with pytest.raises(ValueError, match="SSRF protection"):
        validate_url_ssrf_safe("http://127.0.0.1:8080/secret")


def test_private_ip_rejected():
    with pytest.raises(ValueError, match="SSRF protection"):
        validate_url_ssrf_safe("http://10.0.0.1/internal")


def test_link_local_rejected():
    with pytest.raises(ValueError, match="SSRF protection"):
        validate_url_ssrf_safe("http://169.254.169.254/latest/meta-data")


def test_empty_hostname_rejected():
    with pytest.raises(ValueError):
        validate_url_ssrf_safe("://invalid-url")
