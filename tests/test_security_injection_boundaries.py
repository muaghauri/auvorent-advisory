from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.app.phase6_renderer import clean_fragment, safe_local_url
from backend.app.schemas import (
    CreatePageInput,
    CreateSectionInput,
    NavigationItemInput,
    ReorderSectionsInput,
    UpdateSettingsInput,
)


def test_navigation_blocks_script_and_protocol_relative_urls():
    for bad in (
        "javascript:alert(1)",
        "data:text/html,<script>alert(1)</script>",
        "//evil.example/path",
        "/../../admin",
        "http://example.com",
    ):
        with pytest.raises(ValidationError):
            NavigationItemInput(label="Unsafe", url=bad)

    assert NavigationItemInput(label="Contact", url="/contact/").url == "/contact/"
    assert NavigationItemInput(label="External", url="https://example.com/path").url.startswith("https://")


def test_page_slug_and_template_identifiers_are_bounded():
    with pytest.raises(ValidationError):
        CreatePageInput(title="Bad", route="/bad/", slug="Bad Slug")
    with pytest.raises(ValidationError):
        CreatePageInput(title="Bad", route="/bad/", slug="bad", template="../../template")


def test_section_payload_size_is_bounded():
    CreateSectionInput(section_key="hero", section_type="hero", content={"heading": "Safe"})
    with pytest.raises(ValidationError):
        CreateSectionInput(section_key="hero", section_type="hero", content={"body": "x" * (257 * 1024)})


def test_section_reorder_rejects_duplicate_ids():
    with pytest.raises(ValidationError):
        ReorderSectionsInput(section_ids=["one", "one"])


def test_settings_batch_and_values_are_bounded():
    UpdateSettingsInput(values={"brand.tagline": "Business clarity"})
    with pytest.raises(ValidationError):
        UpdateSettingsInput(values={f"k{i}": "v" for i in range(26)})
    with pytest.raises(ValidationError):
        UpdateSettingsInput(values={"brand.tagline": "x" * (33 * 1024)})


def test_renderer_removes_executable_html_and_unsafe_urls():
    dirty = """
    <section onclick="alert(1)">
      <script>alert(1)</script>
      <iframe src="https://evil.example"></iframe>
      <a href="javascript:alert(1)">bad</a>
      <img src="https://evil.example/a.png" onerror="alert(1)">
      <p class="safe-class">Hello</p>
    </section>
    """
    clean = clean_fragment(dirty).lower()
    assert "<script" not in clean
    assert "<iframe" not in clean
    assert "onclick" not in clean
    assert "onerror" not in clean
    assert "javascript:" not in clean
    assert "https://evil.example" not in clean
    assert "hello" in clean


def test_local_url_guard_blocks_traversal_and_external_protocols():
    assert safe_local_url("/contact/?from=assessment") == "/contact/?from=assessment"
    assert safe_local_url("/assets/image.webp") == "/assets/image.webp"
    for bad in ("//evil.example", "../secret", "/a/../secret", "javascript:alert(1)", "https://evil.example"):
        assert safe_local_url(bad) is None


def test_public_site_header_policy_covers_admin_api_and_clickjacking():
    headers = (Path(__file__).resolve().parents[1] / "seed" / "v6_site" / "_headers").read_text(encoding="utf-8")
    lower = headers.lower()
    assert "strict-transport-security" in lower
    assert "x-frame-options: deny" in lower
    assert "frame-ancestors 'none'" in lower
    assert "object-src 'none'" in lower
    assert "https://admin.auvorent.com" in headers
