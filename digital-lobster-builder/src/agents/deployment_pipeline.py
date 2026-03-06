"""Deployment Pipeline agent.

Builds the Astro static site on the VPS, deploys it behind Nginx,
verifies the live site, and registers a Strapi webhook for automatic
rebuilds on content changes.
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import tarfile
import time
from datetime import datetime, timezone
from typing import Any

import httpx

from src.agents.base import AgentResult, BaseAgent
from src.models.deployment_report import DeploymentReport

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
ASTRO_SRC_PATH = "/var/www/astro-src"
ASTRO_DIST_PATH = "/var/www/astro"
STRAPI_BUILD_URL = "http://localhost:1337"
REBUILD_ENDPOINT = "http://localhost:4000/rebuild"
WEBHOOK_EVENTS = ["entry.create", "entry.update", "entry.delete"]


# ---------------------------------------------------------------------------
# SSH / SCP helpers
# ---------------------------------------------------------------------------

def _ssh_base_args(ssh_private_key_path: str | None) -> list[str]:
    """Return common SSH option flags."""
    args = [
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        "-o", "ConnectTimeout=30",
    ]
    if ssh_private_key_path:
        args.extend(["-i", ssh_private_key_path])
    return args


async def scp_project_to_vps(
    ssh_connection_string: str,
    ssh_private_key_path: str | None,
    astro_project: dict[str, str],
) -> int:
    """SCP the Astro project files to the VPS at ``/var/www/astro-src``.

    Creates a tar archive in memory from *astro_project* (a mapping of
    relative file paths to file contents), pipes it to the remote host
    via ``ssh … tar xf -``, and returns the number of files transferred.

    Raises:
        RuntimeError: If the SCP/SSH transfer fails.
    """
    # Build an in-memory tar archive of the project files
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for rel_path, content in astro_project.items():
            data = content.encode("utf-8") if isinstance(content, str) else content
            info = tarfile.TarInfo(name=rel_path)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    archive_bytes = buf.getvalue()

    ssh_opts = _ssh_base_args(ssh_private_key_path)

    # Ensure target directory exists, then extract archive
    cmd = [
        "ssh", *ssh_opts, ssh_connection_string,
        f"mkdir -p {ASTRO_SRC_PATH} && tar xzf - -C {ASTRO_SRC_PATH}",
    ]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate(input=archive_bytes)

    if proc.returncode != 0:
        stderr_text = stderr.decode("utf-8", errors="replace")
        raise RuntimeError(
            f"SCP to {ASTRO_SRC_PATH} failed: {stderr_text}"
        )

    return len(astro_project)


async def ssh_run(
    ssh_connection_string: str,
    ssh_private_key_path: str | None,
    command: str,
) -> tuple[str, str]:
    """Execute *command* on the remote host via SSH.

    Returns:
        Tuple of (stdout, stderr) decoded as UTF-8.

    Raises:
        RuntimeError: If the remote command exits with a non-zero status.
    """
    ssh_opts = _ssh_base_args(ssh_private_key_path)
    cmd = ["ssh", *ssh_opts, ssh_connection_string, command]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout_bytes, stderr_bytes = await proc.communicate()
    stdout_text = stdout_bytes.decode("utf-8", errors="replace")
    stderr_text = stderr_bytes.decode("utf-8", errors="replace")

    if proc.returncode != 0:
        raise RuntimeError(
            f"SSH command failed (rc={proc.returncode}): {stderr_text}"
        )

    return stdout_text, stderr_text


# ---------------------------------------------------------------------------
# Build & deploy helpers
# ---------------------------------------------------------------------------

async def build_astro_on_vps(
    ssh_connection_string: str,
    ssh_private_key_path: str | None,
) -> tuple[float, str]:
    """Run ``npm install && npm run build`` on the VPS.

    Returns:
        Tuple of (build_duration_seconds, build_stdout).

    Raises:
        RuntimeError: On build failure — includes build output and a note
            about Strapi API status.
    """
    build_cmd = (
        f"cd {ASTRO_SRC_PATH} && "
        f"STRAPI_URL={STRAPI_BUILD_URL} npm install && "
        f"STRAPI_URL={STRAPI_BUILD_URL} npm run build"
    )

    start = time.monotonic()
    try:
        stdout, _stderr = await ssh_run(
            ssh_connection_string, ssh_private_key_path, build_cmd
        )
    except RuntimeError as exc:
        # Check Strapi API status to give a more helpful error
        strapi_status = await _check_strapi_status(
            ssh_connection_string, ssh_private_key_path
        )
        raise RuntimeError(
            f"Astro build failed. Build output: {exc}. "
            f"Strapi API status: {strapi_status}"
        ) from exc

    duration = time.monotonic() - start
    return duration, stdout


async def deploy_built_files(
    ssh_connection_string: str,
    ssh_private_key_path: str | None,
) -> int:
    """Copy built files to ``/var/www/astro`` and set ownership.

    Returns:
        Number of files deployed.

    Raises:
        RuntimeError: If the copy or ownership change fails.
    """
    deploy_cmd = (
        f"cp -r {ASTRO_SRC_PATH}/dist/* {ASTRO_DIST_PATH}/ && "
        f"chown -R www-data:www-data {ASTRO_DIST_PATH}"
    )
    await ssh_run(ssh_connection_string, ssh_private_key_path, deploy_cmd)

    # Count deployed files
    count_cmd = f"find {ASTRO_DIST_PATH} -type f | wc -l"
    stdout, _ = await ssh_run(
        ssh_connection_string, ssh_private_key_path, count_cmd
    )
    try:
        return int(stdout.strip())
    except ValueError:
        return 0


async def reload_nginx(
    ssh_connection_string: str,
    ssh_private_key_path: str | None,
) -> None:
    """Test and reload the Nginx configuration.

    Raises:
        RuntimeError: If ``nginx -t`` or ``systemctl reload nginx`` fails.
    """
    await ssh_run(
        ssh_connection_string,
        ssh_private_key_path,
        "nginx -t && systemctl reload nginx",
    )


async def _check_strapi_status(
    ssh_connection_string: str,
    ssh_private_key_path: str | None,
) -> str:
    """Check Strapi health from the VPS itself (localhost)."""
    try:
        stdout, _ = await ssh_run(
            ssh_connection_string,
            ssh_private_key_path,
            f"curl -s -o /dev/null -w '%{{http_code}}' {STRAPI_BUILD_URL}/_health",
        )
        return f"HTTP {stdout.strip()}"
    except RuntimeError:
        return "unreachable"


# ---------------------------------------------------------------------------
# Site verification (sub-task 8.2)
# ---------------------------------------------------------------------------

async def verify_site(
    domain_name: str,
    sample_page: str | None = None,
    timeout: float = 30.0,
) -> tuple[int, int]:
    """Verify the live site returns 200 for the homepage and a sample page.

    Returns:
        Tuple of (homepage_status, sample_page_status).
    """
    async with httpx.AsyncClient(
        timeout=timeout, follow_redirects=True
    ) as client:
        homepage_url = f"https://{domain_name}/"
        try:
            resp = await client.get(homepage_url)
            homepage_status = resp.status_code
        except httpx.HTTPError:
            homepage_status = 0

        sample_page_status = 0
        if sample_page:
            sample_url = f"https://{domain_name}/{sample_page.lstrip('/')}"
            try:
                resp = await client.get(sample_url)
                sample_page_status = resp.status_code
            except httpx.HTTPError:
                sample_page_status = 0

    return homepage_status, sample_page_status


# ---------------------------------------------------------------------------
# Webhook registration (sub-task 8.2)
# ---------------------------------------------------------------------------

async def register_strapi_webhook(
    strapi_base_url: str,
    api_token: str,
) -> bool:
    """Register a Strapi webhook for content change events.

    The webhook fires on ``entry.create``, ``entry.update``, and
    ``entry.delete`` and POSTs to the local rebuild service at
    ``http://localhost:4000/rebuild``.

    Returns:
        ``True`` if the webhook was registered successfully.
    """
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "name": "Astro Rebuild",
        "url": REBUILD_ENDPOINT,
        "events": WEBHOOK_EVENTS,
        "enabled": True,
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.post(
                f"{strapi_base_url}/api/webhook-store",
                headers=headers,
                json=payload,
            )
            if resp.status_code in (200, 201):
                logger.info("Strapi webhook registered successfully")
                return True
            logger.warning(
                "Webhook registration returned status %d: %s",
                resp.status_code,
                resp.text,
            )
            return False
        except httpx.HTTPError as exc:
            logger.warning("Webhook registration failed: %s", exc)
            return False


# ---------------------------------------------------------------------------
# Agent class
# ---------------------------------------------------------------------------

class DeploymentPipelineAgent(BaseAgent):
    """Builds Astro on the VPS and deploys behind Nginx.

    Reads ``droplet_ip``, ``ssh_connection_string``, ``domain_name``,
    ``strapi_base_url``, ``strapi_api_token``, and ``astro_project``
    from the pipeline context.  Writes ``deployment_report`` back into
    the context.
    """

    async def execute(self, context: dict[str, Any]) -> AgentResult:
        """Execute the full deployment workflow.

        1. SCP the Astro project to VPS at /var/www/astro-src
        2. SSH: npm install && npm run build (STRAPI_URL=http://localhost:1337)
        3. SSH: copy built files to /var/www/astro, set www-data ownership
        4. SSH: nginx -t && systemctl reload nginx
        5. Verify: GET https://{domain}/ → 200
        6. Verify: GET https://{domain}/{sample_page} → 200
        7. Register Strapi webhook for entry.create, entry.update, entry.delete
           → POST http://localhost:4000/rebuild
        8. Return deployment_report artifact
        """
        start = time.monotonic()
        warnings: list[str] = []

        droplet_ip: str = context["droplet_ip"]
        ssh_connection_string: str = context["ssh_connection_string"]
        domain_name: str = context["domain_name"]
        strapi_base_url: str = context["strapi_base_url"]
        strapi_api_token: str = context["strapi_api_token"]
        astro_project: dict[str, str] = context["astro_project"]

        # Resolve SSH private key path from cms_config if available
        cms_config = context.get("cms_config")
        ssh_private_key_path: str | None = None
        if cms_config is not None:
            ssh_private_key_path = getattr(
                cms_config, "ssh_private_key_path", None
            )

        # Determine a sample page for verification
        sample_page: str | None = context.get("sample_page")
        if not sample_page:
            # Pick the first non-config file that looks like a page route
            for fpath in astro_project:
                if fpath.startswith("src/pages/") and fpath.endswith(".astro"):
                    slug = (
                        fpath.removeprefix("src/pages/")
                        .removesuffix(".astro")
                        .removesuffix("/index")
                    )
                    if slug and slug != "index":
                        sample_page = slug
                        break

        # ------------------------------------------------------------------
        # Step 1: SCP project to VPS
        # ------------------------------------------------------------------
        try:
            files_transferred = await scp_project_to_vps(
                ssh_connection_string, ssh_private_key_path, astro_project
            )
        except RuntimeError as exc:
            raise RuntimeError(
                f"SCP/SSH failure — target: {ASTRO_SRC_PATH}, "
                f"error: {exc}"
            ) from exc

        # ------------------------------------------------------------------
        # Step 2: Build Astro on VPS
        # ------------------------------------------------------------------
        try:
            build_duration, _build_output = await build_astro_on_vps(
                ssh_connection_string, ssh_private_key_path
            )
        except RuntimeError as exc:
            raise RuntimeError(
                f"Build failure — {exc}"
            ) from exc

        # ------------------------------------------------------------------
        # Step 3: Deploy built files
        # ------------------------------------------------------------------
        try:
            files_deployed = await deploy_built_files(
                ssh_connection_string, ssh_private_key_path
            )
        except RuntimeError as exc:
            raise RuntimeError(
                f"SCP/SSH failure — target: {ASTRO_DIST_PATH}, "
                f"error: {exc}"
            ) from exc

        # ------------------------------------------------------------------
        # Step 4: Reload Nginx
        # ------------------------------------------------------------------
        try:
            await reload_nginx(ssh_connection_string, ssh_private_key_path)
        except RuntimeError as exc:
            raise RuntimeError(
                f"Nginx reload failed: {exc}"
            ) from exc

        # ------------------------------------------------------------------
        # Step 5 & 6: Verify live site
        # ------------------------------------------------------------------
        homepage_status, sample_page_status = await verify_site(
            domain_name, sample_page
        )
        if homepage_status != 200:
            warnings.append(
                f"Homepage returned status {homepage_status} "
                f"(expected 200)"
            )
        if sample_page and sample_page_status != 200:
            warnings.append(
                f"Sample page '{sample_page}' returned status "
                f"{sample_page_status} (expected 200)"
            )

        # ------------------------------------------------------------------
        # Step 7: Register Strapi webhook
        # ------------------------------------------------------------------
        webhook_registered = await register_strapi_webhook(
            strapi_base_url, strapi_api_token
        )
        if not webhook_registered:
            warnings.append("Strapi webhook registration failed")

        # ------------------------------------------------------------------
        # Step 8: Build deployment report
        # ------------------------------------------------------------------
        deployment_report = DeploymentReport(
            live_site_url=f"https://{domain_name}",
            strapi_admin_url=f"https://{domain_name}/admin",
            droplet_ip=droplet_ip,
            deployment_timestamp=datetime.now(timezone.utc).isoformat(),
            build_duration_seconds=round(build_duration, 2),
            files_deployed=files_deployed,
            homepage_status=homepage_status,
            sample_page_status=sample_page_status,
            webhook_registered=webhook_registered,
        )

        duration = time.monotonic() - start
        return AgentResult(
            agent_name="deployment_pipeline",
            artifacts={
                "deployment_report": deployment_report,
            },
            warnings=warnings,
            duration_seconds=duration,
        )
