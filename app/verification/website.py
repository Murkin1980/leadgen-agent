from __future__ import annotations

import ipaddress
import logging
import socket
from urllib.parse import urlparse

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class WebsiteVerificationError(Exception):
    """Error during website verification."""
    pass


class WebsiteVerifier:
    """Verifies if a website is reachable with SSRF protection."""

    PRIVATE_NETWORKS = [
        ipaddress.ip_network("10.0.0.0/8"),
        ipaddress.ip_network("172.16.0.0/12"),
        ipaddress.ip_network("192.168.0.0/16"),
        ipaddress.ip_network("127.0.0.0/8"),
        ipaddress.ip_network("169.254.0.0/16"),
        ipaddress.ip_network("::1/128"),
        ipaddress.ip_network("fc00::/7"),
        ipaddress.ip_network("fe80::/10"),
    ]

    def __init__(
        self,
        timeout: float | None = None,
        max_redirects: int | None = None,
        user_agent: str | None = None,
    ):
        self.timeout = timeout or settings.verification_timeout
        self.max_redirects = max_redirects or settings.verification_max_redirects
        self.user_agent = user_agent or settings.verification_user_agent

    def _is_private_ip(self, ip: str) -> bool:
        """Check if IP address is in private/reserved range."""
        try:
            addr = ipaddress.ip_address(ip)
            for network in self.PRIVATE_NETWORKS:
                if addr in network:
                    return True
            return False
        except ValueError:
            return True

    def _resolve_hostname(self, hostname: str) -> list[str]:
        """Resolve hostname and check for private IPs."""
        try:
            ips = socket.getaddrinfo(hostname, None)
            resolved_ips = set()
            for family, _, _, _, sockaddr in ips:
                ip = sockaddr[0]
                resolved_ips.add(ip)
                if self._is_private_ip(ip):
                    raise WebsiteVerificationError(
                        f"SSRF blocked: {hostname} resolves to private IP {ip}"
                    )
            return list(resolved_ips)
        except socket.gaierror as e:
            raise WebsiteVerificationError(f"DNS resolution failed for {hostname}: {e}")

    def _validate_url(self, url: str) -> str:
        """Validate URL and return normalized version."""
        if not url:
            raise WebsiteVerificationError("URL is empty")

        url = url.strip()
        if not url.startswith(("http://", "https://")):
            url = "http://" + url

        try:
            parsed = urlparse(url)
        except Exception as e:
            raise WebsiteVerificationError(f"Invalid URL: {e}")

        if not parsed.hostname:
            raise WebsiteVerificationError(f"No hostname in URL: {url}")

        if parsed.hostname in ("localhost", "127.0.0.1", "::1"):
            raise WebsiteVerificationError("SSRF blocked: localhost URL")

        if parsed.hostname.endswith(".local"):
            raise WebsiteVerificationError("SSRF blocked: .local domain")

        return url

    def verify(self, url: str) -> dict:
        """
        Verify if a website is reachable.
        
        Returns:
            dict with keys:
                - status: "ok" | "unreachable" | "has_website" | "error"
                - status_code: int | None
                - redirect_url: str | None
                - error: str | None
        """
        if not settings.verification_enabled:
            return {"status": "ok", "status_code": None, "redirect_url": None, "error": None}

        try:
            normalized_url = self._validate_url(url)
            parsed = urlparse(normalized_url)
            
            self._resolve_hostname(parsed.hostname)

            with httpx.Client(
                timeout=self.timeout,
                max_redirects=self.max_redirects,
                follow_redirects=True,
                headers={"User-Agent": self.user_agent},
            ) as client:
                response = client.head(normalized_url, allow_redirects=True)

                redirect_url = str(response.url) if str(response.url) != normalized_url else None

                if response.status_code < 400:
                    return {
                        "status": "has_website",
                        "status_code": response.status_code,
                        "redirect_url": redirect_url,
                        "error": None,
                    }
                else:
                    return {
                        "status": "unreachable",
                        "status_code": response.status_code,
                        "redirect_url": redirect_url,
                        "error": f"HTTP {response.status_code}",
                    }

        except WebsiteVerificationError as e:
            return {
                "status": "unreachable",
                "status_code": None,
                "redirect_url": None,
                "error": str(e),
            }
        except httpx.TimeoutException:
            return {
                "status": "unreachable",
                "status_code": None,
                "redirect_url": None,
                "error": "Timeout",
            }
        except httpx.RequestError as e:
            return {
                "status": "unreachable",
                "status_code": None,
                "redirect_url": None,
                "error": f"Request error: {e}",
            }
        except Exception as e:
            return {
                "status": "error",
                "status_code": None,
                "redirect_url": None,
                "error": f"Unexpected error: {e}",
            }


def verify_website(url: str) -> dict:
    """Convenience function to verify a website."""
    verifier = WebsiteVerifier()
    return verifier.verify(url)
