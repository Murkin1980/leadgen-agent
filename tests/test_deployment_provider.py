import pytest
from app.config import settings


class TestDeploymentProviderSelection:
    def test_mock_provider_setting(self):
        original = settings.deployment_provider
        try:
            settings.deployment_provider = "mock"
            from app.workers.deployer_worker import _get_adapter
            from app.deployment.mock import MockDeploymentAdapter
            adapter = _get_adapter()
            assert isinstance(adapter, MockDeploymentAdapter)
        finally:
            settings.deployment_provider = original

    def test_cloudflare_provider_setting(self):
        original = settings.deployment_provider
        try:
            settings.deployment_provider = "cloudflare"
            from app.workers.deployer_worker import _get_adapter
            from app.deployment.cloudflare import CloudflarePagesDeploymentAdapter
            adapter = _get_adapter()
            assert isinstance(adapter, CloudflarePagesDeploymentAdapter)
        finally:
            settings.deployment_provider = original
