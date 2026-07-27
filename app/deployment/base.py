from dataclasses import dataclass


@dataclass
class DeploymentResult:
    success: bool
    url: str = ""
    deployment_id: str = ""
    stdout: str = ""
    stderr: str = ""
    error: str = ""
