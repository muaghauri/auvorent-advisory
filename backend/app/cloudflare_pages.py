from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path


class CloudflarePagesError(RuntimeError):
    """Raised when a Cloudflare Pages deployment cannot be completed."""


_PROJECT_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
_BRANCH_RE = re.compile(r"^[A-Za-z0-9._/-]{1,120}$")


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


def _validate_deploy_inputs(project: str, branch: str, commit_message: str, timeout: int) -> None:
    if not _PROJECT_RE.fullmatch(project):
        raise CloudflarePagesError("Invalid Cloudflare Pages project configuration.")
    if not _BRANCH_RE.fullmatch(branch) or ".." in branch or branch.startswith(("/", "-")):
        raise CloudflarePagesError("Invalid deployment branch.")
    if not commit_message or len(commit_message) > 240 or any(c in commit_message for c in "\r\n\x00"):
        raise CloudflarePagesError("Invalid deployment commit message.")
    if timeout < 30 or timeout > 600:
        raise CloudflarePagesError("Deployment timeout must be between 30 and 600 seconds.")


def _redact(text: str, *secrets_to_hide: str) -> str:
    clean = text or ""
    for secret in secrets_to_hide:
        if secret:
            clean = clean.replace(secret, "[REDACTED]")
    # Defensive fallback for common credential-looking fragments in provider errors.
    clean = re.sub(r"(?i)(authorization:\s*bearer\s+)[^\s]+", r"\1[REDACTED]", clean)
    clean = re.sub(r"(?i)(api[_-]?token[=:]\s*)[^\s]+", r"\1[REDACTED]", clean)
    return clean


def deploy_pages(
    directory: str | Path,
    *,
    branch: str = "main",
    commit_message: str = "CMS production deployment",
    timeout: int = 300,
) -> dict:
    directory = Path(directory).resolve()

    if not directory.is_dir():
        # Avoid returning internal filesystem paths to API callers/log records.
        raise CloudflarePagesError("Deployment directory is unavailable.")

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
        raise CloudflarePagesError("Cloudflare deployment configuration is incomplete.")

    _validate_deploy_inputs(project, branch, commit_message, timeout)

    wrangler = shutil.which("wrangler")
    if not wrangler:
        raise CloudflarePagesError("Cloudflare deployment runtime is unavailable.")

    env = os.environ.copy()
    env["CLOUDFLARE_ACCOUNT_ID"] = account_id
    env["CLOUDFLARE_API_TOKEN"] = token
    env["CI"] = "true"
    # Keep subprocess behavior deterministic and avoid interactive prompts.
    env["NO_COLOR"] = "1"

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
        raise CloudflarePagesError("Cloudflare Pages deployment timed out.") from exc
    except OSError as exc:
        raise CloudflarePagesError("Cloudflare deployment process could not start.") from exc

    output = _redact("\n".join(part for part in [result.stdout, result.stderr] if part), token, account_id)

    if result.returncode != 0:
        # Keep provider diagnostics bounded and scrubbed; no environment dump/path disclosure.
        raise CloudflarePagesError("Cloudflare Pages deployment failed. Provider output: " + output[-1500:])

    match = re.search(r"https://[A-Za-z0-9.-]+\.pages\.dev(?:/[^\s]*)?", output)

    return {
        "provider": "cloudflare_pages",
        "project": project,
        "branch": branch,
        "deployment_url": match.group(0) if match else None,
        "success": True,
    }
