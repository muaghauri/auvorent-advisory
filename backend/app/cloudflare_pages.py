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
_ACCOUNT_RE = re.compile(r"^[a-fA-F0-9]{32}$")
_ENV_PASSTHROUGH = {
    "HOME",
    "LANG",
    "LC_ALL",
    "NODE_PATH",
    "PATH",
    "SSL_CERT_DIR",
    "SSL_CERT_FILE",
    "TEMP",
    "TMP",
    "TMPDIR",
    "USER",
}


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


def _deployment_env(account_id: str, token: str) -> dict[str, str]:
    """Give Wrangler only the runtime values it actually needs.

    The Railway process also holds database, R2, mail and session secrets. Those
    values must not be inherited by the Node/Wrangler child process simply
    because it is launched from the CMS runtime.
    """
    env = {
        key: value
        for key, value in os.environ.items()
        if key in _ENV_PASSTHROUGH and value
    }
    env.update(
        {
            "CLOUDFLARE_ACCOUNT_ID": account_id,
            "CLOUDFLARE_API_TOKEN": token,
            "CI": "true",
            "NO_COLOR": "1",
        }
    )
    return env


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

    if not account_id or not project or not token:
        raise CloudflarePagesError("Cloudflare deployment configuration is incomplete.")
    if not _ACCOUNT_RE.fullmatch(account_id):
        raise CloudflarePagesError("Invalid Cloudflare account configuration.")
    if len(token) < 20 or len(token) > 512 or any(ord(ch) < 33 for ch in token):
        raise CloudflarePagesError("Invalid Cloudflare API token configuration.")

    _validate_deploy_inputs(project, branch, commit_message, timeout)

    wrangler = shutil.which("wrangler")
    if not wrangler:
        raise CloudflarePagesError("Cloudflare deployment runtime is unavailable.")
    wrangler_path = Path(wrangler).resolve()
    if not wrangler_path.is_file() or not wrangler_path.is_absolute():
        raise CloudflarePagesError("Cloudflare deployment runtime is invalid.")

    env = _deployment_env(account_id, token)

    command = [
        str(wrangler_path),
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
    output = "".join(ch for ch in output if ch in "\n\t" or ord(ch) >= 32)

    if result.returncode != 0:
        # Keep provider diagnostics bounded and scrubbed; no environment dump/path disclosure.
        raise CloudflarePagesError("Cloudflare Pages deployment failed. Provider output: " + output[-1200:])

    match = re.search(r"https://[A-Za-z0-9.-]+\.pages\.dev(?:/[^\s]*)?", output)

    return {
        "provider": "cloudflare_pages",
        "project": project,
        "branch": branch,
        "deployment_url": match.group(0) if match else None,
        "success": True,
    }
