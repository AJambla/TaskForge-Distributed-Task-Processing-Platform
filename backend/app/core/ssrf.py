"""SSRF protection utilities — prevent handlers from contacting internal networks."""
from __future__ import annotations

import ipaddress
import logging
import socket
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


def validate_url_ssrf_safe(url: str) -> None:
    """Validate that a URL does not resolve to an internal/private IP address.

    Raises:
        ValueError: If the URL's hostname resolves to a private, loopback,
            link-local, or multicast IP address.
    """
    parsed = urlparse(url)
    hostname = parsed.hostname
    if not hostname:
        raise ValueError(f"Invalid URL: could not resolve hostname from {url}")

    try:
        addr_info = socket.getaddrinfo(hostname, None, socket.AF_INET, socket.SOCK_STREAM)
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

        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast:
            raise ValueError(
                f"SSRF protection: hostname '{hostname}' resolves to "
                f"internal IP address {ip_str}. Refusing to make request."
            )

    if not seen_ips:
        raise ValueError(f"SSRF protection: hostname '{hostname}' did not resolve to any IPv4 address.")
