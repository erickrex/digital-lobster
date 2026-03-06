"""Strapi Provisioner agent — provisions a DigitalOcean Droplet via Terraform,
verifies Strapi health, creates the initial admin user, and generates an API token.

Requirements: 1.8, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import shutil
import time
from pathlib import Path
from typing import Any

import httpx

from src.agents.base import AgentResult, BaseAgent
from src.models.cms_config import CMSConfig

logger = logging.getLogger(__name__)

# Directory containing the Terraform module (relative to project root).
TERRAFORM_DIR = Path(__file__).resolve().parent.parent.parent / "terraform"

# Health-check polling defaults.
DEFAULT_HEALTH_TIMEOUT = 600  # seconds
HEALTH_POLL_INTERVAL = 10  # seconds


class StrapiProvisionerAgent(BaseAgent):
    """Provisions a DigitalOcean Droplet running Strapi via Terraform,
    polls the health endpoint, creates an admin user, and generates an
    API token."""

    def __init__(
        self,
        gradient_client: Any,
        kb_client: Any = None,
        terraform_dir: Path | str | None = None,
        health_timeout: int = DEFAULT_HEALTH_TIMEOUT,
    ) -> None:
        super().__init__(gradient_client, kb_client)
        self.terraform_dir = Path(terraform_dir) if terraform_dir else TERRAFORM_DIR
        self.health_timeout = health_timeout

    async def execute(self, context: dict[str, Any]) -> AgentResult:
        """Run the full provisioning workflow.

        1. Write Terraform variable values to ``terraform.tfvars.json``
        2. Run ``terraform init`` + ``terraform apply -auto-approve``
        3. Parse outputs (droplet_ip, domain, strapi_admin_url, ssh_string)
        4. Poll ``GET http://{droplet_ip}:1337/_health`` until 200
        5. ``POST /admin/register-admin`` to create initial admin user
        6. Generate API token via admin API
        7. Store Terraform state file to configured location
        8. Return artifacts
        """
        start = time.monotonic()
        warnings: list[str] = []

        cms_config: CMSConfig = context["cms_config"]

        # 1. Write tfvars
        write_tfvars(self.terraform_dir, cms_config)

        # 2. Terraform init + apply
        tf_outputs = await run_terraform(self.terraform_dir)

        # 3. Parse outputs
        droplet_ip: str = tf_outputs["droplet_ip"]["value"]
        domain_name: str = tf_outputs["domain_name"]["value"]
        strapi_admin_url: str = tf_outputs["strapi_admin_url"]["value"]
        ssh_connection_string: str = tf_outputs["ssh_connection_string"]["value"]

        # 4. Health check
        await poll_health(droplet_ip, self.health_timeout)

        # 5. Create admin user
        admin_jwt = await create_admin_user(
            droplet_ip,
            cms_config.strapi_admin_email,
            cms_config.strapi_admin_password.get_secret_value(),
        )

        # 6. Generate API token
        api_token = await generate_api_token(droplet_ip, admin_jwt)

        # 7. Store Terraform state
        store_terraform_state(self.terraform_dir, cms_config.terraform_state_path)

        strapi_base_url = f"http://{droplet_ip}:1337"

        duration = time.monotonic() - start
        return AgentResult(
            agent_name="strapi_provisioner",
            artifacts={
                "strapi_base_url": strapi_base_url,
                "strapi_api_token": api_token,
                "droplet_ip": droplet_ip,
                "ssh_connection_string": ssh_connection_string,
                "admin_credentials": {
                    "email": cms_config.strapi_admin_email,
                    "password": cms_config.strapi_admin_password.get_secret_value(),
                },
                "domain_name": domain_name,
            },
            warnings=warnings,
            duration_seconds=duration,
        )


# ======================================================================
# Pure / helper functions — testable in isolation
# ======================================================================


def write_tfvars(terraform_dir: Path, config: CMSConfig) -> Path:
    """Write a ``terraform.tfvars.json`` file from *config*.

    Returns the path to the written file.
    """
    tfvars = {
        "do_token": config.do_token.get_secret_value(),
        "domain_name": config.domain_name,
        "droplet_region": config.droplet_region,
        "droplet_size": config.droplet_size,
        "ssh_public_key": config.ssh_public_key,
        "strapi_admin_email": config.strapi_admin_email,
        "strapi_admin_password": config.strapi_admin_password.get_secret_value(),
    }
    tfvars_path = terraform_dir / "terraform.tfvars.json"
    tfvars_path.write_text(json.dumps(tfvars, indent=2))
    return tfvars_path


async def run_terraform(terraform_dir: Path) -> dict[str, Any]:
    """Run ``terraform init`` and ``terraform apply -auto-approve``.

    Returns the parsed JSON output from ``terraform output -json``.

    Raises:
        RuntimeError: If either Terraform command fails, with stderr and
            the failed resource name (if detectable).
    """
    # terraform init
    init_proc = await asyncio.create_subprocess_exec(
        "terraform", "init", "-input=false",
        cwd=str(terraform_dir),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    init_stdout, init_stderr = await init_proc.communicate()
    if init_proc.returncode != 0:
        stderr_text = init_stderr.decode("utf-8", errors="replace")
        resource = _extract_failed_resource(stderr_text)
        raise RuntimeError(
            f"terraform init failed (resource: {resource}): {stderr_text}"
        )

    # terraform apply
    apply_proc = await asyncio.create_subprocess_exec(
        "terraform", "apply", "-auto-approve", "-input=false",
        cwd=str(terraform_dir),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    apply_stdout, apply_stderr = await apply_proc.communicate()
    if apply_proc.returncode != 0:
        stderr_text = apply_stderr.decode("utf-8", errors="replace")
        resource = _extract_failed_resource(stderr_text)
        raise RuntimeError(
            f"terraform apply failed (resource: {resource}): {stderr_text}"
        )

    # terraform output -json
    output_proc = await asyncio.create_subprocess_exec(
        "terraform", "output", "-json",
        cwd=str(terraform_dir),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    output_stdout, output_stderr = await output_proc.communicate()
    if output_proc.returncode != 0:
        stderr_text = output_stderr.decode("utf-8", errors="replace")
        raise RuntimeError(f"terraform output failed: {stderr_text}")

    return json.loads(output_stdout.decode("utf-8"))


def _extract_failed_resource(stderr: str) -> str:
    """Best-effort extraction of the failed Terraform resource name from stderr.

    Looks for patterns like ``Error: ... digitalocean_droplet.strapi ...``
    or ``resource "digitalocean_droplet" "strapi"``.
    """
    # Pattern: resource "type" "name"
    match = re.search(r'resource\s+"([^"]+)"\s+"([^"]+)"', stderr)
    if match:
        return f"{match.group(1)}.{match.group(2)}"

    # Pattern: type.name in error lines
    match = re.search(r'(digitalocean_\w+\.\w+)', stderr)
    if match:
        return match.group(1)

    return "unknown"


async def poll_health(
    droplet_ip: str,
    timeout: int = DEFAULT_HEALTH_TIMEOUT,
    poll_interval: int = HEALTH_POLL_INTERVAL,
) -> None:
    """Poll ``GET http://{droplet_ip}:1337/_health`` until a 200 response.

    Raises:
        RuntimeError: If the health check does not succeed within *timeout*
            seconds, with the droplet IP and log file reference.
    """
    url = f"http://{droplet_ip}:1337/_health"
    deadline = time.monotonic() + timeout

    async with httpx.AsyncClient(timeout=10) as client:
        while time.monotonic() < deadline:
            try:
                resp = await client.get(url)
                if resp.status_code == 200:
                    logger.info("Strapi health check passed at %s", url)
                    return
            except httpx.HTTPError:
                pass  # connection refused, timeout, etc. — keep polling

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            await asyncio.sleep(min(poll_interval, remaining))

    raise RuntimeError(
        f"Strapi health check timed out after {timeout}s. "
        f"Droplet IP: {droplet_ip}. "
        f"Check /var/log/cloud-init-output.log on the droplet for details."
    )


async def create_admin_user(
    droplet_ip: str,
    email: str,
    password: str,
) -> str:
    """Create the initial Strapi admin user via ``POST /admin/register-admin``.

    Returns the admin JWT token for subsequent API calls.

    Raises:
        RuntimeError: If the admin registration request fails.
    """
    url = f"http://{droplet_ip}:1337/admin/register-admin"
    payload = {
        "firstname": "Admin",
        "lastname": "User",
        "email": email,
        "password": password,
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(url, json=payload)

    if resp.status_code not in (200, 201):
        raise RuntimeError(
            f"Failed to create Strapi admin user (HTTP {resp.status_code}): "
            f"{resp.text}"
        )

    data = resp.json()
    token = data.get("data", {}).get("token") or data.get("token")
    if not token:
        raise RuntimeError(
            f"Admin registration succeeded but no token in response: {data}"
        )
    return token


async def generate_api_token(droplet_ip: str, admin_jwt: str) -> str:
    """Generate a full-access API token via the Strapi admin API.

    Returns the plain-text access token string.

    Raises:
        RuntimeError: If token generation fails.
    """
    url = f"http://{droplet_ip}:1337/admin/api-tokens"
    payload = {
        "name": "digital-lobster-pipeline",
        "description": "Auto-generated token for the Digital Lobster migration pipeline",
        "type": "full-access",
    }
    headers = {"Authorization": f"Bearer {admin_jwt}"}

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(url, json=payload, headers=headers)

    if resp.status_code not in (200, 201):
        raise RuntimeError(
            f"Failed to generate Strapi API token (HTTP {resp.status_code}): "
            f"{resp.text}"
        )

    data = resp.json()
    access_key = data.get("data", {}).get("accessKey") or data.get("accessKey")
    if not access_key:
        raise RuntimeError(
            f"API token creation succeeded but no accessKey in response: {data}"
        )
    return access_key


def store_terraform_state(terraform_dir: Path, destination: str) -> Path:
    """Copy the Terraform state file to the configured destination.

    Returns the destination path.
    """
    state_src = terraform_dir / "terraform.tfstate"
    dest_path = Path(destination)
    if dest_path.is_dir():
        dest_path = dest_path / "terraform.tfstate"
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(state_src), str(dest_path))
    logger.info("Terraform state stored at %s", dest_path)
    return dest_path
