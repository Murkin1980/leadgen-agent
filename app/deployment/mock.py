from __future__ import annotations

import logging
from pathlib import Path

from app.deployment.base import DeploymentResult

logger = logging.getLogger(__name__)


class MockDeploymentAdapter:
    def deploy(self, public_dir: Path) -> DeploymentResult:
        if not public_dir.exists():
            return DeploymentResult(
                success=False,
                error=f"Public directory does not exist: {public_dir}",
            )

        has_index = any(public_dir.rglob("index.html"))
        if not has_index:
            return DeploymentResult(
                success=False,
                error=f"No index.html found in {public_dir}",
            )

        logger.info("Mock deployment of %s succeeded", public_dir)

        return DeploymentResult(
            success=True,
            url="https://mock-deployment.pages.dev",
            deployment_id="mock-deployment-001",
            stdout="Mock deploy: success",
            stderr="",
        )
