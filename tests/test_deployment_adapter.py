import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from app.deployment.base import DeploymentResult
from app.deployment.mock import MockDeploymentAdapter
from app.deployment.cloudflare import CloudflarePagesDeploymentAdapter
from app.config import settings


class TestMockDeploymentAdapter:
    def test_mock_deploy_success(self, tmp_path):
        index = tmp_path / "index.html"
        index.write_text("<html>test</html>")

        adapter = MockDeploymentAdapter()
        result = adapter.deploy(tmp_path)

        assert result.success is True
        assert "mock-deployment" in result.deployment_id
        assert result.url.startswith("https://")

    def test_mock_deploy_missing_dir(self, tmp_path):
        adapter = MockDeploymentAdapter()
        result = adapter.deploy(tmp_path / "nonexistent")

        assert result.success is False
        assert "does not exist" in result.error

    def test_mock_deploy_no_index(self, tmp_path):
        (tmp_path / "other.html").write_text("<html></html>")

        adapter = MockDeploymentAdapter()
        result = adapter.deploy(tmp_path)

        assert result.success is False
        assert "No index.html" in result.error

    def test_mock_deploy_has_index_in_subdir(self, tmp_path):
        subdir = tmp_path / "my-landing"
        subdir.mkdir()
        (subdir / "index.html").write_text("<html>landing</html>")

        adapter = MockDeploymentAdapter()
        result = adapter.deploy(tmp_path)

        assert result.success is True


class TestCloudflarePagesAdapter:
    def test_missing_token(self, tmp_path):
        (tmp_path / "index.html").write_text("<html></html>")

        adapter = CloudflarePagesDeploymentAdapter()
        with patch.object(settings, "cloudflare_api_token", ""):
            result = adapter.deploy(tmp_path)
            assert result.success is False
            assert "CLOUDFLARE_API_TOKEN" in result.error

    def test_missing_account_id(self, tmp_path):
        (tmp_path / "index.html").write_text("<html></html>")

        adapter = CloudflarePagesDeploymentAdapter()
        with (
            patch.object(settings, "cloudflare_api_token", "test-token"),
            patch.object(settings, "cloudflare_account_id", ""),
        ):
            result = adapter.deploy(tmp_path)
            assert result.success is False
            assert "CLOUDFLARE_ACCOUNT_ID" in result.error

    def test_missing_directory(self, tmp_path):
        adapter = CloudflarePagesDeploymentAdapter()
        with (
            patch.object(settings, "cloudflare_api_token", "test-token"),
            patch.object(settings, "cloudflare_account_id", "test-id"),
        ):
            result = adapter.deploy(tmp_path / "nonexistent")
            assert result.success is False
            assert "does not exist" in result.error

    def test_empty_directory(self, tmp_path):
        adapter = CloudflarePagesDeploymentAdapter()
        with (
            patch.object(settings, "cloudflare_api_token", "test-token"),
            patch.object(settings, "cloudflare_account_id", "test-id"),
        ):
            result = adapter.deploy(tmp_path)
            assert result.success is False
            assert "No index.html" in result.error


class TestDeploymentResult:
    def test_success_result(self):
        result = DeploymentResult(
            success=True,
            url="https://test.pages.dev",
            deployment_id="dep-001",
            stdout="done",
        )
        assert result.success is True
        assert result.error == ""

    def test_failure_result(self):
        result = DeploymentResult(
            success=False,
            error="Something went wrong",
        )
        assert result.success is False
        assert result.error == "Something went wrong"
