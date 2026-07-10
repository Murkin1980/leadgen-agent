from __future__ import annotations

from typing import Protocol

from app.deployment.base import DeploymentResult


class DeploymentAdapter(Protocol):
    def deploy(self, public_dir: Path) -> DeploymentResult: ...
