"""SSRFGuard — blocks requests to private/internal IPs with DNS pinning."""

from __future__ import annotations

import ipaddress
import logging
import socket
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

# RFC reserved ranges that must never be targeted directly.
_BLOCKED_NETWORKS: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = [
    ipaddress.IPv4Network("10.0.0.0/8"),
    ipaddress.IPv4Network("172.16.0.0/12"),
    ipaddress.IPv4Network("192.168.0.0/16"),
    ipaddress.IPv4Network("127.0.0.0/8"),       # loopback
    ipaddress.IPv4Network("169.254.0.0/16"),     # link-local
    ipaddress.IPv4Network("224.0.0.0/4"),        # multicast
    ipaddress.IPv4Network("240.0.0.0/4"),        # reserved
    ipaddress.IPv4Network("0.0.0.0/8"),
    ipaddress.IPv6Network("::1/128"),
    ipaddress.IPv6Network("fc00::/7"),            # ULA
    ipaddress.IPv6Network("fe80::/10"),           # link-local
    ipaddress.IPv6Network("ff00::/8"),            # multicast
]


# --------------------------------------------------------------------------- #
# CheckedURL                                                                    #
# --------------------------------------------------------------------------- #

@dataclass
class CheckedURL:
    """Result of an SSRF check."""
    url: str
    safe: bool
    resolved_ip: str = ""
    reason: str = ""
    blocked_network: str = ""


# --------------------------------------------------------------------------- #
# SSRFGuard                                                                     #
# --------------------------------------------------------------------------- #

class SSRFGuard:
    """Validates URLs before fetching to prevent SSRF attacks.

    Usage::

        guard = SSRFGuard()
        result = guard.check_url("http://169.254.169.254/metadata")
        if not result.safe:
            raise RuntimeError(result.reason)
    """

    def __init__(
        self,
        extra_blocked: list[str] | None = None,
        allow_localhost: bool = False,
        dns_timeout: float = 5.0,
    ) -> None:
        self.allow_localhost = allow_localhost
        self.dns_timeout = dns_timeout
        self.blocked_networks = list(_BLOCKED_NETWORKS)

        if extra_blocked:
            for cidr in extra_blocked:
                try:
                    net = ipaddress.ip_network(cidr, strict=False)
                    self.blocked_networks.append(net)
                except ValueError:
                    logger.warning("SSRFGuard: invalid CIDR '%s' ignored", cidr)

    def check_url(self, url: str) -> CheckedURL:
        """Resolve *url* and verify the target IP is not in a blocked range."""
        try:
            parsed = urlparse(url)
        except Exception as exc:
            return CheckedURL(url=url, safe=False, reason=f"Invalid URL: {exc}")

        if parsed.scheme not in ("http", "https"):
            return CheckedURL(url=url, safe=False, reason=f"Unsupported scheme: {parsed.scheme}")

        hostname = parsed.hostname
        if not hostname:
            return CheckedURL(url=url, safe=False, reason="No hostname in URL")

        # DNS resolution with pinning.
        try:
            resolved = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM, 0, socket.AI_NUMERICHOST)
        except socket.gaierror as exc:
            return CheckedURL(url=url, safe=False, reason=f"DNS resolution failed: {exc}")

        for family, _socktype, _proto, _canonname, sockaddr in resolved:
            ip_str = sockaddr[0]
            try:
                ip = ipaddress.ip_address(ip_str)
            except ValueError:
                continue

            if not self.allow_localhost and ip.is_loopback:
                return CheckedURL(
                    url=url,
                    safe=False,
                    resolved_ip=ip_str,
                    reason="Loopback address blocked",
                )

            for net in self.blocked_networks:
                if ip in net:
                    return CheckedURL(
                        url=url,
                        safe=False,
                        resolved_ip=ip_str,
                        reason=f"IP {ip_str} falls in blocked network {net}",
                        blocked_network=str(net),
                    )

        return CheckedURL(url=url, safe=True, resolved_ip=ip_str if resolved else "")

    async def safe_get(
        self,
        url: str,
        timeout: float = 30.0,
        follow_redirects: bool = False,
        **kwargs: Any,
    ) -> httpx.Response:
        """Perform a GET request only if the URL passes the SSRF check.

        Redirects are not followed by default.  When they are followed, each
        intermediate Location header is re-validated.
        """
        check = self.check_url(url)
        if not check.safe:
            raise ValueError(f"SSRF blocked: {check.reason} (url={url})")

        headers = kwargs.pop("headers", {})
        headers.setdefault("User-Agent", "NexusForge-SSRFGuard/1.0")

        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=follow_redirects,
            max_redirects=5,
        ) as client:
            response = await client.get(url, headers=headers, **kwargs)

            if follow_redirects:
                # Re-validate each redirect.
                for hist in response.history:
                    redirect_url = str(hist.headers.get("location", ""))
                    if redirect_url:
                        redir_check = self.check_url(redirect_url)
                        if not redir_check.safe:
                            raise ValueError(
                                f"SSRF blocked on redirect: {redir_check.reason} "
                                f"(url={redirect_url})"
                            )

        return response

    async def safe_post(
        self,
        url: str,
        data: Any = None,
        timeout: float = 30.0,
        **kwargs: Any,
    ) -> httpx.Response:
        """Perform a POST request only if the URL passes the SSRF check."""
        check = self.check_url(url)
        if not check.safe:
            raise ValueError(f"SSRF blocked: {check.reason} (url={url})")

        headers = kwargs.pop("headers", {})
        headers.setdefault("User-Agent", "NexusForge-SSRFGuard/1.0")

        async with httpx.AsyncClient(timeout=timeout) as client:
            return await client.post(url, data=data, headers=headers, **kwargs)
