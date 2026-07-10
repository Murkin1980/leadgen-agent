from __future__ import annotations

import logging
import re
import shutil
import subprocess
import time
from pathlib import Path

from app.config import settings
from app.deployment.base import DeploymentResult

logger = logging.getLogger(__name__)

MAX_LOG_CHARS = 2000
DEPLOY_TIMEOUT = 300


class CloudflarePagesDeploymentAdapter:
    def deploy(self, public_dir: Path) -> DeploymentResult:
        token = settings.cloudflare_api_token
        account_id = settings.cloudflare_account_id
        project = settings.cloudflare_pages_project
        branch = settings.cloudflare_pages_branch

        missing = []
        if not token:
            missing.append("CLOUDFLARE_API_TOKEN")
        if not account_id:
            missing.append("CLOUDFLARE_ACCOUNT_ID")
        if missing:
            return DeploymentResult(
                success=False,
                error=f"Missing configuration: {', '.join(missing)}",
            )

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

        wrangler = self._find_wrangler()
        if not wrangler:
            return DeploymentResult(
                success=False,
                error="Wrangler not found. Run 'npm ci' or install wrangler globally.",
            )

        cmd = [
            wrangler, "pages", "deploy", str(public_dir),
            "--project-name", project,
            "--branch", branch,
            "--commit-dirty=true",
        ]

        env = {
            "CLOUDFLARE_API_TOKEN": token,
            "CLOUDFLARE_ACCOUNT_ID": account_id,
        }

        logger.info("Deploying to Cloudflare Pages: project=%s branch=%s", project, branch)

        try:
            start = time.monotonic()
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=DEPLOY_TIMEOUT,
                env={**dict(__import__("os").environ), **env},
                shell=False,
            )
            elapsed = time.monotonic() - start
        except subprocess.TimeoutExpired:
            return DeploymentResult(
                success=False,
                error=f"Deployment timed out after {DEPLOY_TIMEOUT}s",
            )
        except FileNotFoundError:
            return DeploymentResult(
                success=False,
                error=f"Wrangler binary not found at: {wrangler}",
            )

        stdout_excerpt = (result.stdout or "")[:MAX_LOG_CHARS]
        stderr_excerpt = (result.stderr or "")[:MAX_LOG_CHARS]

        if result.returncode != 0:
            return DeploymentResult(
                success=False,
                stdout=stdout_excerpt,
                stderr=stderr_excerpt,
                error=f"Wrangler exited with code {result.returncode}",
            )

        url = self._parse_url(stdout_excerpt) or settings.cloudflare_public_url

        return DeploymentResult(
            success=True,
            url=url,
            stdout=stdout_excerpt,
            stderr=stderr_excerpt,
        )

    def _find_wrangler(self) -> str | None:
        local = Path("node_modules/.bin/wrangler")
        if local.exists():
            return str(local.resolve())

        from_path = shutil.which("wrangler")
        if from_path:
            return from_path

        npx = shutil.which("npx")
        if npx:
            return npx

        return None

    def _parse_url(self, output: str) -> str | None:
        match = re.search(r"https://[a-z0-9\-]+\.pages\.dev", output)
        return match.group(0) if match else None
