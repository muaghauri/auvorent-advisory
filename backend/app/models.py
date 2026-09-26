from __future__ import annotations
from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base

def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)

class User(Base):
    __tablename__ = "cms_users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(300))
    role: Mapped[str] = mapped_column(String(32), default="viewer", index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False)
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    sessions: Mapped[list["CMSession"]] = relationship(back_populates="user", cascade="all,delete-orphan")

class CMSession(Base):
    __tablename__ = "cms_sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("cms_users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    user: Mapped[User] = relationship(back_populates="sessions")

class LoginAttempt(Base):
    __tablename__ = "cms_login_attempts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(320), index=True)
    ip_hash: Mapped[str] = mapped_column(String(64), index=True)
    succeeded: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

class AuditLog(Base):
    __tablename__ = "cms_audit_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(80), index=True)
    target_type: Mapped[str] = mapped_column(String(64))
    target_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    detail: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

Index("ix_cms_login_attempts_ip_created", LoginAttempt.ip_hash, LoginAttempt.created_at)


class Page(Base):
    __tablename__ = "cms_pages"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    route: Mapped[str] = mapped_column(String(240), unique=True, index=True)
    slug: Mapped[str] = mapped_column(String(180), index=True)
    title: Mapped[str] = mapped_column(String(180))
    template: Mapped[str] = mapped_column(String(80), default="standard")
    status: Mapped[str] = mapped_column(String(24), default="draft", index=True)
    show_in_navigation: Mapped[bool] = mapped_column(Boolean, default=False)
    is_indexable: Mapped[bool] = mapped_column(Boolean, default=False)
    seo_title: Mapped[str] = mapped_column(String(180), default="")
    meta_description: Mapped[str] = mapped_column(String(320), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    sections: Mapped[list["PageSection"]] = relationship(back_populates="page", cascade="all,delete-orphan", order_by="PageSection.position")

class PageSection(Base):
    __tablename__ = "cms_page_sections"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    page_id: Mapped[str] = mapped_column(ForeignKey("cms_pages.id", ondelete="CASCADE"), index=True)
    section_key: Mapped[str] = mapped_column(String(120), index=True)
    section_type: Mapped[str] = mapped_column(String(80), default="rich_text")
    position: Mapped[int] = mapped_column(Integer, default=0)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    content_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    page: Mapped[Page] = relationship(back_populates="sections")

class NavigationItem(Base):
    __tablename__ = "cms_navigation_items"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    location: Mapped[str] = mapped_column(String(32), default="header", index=True)
    label: Mapped[str] = mapped_column(String(100))
    url: Mapped[str] = mapped_column(String(300))
    position: Mapped[int] = mapped_column(Integer, default=0)
    is_visible: Mapped[bool] = mapped_column(Boolean, default=True)
    open_new_tab: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

class SiteSetting(Base):
    __tablename__ = "cms_site_settings"
    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    value_json: Mapped[str] = mapped_column(Text, default="null")
    group_name: Mapped[str] = mapped_column(String(60), default="general", index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

class ContentRevision(Base):
    __tablename__ = "cms_content_revisions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_type: Mapped[str] = mapped_column(String(40), index=True)
    entity_id: Mapped[str] = mapped_column(String(80), index=True)
    snapshot_json: Mapped[str] = mapped_column(Text)
    actor_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

# Phase 3 — stable collection IDs, media references and content relationships.
class CollectionEntry(Base):
    __tablename__ = "cms_collection_entries"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    title: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(180))
    summary: Mapped[str] = mapped_column(Text, default="")
    body_markdown: Mapped[str] = mapped_column(Text, default="")
    content_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(24), default="draft", index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False)
    hero_media_id: Mapped[str | None] = mapped_column(ForeignKey("cms_media_assets.id", ondelete="SET NULL"), nullable=True)
    icon_media_id: Mapped[str | None] = mapped_column(ForeignKey("cms_media_assets.id", ondelete="SET NULL"), nullable=True)
    seo_title: Mapped[str] = mapped_column(String(180), default="")
    meta_description: Mapped[str] = mapped_column(String(320), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

Index("uq_cms_collection_kind_slug", CollectionEntry.kind, CollectionEntry.slug, unique=True)

class CollectionRelationship(Base):
    __tablename__ = "cms_collection_relationships"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("cms_collection_entries.id", ondelete="CASCADE"), index=True)
    target_id: Mapped[str] = mapped_column(ForeignKey("cms_collection_entries.id", ondelete="CASCADE"), index=True)
    relation: Mapped[str] = mapped_column(String(40), default="related")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

Index("uq_cms_collection_relationship", CollectionRelationship.source_id, CollectionRelationship.target_id, CollectionRelationship.relation, unique=True)

class MediaAsset(Base):
    __tablename__ = "cms_media_assets"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    original_name: Mapped[str] = mapped_column(String(240))
    storage_name: Mapped[str] = mapped_column(String(100), unique=True)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    mime_type: Mapped[str] = mapped_column(String(90))
    kind: Mapped[str] = mapped_column(String(24), index=True)  # image | icon | document | brand
    icon_style: Mapped[str | None] = mapped_column(String(16), nullable=True)  # line | filled
    byte_size: Mapped[int] = mapped_column(Integer)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    alt_text: Mapped[str] = mapped_column(String(300), default="")
    caption: Mapped[str] = mapped_column(String(500), default="")
    source_notes: Mapped[str] = mapped_column(String(500), default="")
    decorative: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

class MediaUsage(Base):
    __tablename__ = "cms_media_usages"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    media_id: Mapped[str] = mapped_column(ForeignKey("cms_media_assets.id", ondelete="CASCADE"), index=True)
    owner_type: Mapped[str] = mapped_column(String(32)) # collection | page_section
    owner_id: Mapped[str] = mapped_column(String(36), index=True)
    slot: Mapped[str] = mapped_column(String(36)) # hero | icon | illustration | image
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

Index("uq_cms_media_usage", MediaUsage.media_id, MediaUsage.owner_type, MediaUsage.owner_id, MediaUsage.slot, unique=True)

# Phase 4 — lead capture, managed forms and the preliminary optimization assessment.
class FormDefinition(Base):
    __tablename__ = "cms_forms"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(180))
    intro: Mapped[str] = mapped_column(Text, default="")
    success_message: Mapped[str] = mapped_column(String(500), default="Thank you. We will review your inquiry.")
    fields_json: Mapped[str] = mapped_column(Text, default="[]")
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

class LeadSettings(Base):
    __tablename__ = "cms_lead_settings"
    id: Mapped[str] = mapped_column(String(20), primary_key=True, default="primary")
    recipient_email: Mapped[str] = mapped_column(String(254), default="muaghauri@gmail.com")
    cc_json: Mapped[str] = mapped_column(Text, default="[]")
    reply_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    subject_prefix: Mapped[str] = mapped_column(String(100), default="Auvorent inquiry")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

class Inquiry(Base):
    __tablename__ = "cms_inquiries"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    form_id: Mapped[str] = mapped_column(ForeignKey("cms_forms.id", ondelete="RESTRICT"), index=True)
    name: Mapped[str] = mapped_column(String(180), default="")
    email: Mapped[str] = mapped_column(String(254), default="")
    company: Mapped[str] = mapped_column(String(180), default="")
    priority: Mapped[str] = mapped_column(String(160), default="")
    answers_json: Mapped[str] = mapped_column(Text, default="{}")
    source_page: Mapped[str] = mapped_column(String(300), default="")
    utm_json: Mapped[str] = mapped_column(Text, default="{}")
    consent: Mapped[bool] = mapped_column(Boolean, default=False)
    ip_hash: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(24), default="new", index=True)
    assigned_user_id: Mapped[str | None] = mapped_column(ForeignKey("cms_users.id", ondelete="SET NULL"), nullable=True)
    notification_status: Mapped[str] = mapped_column(String(24), default="pending")
    notification_attempts: Mapped[int] = mapped_column(Integer, default=0)
    notified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

class InquiryNote(Base):
    __tablename__ = "cms_inquiry_notes"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    inquiry_id: Mapped[str] = mapped_column(ForeignKey("cms_inquiries.id", ondelete="CASCADE"), index=True)
    author_id: Mapped[str | None] = mapped_column(ForeignKey("cms_users.id", ondelete="SET NULL"), nullable=True)
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

class AssessmentDefinition(Base):
    __tablename__ = "cms_assessments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    intro: Mapped[str] = mapped_column(Text, default="")
    disclaimer: Mapped[str] = mapped_column(String(600), default="This is a preliminary screening, not a verified business diagnosis.")
    questions_json: Mapped[str] = mapped_column(Text, default="[]")
    results_json: Mapped[str] = mapped_column(Text, default="{}")
    cta_label: Mapped[str] = mapped_column(String(100), default="Request a strategy conversation")
    cta_url: Mapped[str] = mapped_column(String(300), default="/contact/")
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

# Phase 5 — SEO, gated editorial approval, private previews and immutable staging releases.
class SeoRecord(Base):
    __tablename__ = 'cms_seo_records'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(32), index=True)
    entity_id: Mapped[str] = mapped_column(String(36), index=True)
    seo_title: Mapped[str] = mapped_column(String(180), default='')
    meta_description: Mapped[str] = mapped_column(String(320), default='')
    canonical_override: Mapped[str] = mapped_column(String(512), default='')
    robots_index: Mapped[bool] = mapped_column(Boolean, default=False)
    robots_follow: Mapped[bool] = mapped_column(Boolean, default=True)
    og_title: Mapped[str] = mapped_column(String(180), default='')
    og_description: Mapped[str] = mapped_column(String(320), default='')
    og_image_media_id: Mapped[str | None] = mapped_column(ForeignKey('cms_media_assets.id', ondelete='SET NULL'), nullable=True)
    schema_type: Mapped[str] = mapped_column(String(32), default='WebPage')
    breadcrumb_title: Mapped[str] = mapped_column(String(180), default='')
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

Index('uq_cms_seo_entity', SeoRecord.entity_type, SeoRecord.entity_id, unique=True)

class RedirectRule(Base):
    __tablename__ = 'cms_redirects'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    old_path: Mapped[str] = mapped_column(String(255))
    new_path: Mapped[str] = mapped_column(String(255))
    status_code: Mapped[int] = mapped_column(Integer, default=301)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    note: Mapped[str] = mapped_column(String(300), default='')
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

class EditorialReview(Base):
    __tablename__ = 'cms_editorial_reviews'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(32), index=True)
    entity_id: Mapped[str] = mapped_column(String(36), index=True)
    state: Mapped[str] = mapped_column(String(24), default='in_review', index=True)
    content_hash: Mapped[str] = mapped_column(String(64))
    requested_by: Mapped[str] = mapped_column(String(36))
    reviewed_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    note: Mapped[str] = mapped_column(String(1000), default='')
    requested_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

class PrivatePreview(Base):
    __tablename__ = 'cms_private_previews'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64))
    entity_type: Mapped[str] = mapped_column(String(32))
    entity_id: Mapped[str] = mapped_column(String(36))
    snapshot_json: Mapped[str] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String(36))
    expires_at: Mapped[datetime] = mapped_column(DateTime)

class PublishDeployment(Base):
    __tablename__ = 'cms_publish_deployments'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    release_id: Mapped[str | None] = mapped_column(String(72), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default='queued', index=True)
    environment: Mapped[str] = mapped_column(String(32), default='local_staging')
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    requested_by: Mapped[str] = mapped_column(String(36))
    report_json: Mapped[str] = mapped_column(Text, default='{}')
    error_message: Mapped[str] = mapped_column(String(1000), default='')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

Index("ix_cms_redirects_old_path",RedirectRule.old_path,unique=True)
Index("ix_cms_private_previews_token_hash",PrivatePreview.token_hash,unique=True)
Index("uq_cms_publish_release",PublishDeployment.release_id,unique=True)
