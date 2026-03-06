"""Deployment pipeline report model."""

from typing import Any

from pydantic import BaseModel

from src.utils.scrubbing import scrub_credentials


class DeploymentReport(BaseModel):
    """Report from the deployment pipeline."""

    live_site_url: str
    strapi_admin_url: str
    droplet_ip: str
    deployment_timestamp: str
    build_duration_seconds: float
    files_deployed: int
    homepage_status: int
    sample_page_status: int
    webhook_registered: bool

    def to_safe_dict(self) -> dict[str, Any]:
        """Return a dict with any credentials scrubbed as a safety net."""
        return scrub_credentials(self.model_dump())
