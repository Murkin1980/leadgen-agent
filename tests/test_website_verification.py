import pytest
from unittest.mock import patch, MagicMock

from app.verification.website import WebsiteVerifier, verify_website


class TestWebsiteVerifier:
    def test_validate_url_empty(self):
        verifier = WebsiteVerifier()
        with pytest.raises(Exception):
            verifier._validate_url("")

    def test_validate_url_adds_http(self):
        verifier = WebsiteVerifier()
        result = verifier._validate_url("example.com")
        assert result == "http://example.com"

    def test_validate_url_keeps_https(self):
        verifier = WebsiteVerifier()
        result = verifier._validate_url("https://example.com")
        assert result == "https://example.com"

    def test_validate_url_rejects_localhost(self):
        verifier = WebsiteVerifier()
        with pytest.raises(Exception):
            verifier._validate_url("http://localhost/test")

    def test_validate_url_rejects_127(self):
        verifier = WebsiteVerifier()
        with pytest.raises(Exception):
            verifier._validate_url("http://127.0.0.1/test")

    def test_validate_url_rejects_local_domain(self):
        verifier = WebsiteVerifier()
        with pytest.raises(Exception):
            verifier._validate_url("http://mycomputer.local/test")

    def test_is_private_ip_10(self):
        verifier = WebsiteVerifier()
        assert verifier._is_private_ip("10.0.0.1") is True

    def test_is_private_ip_192(self):
        verifier = WebsiteVerifier()
        assert verifier._is_private_ip("192.168.1.1") is True

    def test_is_private_ip_public(self):
        verifier = WebsiteVerifier()
        assert verifier._is_private_ip("8.8.8.8") is False

    def test_is_private_ip_localhost(self):
        verifier = WebsiteVerifier()
        assert verifier._is_private_ip("127.0.0.1") is True

    def test_is_private_ip_invalid(self):
        verifier = WebsiteVerifier()
        assert verifier._is_private_ip("not_an_ip") is True


class TestWebsiteVerification:
    def test_verify_disabled(self):
        with patch("app.verification.website.settings") as mock_settings:
            mock_settings.verification_enabled = False
            result = verify_website("http://example.com")
            assert result["status"] == "ok"

    def test_verify_empty_url(self):
        with patch("app.verification.website.settings") as mock_settings:
            mock_settings.verification_enabled = True
            result = verify_website("")
            assert result["status"] == "unreachable"

    def test_verify_ssrf_blocked(self):
        with patch("app.verification.website.settings") as mock_settings:
            mock_settings.verification_enabled = True
            result = verify_website("http://localhost/test")
            assert result["status"] == "unreachable"
            assert "SSRF" in result["error"]

    @patch("app.verification.website.httpx.Client")
    def test_verify_success(self, mock_client_class):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.url = "http://example.com"
        
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.head.return_value = mock_response
        mock_client_class.return_value = mock_client
        
        with patch("app.verification.website.settings") as mock_settings:
            mock_settings.verification_enabled = True
            mock_settings.verification_timeout = 5.0
            mock_settings.verification_max_redirects = 3
            mock_settings.verification_user_agent = "TestBot"
            
            with patch("socket.getaddrinfo", return_value=[(2, None, None, None, ("93.184.216.34", 0))]):
                result = verify_website("http://example.com")
                assert result["status"] == "has_website"
                assert result["status_code"] == 200

    @patch("app.verification.website.httpx.Client")
    def test_verify_timeout(self, mock_client_class):
        import httpx
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.head.side_effect = httpx.TimeoutException("timeout")
        mock_client_class.return_value = mock_client
        
        with patch("app.verification.website.settings") as mock_settings:
            mock_settings.verification_enabled = True
            mock_settings.verification_timeout = 1.0
            mock_settings.verification_max_redirects = 3
            mock_settings.verification_user_agent = "TestBot"
            
            with patch("socket.getaddrinfo", return_value=[(2, None, None, None, ("93.184.216.34", 0))]):
                result = verify_website("http://example.com")
                assert result["status"] == "unreachable"
                assert "Timeout" in result["error"]
