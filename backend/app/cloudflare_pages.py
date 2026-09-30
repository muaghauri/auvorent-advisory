from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path


class CloudflarePagesError(RuntimeError):
    """Raised when a Cloudflare Pages deployment cannot be completed."""


def deployment_status() -> dict:
    """Return non-secret configuration/runtime status."""
    return {
        "configured": all(
            [
                os.getenv("CLOUDFLARE_ACCOUNT_ID", "").strip(),
                os.getenv("CLOUDFLARE_PAGES_PROJECT", "").strip(),
                os.getenv("CLOUDFLARE_API_TOKEN", "").strip(),
            ]
        ),
        "project": os.getenv("CLOUDFLARE_PAGES_PROJECT", "").strip() or None,
        "wrangler_available": shutil.which("wrangler") is not None,
    }


def deploy_pages(
    directory: str | Path,
    *,
    branch: str = "main",
    commit_message: str = "CMS production deployment",
    timeout: int = 300,
) -> dict:
    directory = Path(directory).resolve()

    if not directory.is_dir():
        raise CloudflarePagesError(
            f"Deployment directory does not exist: {directory}"
        )

    account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID", "").strip()
    project = os.getenv("CLOUDFLARE_PAGES_PROJECT", "").strip()
    token = os.getenv("CLOUDFLARE_API_TOKEN", "").strip()

    missing = []
    if not account_id:
        missing.append("CLOUDFLARE_ACCOUNT_ID")
    if not project:
        missing.append("CLOUDFLARE_PAGES_PROJECT")
    if not token:
        missing.append("CLOUDFLARE_API_TOKEN")

    if missing:
        raise CloudflarePagesError(
            "Missing Cloudflare configuration: " + ", ".join(missing)
        )

    wrangler = shutil.which("wrangler")
    if not wrangler:
        raise CloudflarePagesError(
            "Wrangler executable is not available in the runtime."
        )

    env = os.environ.copy()
    env["CLOUDFLARE_ACCOUNT_ID"] = account_id
    env["CLOUDFLARE_API_TOKEN"] = token
    env["CI"] = "true"

    command = [
        wrangler,
        "pages",
        "deploy",
        str(directory),
        "--project-name",
        project,
        "--branch",
        branch,
        "--commit-message",
        commit_message,
    ]

    try:
        result = subprocess.run(
            command,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise CloudflarePagesError(
            f"Cloudflare Pages deployment timed out after {timeout} seconds."
        ) from exc

    output = "\n".join(
        part for part in [result.stdout, result.stderr] if part
    )

    # Defensive redaction in case a CLI error ever echoes the credential.
    if token:
        output = output.replace(token, "[REDACTED]")

    if result.returncode != 0:
        raise CloudflarePagesError(
            "Cloudflare Pages deployment failed:\n" + output[-3000:]
        )

    match = re.search(
        r"https://[^\s]+\.pages\.dev",
        output,
    )

    return {
        "provider": "cloudflare_pages",
        "project": project,
        "branch": branch,
        "deployment_url": match.group(0) if match else None,
        "success": True,
    }
