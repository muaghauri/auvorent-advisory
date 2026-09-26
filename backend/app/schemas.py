from __future__ import annotations
from pydantic import BaseModel, EmailStr, Field, ConfigDict, field_validator
from typing import Literal

Role = Literal["super_admin", "admin", "editor", "reviewer", "viewer"]

class LoginInput(BaseModel):
    email: EmailStr
    password: str

class ChangePasswordInput(BaseModel):
    current_password: str
    new_password: str = Field(min_length=12, max_length=128)

class CreateUserInput(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=120)
    role: Role = "viewer"
    initial_password: str = Field(min_length=12, max_length=128)

    @field_validator("full_name")
    @classmethod
    def meaningful_name(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 2:
            raise ValueError("Provide a full name")
        return value

class UpdateUserInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    full_name: str | None = Field(default=None, min_length=2, max_length=120)
    role: Role | None = None
    is_active: bool | None = None

    @field_validator("full_name")
    @classmethod
    def meaningful_update_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if len(value) < 2:
            raise ValueError("Provide a full name")
        return value

class ResetUserPasswordInput(BaseModel):
    new_password: str = Field(min_length=12, max_length=128)


PageStatus = Literal["draft", "unpublished", "archived"]

class CreatePageInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=2, max_length=180)
    route: str = Field(min_length=1, max_length=240)
    slug: str = Field(min_length=1, max_length=180)
    template: str = Field(default="standard", max_length=80)
    status: PageStatus = "draft"
    show_in_navigation: bool = False
    is_indexable: bool = False
    seo_title: str = Field(default="", max_length=180)
    meta_description: str = Field(default="", max_length=320)

class UpdatePageInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, min_length=2, max_length=180)
    route: str | None = Field(default=None, min_length=1, max_length=240)
    slug: str | None = Field(default=None, min_length=1, max_length=180)
    template: str | None = Field(default=None, max_length=80)
    status: PageStatus | None = None
    show_in_navigation: bool | None = None
    is_indexable: bool | None = None
    seo_title: str | None = Field(default=None, max_length=180)
    meta_description: str | None = Field(default=None, max_length=320)

class CreateSectionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    section_key: str = Field(min_length=1, max_length=120)
    section_type: str = Field(default="rich_text", max_length=80)
    position: int = Field(default=0, ge=0, le=500)
    is_enabled: bool = True
    content: dict = Field(default_factory=dict)

class UpdateSectionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    section_key: str | None = Field(default=None, min_length=1, max_length=120)
    section_type: str | None = Field(default=None, max_length=80)
    position: int | None = Field(default=None, ge=0, le=500)
    is_enabled: bool | None = None
    content: dict | None = None

class ReorderSectionsInput(BaseModel):
    section_ids: list[str] = Field(min_length=1, max_length=200)

class NavigationItemInput(BaseModel):
    id: str | None = None
    location: Literal["header", "footer", "utility"] = "header"
    label: str = Field(min_length=1, max_length=100)
    url: str = Field(min_length=1, max_length=300)
    position: int = Field(default=0, ge=0, le=500)
    is_visible: bool = True
    open_new_tab: bool = False

class ReplaceNavigationInput(BaseModel):
    items: list[NavigationItemInput] = Field(default_factory=list, max_length=200)

class UpdateSettingsInput(BaseModel):
    values: dict[str, object]
