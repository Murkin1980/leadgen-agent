from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class DeploymentResult:
    success: bool
    url: str = ""
    deployment_id: str = ""
    stdout: str = ""
    stderr: str = ""
    error: str = ""
