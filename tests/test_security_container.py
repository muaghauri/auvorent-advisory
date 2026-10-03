from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_runtime_container_drops_root_privileges():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "USER auvorent" in dockerfile
    assert "adduser --system --group --disabled-password auvorent" in dockerfile


def test_docker_context_excludes_credentials_and_local_state():
    entries = {
        line.strip()
        for line in (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    for required in {
        ".git",
        ".env",
        ".env.*",
        "*.pem",
        "*.key",
        "*.p12",
        "*.pfx",
        "instance",
        "*.sqlite",
        "node_modules",
    }:
        assert required in entries
