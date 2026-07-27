from app.config import settings


class TestDeploymentProviderSelection:
    def test_mock_provider_setting(self):
        original = settings.deployment_provider
        try:
            settings.deployment_provider = "mock"
            from app.deployment.mock import MockDeploymentAdapter
            from app.workers.deployer_worker import _get_adapter

            adapter = _get_adapter()
            assert isinstance(adapter, MockDeploymentAdapter)
        finally:
            settings.deployment_provider = original

    def test_cloudflare_provider_setting(self):
        original = settings.deployment_provider
        try:
            settings.deployment_provider = "cloudflare"
            from app.deployment.cloudflare import CloudflarePagesDeploymentAdapter
            from app.workers.deployer_worker import _get_adapter

            adapter = _get_adapter()
            assert isinstance(adapter, CloudflarePagesDeploymentAdapter)
        finally:
            settings.deployment_provider = original
