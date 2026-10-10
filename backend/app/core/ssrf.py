"""SSRF protection utilities — prevent handlers from contacting internal networks."""
from __future__ import annotations

import ipaddress
import logging
import socket
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

_CGNAT_NETWORK = ipaddress.ip_network("100.64.0.0/10")


def _is_disallowed_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    ):
        return True
    if isinstance(ip, ipaddress.IPv4Address) and ip in _CGNAT_NETWORK:
        return True
    return False


def validate_url_ssrf_safe(url: str) -> None:
    """Validate that a URL does not resolve to an internal/private IP address.

    Raises:
        ValueError: If scheme is not http/https or if the URL's hostname resolves to a
            private, loopback, link-local, multicast, or CGNAT IP address.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(
            f"SSRF protection: invalid URL scheme '{parsed.scheme}'. Only http and https are allowed."
        )

    hostname = parsed.hostname
    if not hostname:
        raise ValueError(f"Invalid URL: could not resolve hostname from {url}")

    try:
        addr_info = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError(f"Could not resolve hostname '{hostname}': {exc}") from exc

    seen_ips: set[str] = set()
    for family, socktype, proto, canonname, sockaddr in addr_info:
        ip_str = sockaddr[0]
        if ip_str in seen_ips:
            continue
        seen_ips.add(ip_str)

        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue

        if _is_disallowed_ip(ip):
            raise ValueError(
                f"SSRF protection: hostname '{hostname}' resolves to "
                f"internal IP address {ip_str}. Refusing to make request."
            )

    if not seen_ips:
        raise ValueError(f"SSRF protection: hostname '{hostname}' did not resolve to any IP address.")
