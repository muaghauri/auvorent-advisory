from __future__ import annotations

import json
import re
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

Role = Literal["super_admin", "admin", "editor", "reviewer", "viewer"]
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_KEY = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,119}$")


def _clean_text(value: str, *, label: str) -> str:
    value = value.strip()
    if _CONTROL.search(value):
        raise ValueError(f"{label} contains prohibited control characters")
    return value


def _safe_navigation_url(value: str) -> str:
    value = value.strip()
    if _CONTROL.search(value) or "\\" in value:
        raise ValueError("Navigation URL contains prohibited characters")
    if value.startswith("/") and not value.startswith("//") and ".." not in value:
        return value
    parsed = urlparse(value)
    if (
        parsed.scheme == "https"
        and parsed.hostname
        and not parsed.username
        and not parsed.password
    ):
        return value
    raise ValueError("Navigation URL must be a safe local path or full HTTPS URL")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LoginInput(StrictModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class ChangePasswordInput(StrictModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=12, max_length=128)


class CreateUserInput(StrictModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=120)
    role: Role = "viewer"
    initial_password: str = Field(min_length=12, max_length=128)

    @field_validator("full_name")
    @classmethod
    def meaningful_name(cls, value: str) -> str:
        value = _clean_text(value, label="Full name")
        if len(value) < 2:
            raise ValueError("Provide a full name")
        return value


class UpdateUserInput(StrictModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=120)
    role: Role | None = None
    is_active: bool | None = None

    @field_validator("full_name")
    @classmethod
    def meaningful_update_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = _clean_text(value, label="Full name")
        if len(value) < 2:
            raise ValueError("Provide a full name")
        return value


class ResetUserPasswordInput(StrictModel):
    new_password: str = Field(min_length=12, max_length=128)


PageStatus = Literal["draft", "unpublished", "archived"]


class CreatePageInput(StrictModel):
    title: str = Field(min_length=2, max_length=180)
    route: str = Field(min_length=1, max_length=240)
    slug: str = Field(min_length=1, max_length=180)
    template: str = Field(default="standard", max_length=80)
    status: PageStatus = "draft"
    show_in_navigation: bool = False
    is_indexable: bool = False
    seo_title: str = Field(default="", max_length=180)
    meta_description: str = Field(default="", max_length=320)

    @field_validator("title", "seo_title", "meta_description")
    @classmethod
    def safe_text(cls, value: str) -> str:
        return _clean_text(value, label="Text")

    @field_validator("slug")
    @classmethod
    def safe_slug(cls, value: str) -> str:
        value = value.strip().strip("/")
        if not _SLUG.fullmatch(value):
            raise ValueError("Slug must contain lowercase letters, numbers and single hyphens")
        return value

    @field_validator("template")
    @classmethod
    def safe_template(cls, value: str) -> str:
        value = value.strip()
        if not _KEY.fullmatch(value):
            raise ValueError("Invalid page template identifier")
        return value


class UpdatePageInput(StrictModel):
    title: str | None = Field(default=None, min_length=2, max_length=180)
    route: str | None = Field(default=None, min_length=1, max_length=240)
    slug: str | None = Field(default=None, min_length=1, max_length=180)
    template: str | None = Field(default=None, max_length=80)
    status: PageStatus | None = None
    show_in_navigation: bool | None = None
    is_indexable: bool | None = None
    seo_title: str | None = Field(default=None, max_length=180)
    meta_description: str | None = Field(default=None, max_length=320)

    @field_validator("title", "seo_title", "meta_description")
    @classmethod
    def safe_optional_text(cls, value: str | None) -> str | None:
        return _clean_text(value, label="Text") if value is not None else value

    @field_validator("slug")
    @classmethod
    def safe_optional_slug(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip().strip("/")
        if not _SLUG.fullmatch(value):
            raise ValueError("Slug must contain lowercase letters, numbers and single hyphens")
        return value

    @field_validator("template")
    @classmethod
    def safe_optional_template(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not _KEY.fullmatch(value):
            raise ValueError("Invalid page template identifier")
        return value


class CreateSectionInput(StrictModel):
    section_key: str = Field(min_length=1, max_length=120)
    section_type: str = Field(default="rich_text", max_length=80)
    position: int = Field(default=0, ge=0, le=500)
    is_enabled: bool = True
    content: dict = Field(default_factory=dict)

    @field_validator("section_key", "section_type")
    @classmethod
    def safe_section_identifier(cls, value: str) -> str:
        value = value.strip()
        if not _KEY.fullmatch(value):
            raise ValueError("Section identifiers may contain letters, numbers, underscores and hyphens")
        return value

    @field_validator("content")
    @classmethod
    def bounded_content(cls, value: dict) -> dict:
        if len(value) > 100 or len(json.dumps(value, ensure_ascii=False).encode("utf-8")) > 256 * 1024:
            raise ValueError("Section content exceeds the allowed size")
        return value


class UpdateSectionInput(StrictModel):
    section_key: str | None = Field(default=None, min_length=1, max_length=120)
    section_type: str | None = Field(default=None, max_length=80)
    position: int | None = Field(default=None, ge=0, le=500)
    is_enabled: bool | None = None
    content: dict | None = None

    @field_validator("section_key", "section_type")
    @classmethod
    def safe_optional_section_identifier(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not _KEY.fullmatch(value):
            raise ValueError("Section identifiers may contain letters, numbers, underscores and hyphens")
        return value

    @field_validator("content")
    @classmethod
    def bounded_optional_content(cls, value: dict | None) -> dict | None:
        if value is not None and (len(value) > 100 or len(json.dumps(value, ensure_ascii=False).encode("utf-8")) > 256 * 1024):
            raise ValueError("Section content exceeds the allowed size")
        return value


class ReorderSectionsInput(StrictModel):
    section_ids: list[str] = Field(min_length=1, max_length=200)

    @field_validator("section_ids")
    @classmethod
    def unique_section_ids(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("section_ids must not contain duplicates")
        return value


class NavigationItemInput(StrictModel):
    id: str | None = None
    location: Literal["header", "footer", "utility"] = "header"
    label: str = Field(min_length=1, max_length=100)
    url: str = Field(min_length=1, max_length=300)
    position: int = Field(default=0, ge=0, le=500)
    is_visible: bool = True
    open_new_tab: bool = False

    @field_validator("label")
    @classmethod
    def safe_label(cls, value: str) -> str:
        return _clean_text(value, label="Navigation label")

    @field_validator("url")
    @classmethod
    def safe_url(cls, value: str) -> str:
        return _safe_navigation_url(value)

    @field_validator("id")
    @classmethod
    def safe_id(cls, value: str | None) -> str | None:
        if value is not None and (len(value) > 80 or _CONTROL.search(value)):
            raise ValueError("Invalid navigation item ID")
        return value


class ReplaceNavigationInput(StrictModel):
    items: list[NavigationItemInput] = Field(default_factory=list, max_length=200)

    @field_validator("items")
    @classmethod
    def unique_ids(cls, items: list[NavigationItemInput]) -> list[NavigationItemInput]:
        ids = [item.id for item in items if item.id]
        if len(ids) != len(set(ids)):
            raise ValueError("Navigation item IDs must be unique")
        return items


class UpdateSettingsInput(StrictModel):
    values: dict[str, object]

    @field_validator("values")
    @classmethod
    def bounded_values(cls, values: dict[str, object]) -> dict[str, object]:
        if len(values) > 25:
            raise ValueError("Too many settings in one update")
        for key, value in values.items():
            if not isinstance(key, str) or len(key) > 120 or _CONTROL.search(key):
                raise ValueError("Invalid setting key")
            try:
                encoded = json.dumps(value, ensure_ascii=False)
            except (TypeError, ValueError) as exc:
                raise ValueError("Settings must contain JSON-compatible values") from exc
            if len(encoded.encode("utf-8")) > 32 * 1024:
                raise ValueError(f"Setting '{key}' is too large")
        return values
