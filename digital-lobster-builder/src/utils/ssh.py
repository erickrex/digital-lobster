from __future__ import annotations

import asyncio
import io
import socket
import tarfile
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from urllib.parse import urlparse

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

async def ssh_run(
    ssh_connection_string: str,
    ssh_private_key_path: str | None,
    command: str,
) -> tuple[str, str]:
    """Execute *command* on the remote host via SSH."""
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

async def scp_project_to_vps(
    ssh_connection_string: str,
    ssh_private_key_path: str | None,
    target_path: str,
    project_files: dict[str, str | bytes],
) -> int:
    """Transfer an in-memory project to *target_path* on a remote host."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for rel_path, content in project_files.items():
            data = (
                content.encode("utf-8")
                if isinstance(content, str)
                else content
            )
            info = tarfile.TarInfo(name=rel_path)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    archive_bytes = buf.getvalue()

    ssh_opts = _ssh_base_args(ssh_private_key_path)
    cmd = [
        "ssh", *ssh_opts, ssh_connection_string,
        f"mkdir -p {target_path} && tar xzf - -C {target_path}",
    ]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _stdout, stderr = await proc.communicate(input=archive_bytes)
    if proc.returncode != 0:
        raise RuntimeError(
            f"SCP to {target_path} failed: {stderr.decode('utf-8', errors='replace')}"
        )
    return len(project_files)

def _pick_local_port() -> int:
    """Return a currently unused localhost port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])

@dataclass
class SshTunnel:
    """Represents a running SSH local-port forward."""
    process: asyncio.subprocess.Process
    local_port: int

    @property
    def base_url(self) -> str:
        """Return the local HTTP base URL for the tunnel."""
        return f"http://127.0.0.1:{self.local_port}"

    async def close(self) -> None:
        """Terminate the underlying SSH tunnel process."""
        if self.process.returncode is None:
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), timeout=5)
            except asyncio.TimeoutError:
                self.process.kill()
                await self.process.wait()

async def open_tunnel(
    ssh_connection_string: str,
    ssh_private_key_path: str | None,
    *,
    remote_host: str = "127.0.0.1",
    remote_port: int = 1337,
    local_port: int | None = None,
    timeout: float = 10.0,
) -> SshTunnel:
    """Open an SSH tunnel that forwards a local port to a remote service."""
    local_port = local_port or _pick_local_port()
    ssh_opts = _ssh_base_args(ssh_private_key_path)
    cmd = [
        "ssh",
        *ssh_opts,
        "-o", "ExitOnForwardFailure=yes",
        "-N",
        "-L", f"{local_port}:{remote_host}:{remote_port}",
        ssh_connection_string,
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc.returncode is not None:
            _stdout, stderr = await proc.communicate()
            raise RuntimeError(
                "SSH tunnel exited early: "
                f"{stderr.decode('utf-8', errors='replace')}"
            )
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", local_port)
            writer.close()
            await writer.wait_closed()
            return SshTunnel(process=proc, local_port=local_port)
        except OSError:
            await asyncio.sleep(0.1)

    await SshTunnel(process=proc, local_port=local_port).close()
    raise RuntimeError(
        f"Timed out opening SSH tunnel to {remote_host}:{remote_port}"
    )

@asynccontextmanager
async def strapi_base_url_context(
    base_url: str,
    ssh_connection_string: str | None,
    ssh_private_key_path: str | None,
):
    """Yield a base URL that reaches Strapi through SSH when available."""
    parsed = urlparse(base_url)

    if (
        ssh_connection_string
        and parsed.scheme == "http"
        and parsed.hostname is not None
    ):
        remote_port = parsed.port or 80
        tunnel = await open_tunnel(
            ssh_connection_string,
            ssh_private_key_path,
            remote_host="127.0.0.1",
            remote_port=remote_port,
        )
        try:
            yield tunnel.base_url
        finally:
            await tunnel.close()
        return

    yield base_url
