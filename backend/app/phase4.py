"""Phase 4: configurable forms, safe public submission, inquiries, notifications and preliminary assessment.

Public forms are served from this API; wiring the V6 static site to these endpoints is Phase 6.
Secrets reside in environment configuration. A saved inquiry is never represented as an
emailed inquiry unless SMTP completed successfully.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import smtplib
import uuid
from datetime import timedelta
from email.message import EmailMessage
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, EmailStr, Field, ValidationError, field_validator, model_validator
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .models import AssessmentDefinition, ContentRevision, FormDefinition, Inquiry, InquiryNote, LeadSettings, User, utcnow
from .security import audit, get_db, require_csrf, require_permission

router = APIRouter(prefix="/api/v1", tags=["Leads & Assessments"])
SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
KEY = re.compile(r"^[a-z][a-z0-9_]{0,49}$")
INQUIRY_STATUSES = {"new", "reviewed", "qualified", "follow_up", "converted", "closed", "spam"}


def json_out(raw: str, fallback):
    try:
        data = json.loads(raw)
        return data if isinstance(data, type(fallback)) else fallback
    except (ValueError, TypeError):
        return fallback


def iso(dt):
    return dt.isoformat() + "Z" if dt else None


class FormField(BaseModel):
    id: str = Field(max_length=50)
    label: str = Field(min_length=1, max_length=120)
    type: Literal["text", "email", "textarea", "select", "checkbox"]
    required: bool = False
    placeholder: str = Field(default="", max_length=240)
    help_text: str = Field(default="", max_length=400)
    options: list[str] = Field(default_factory=list, max_length=40)
    max_length: int = Field(default=400, ge=1, le=5000)

    @field_validator("id")
    @classmethod
    def valid_id(cls, v):
        if not KEY.fullmatch(v):
            raise ValueError("Field ID must be lowercase letters, numbers or underscores")
        return v

    @model_validator(mode="after")
    def options_valid(self):
        if self.type == "select":
            if not self.options or len(set(self.options)) != len(self.options):
                raise ValueError("Select fields require unique options")
            if any(not x or len(x) > 120 for x in self.options):
                raise ValueError("Select option length must be 1–120 characters")
        elif self.options:
            raise ValueError("Only select fields have options")
        return self


class FormCreate(BaseModel):
    slug: str = Field(min_length=3, max_length=100)
    title: str = Field(min_length=3, max_length=180)
    intro: str = Field(default="", max_length=1500)
    success_message: str = Field(default="Thank you. We will review your inquiry.", min_length=3, max_length=500)
    fields: list[FormField] = Field(min_length=1, max_length=30)
    is_active: bool = False

    @field_validator("slug")
    @classmethod
    def valid_slug(cls, v):
        if not SLUG.fullmatch(v):
            raise ValueError("Invalid form slug")
        return v

    @model_validator(mode="after")
    def distinct_fields(self):
        ids = [f.id for f in self.fields]
        if {"website", "consent"}.intersection(ids):
            raise ValueError("website and consent are reserved submission fields")
        if len(ids) != len(set(ids)):
            raise ValueError("Field IDs must be unique")
        return self


class FormPatch(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=180)
    intro: str | None = Field(default=None, max_length=1500)
    success_message: str | None = Field(default=None, min_length=3, max_length=500)
    fields: list[FormField] | None = Field(default=None, min_length=1, max_length=30)
    is_active: bool | None = None

    @model_validator(mode="after")
    def distinct_fields(self):
        if self.fields and {"website", "consent"}.intersection({f.id for f in self.fields}):
            raise ValueError("website and consent are reserved submission fields")
        if self.fields and len({f.id for f in self.fields}) != len(self.fields):
            raise ValueError("Field IDs must be unique")
        return self


class LeadSettingsPatch(BaseModel):
    recipient_email: EmailStr
    cc: list[EmailStr] = Field(default_factory=list, max_length=5)
    reply_enabled: bool = False
    subject_prefix: str = Field(default="Auvorent inquiry", min_length=3, max_length=100)

    @field_validator("subject_prefix")
    @classmethod
    def safe_subject(cls, value):
        if "\n" in value or "\r" in value:
            raise ValueError("Email subject prefix cannot contain line breaks")
        return value


class PublicFormSubmission(BaseModel):
    data: dict[str, Any] = Field(default_factory=dict)
    consent: bool
    website: str = Field(default="", max_length=200)  # Honeypot; must be visually hidden on public V6 form.
    source_page: str = Field(default="", max_length=300)
    utm: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def sized(self):
        if len(self.data) > 40 or len(self.utm) > 8:
            raise ValueError("Too many fields")
        if any(len(k) > 50 or len(v) > 120 for k, v in self.utm.items()):
            raise ValueError("UTM parameters too long")
        return self


class InquiryPatch(BaseModel):
    status: Literal["new", "reviewed", "qualified", "follow_up", "converted", "closed", "spam"] | None = None
    assigned_user_id: str | None = None


class NoteCreate(BaseModel):
    text: str = Field(min_length=2, max_length=5000)


class AssessmentOption(BaseModel):
    id: str = Field(min_length=1, max_length=50)
    label: str = Field(min_length=1, max_length=160)

    @field_validator("id")
    @classmethod
    def key(cls, v):
        if not KEY.fullmatch(v):
            raise ValueError("Invalid option ID")
        return v


class AssessmentQuestion(BaseModel):
    id: str = Field(min_length=1, max_length=50)
    prompt: str = Field(min_length=3, max_length=300)
    options: list[AssessmentOption] = Field(min_length=2, max_length=10)
    required: bool = True

    @model_validator(mode="after")
    def distinct(self):
        if not KEY.fullmatch(self.id) or len({o.id for o in self.options}) != len(self.options):
            raise ValueError("Invalid question ID or duplicate option ID")
        return self


class AssessmentResult(BaseModel):
    title: str = Field(min_length=3, max_length=150)
    description: str = Field(min_length=3, max_length=600)


class AssessmentCreate(BaseModel):
    slug: str = Field(min_length=3, max_length=100)
    title: str = Field(min_length=3, max_length=200)
    intro: str = Field(default="", max_length=1500)
    disclaimer: str = Field(default="This is a preliminary screening, not a verified business diagnosis.", min_length=20, max_length=600)
    questions: list[AssessmentQuestion] = Field(min_length=1, max_length=20)
    results: dict[str, AssessmentResult] = Field(default_factory=dict)
    cta_label: str = Field(default="Request a strategy conversation", max_length=100)
    cta_url: str = Field(default="/contact/", max_length=300)
    is_active: bool = False

    @field_validator("slug")
    @classmethod
    def valid_slug(cls, v):
        if not SLUG.fullmatch(v):
            raise ValueError("Invalid slug")
        return v

    @field_validator("cta_url")
    @classmethod
    def cta_link(cls, v):
        if not (v.startswith("/") and not v.startswith("//")):
            raise ValueError("CTA must be an internal path")
        return v

    @model_validator(mode="after")
    def valid_results(self):
        if len({q.id for q in self.questions}) != len(self.questions):
            raise ValueError("Question IDs must be unique")
        choices = {f"{q.id}.{o.id}" for q in self.questions for o in q.options}
        if not set(self.results).issubset(choices):
            raise ValueError("Result rules must reference existing question.option IDs")
        return self


class AssessmentPatch(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=200)
    intro: str | None = Field(default=None, max_length=1500)
    disclaimer: str | None = Field(default=None, min_length=20, max_length=600)
    questions: list[AssessmentQuestion] | None = Field(default=None, min_length=1, max_length=20)
    results: dict[str, AssessmentResult] | None = None
    cta_label: str | None = Field(default=None, max_length=100)
    cta_url: str | None = None
    is_active: bool | None = None

    @field_validator("cta_url")
    @classmethod
    def cta_link(cls, v):
        if v is not None and not (v.startswith("/") and not v.startswith("//")):
            raise ValueError("CTA must be an internal path")
        return v


class AssessmentAnswers(BaseModel):
    answers: dict[str, str] = Field(min_length=1, max_length=20)


def form_out(f: FormDefinition):
    return {"id": f.id, "slug": f.slug, "title": f.title, "intro": f.intro,
            "success_message": f.success_message, "fields": json_out(f.fields_json, []),
            "is_active": f.is_active, "created_at": iso(f.created_at), "updated_at": iso(f.updated_at)}


def lead_out(s: LeadSettings):
    return {"recipient_email": s.recipient_email, "cc": json_out(s.cc_json, []),
            "reply_enabled": s.reply_enabled, "subject_prefix": s.subject_prefix}


def inquiry_out(i: Inquiry, detailed=False):
    result = {"id": i.id, "form_id": i.form_id, "name": i.name, "email": i.email,
              "company": i.company, "priority": i.priority, "status": i.status,
              "assigned_user_id": i.assigned_user_id, "notification_status": i.notification_status,
              "notification_attempts": i.notification_attempts, "created_at": iso(i.created_at)}
    if detailed:
        result.update(answers=json_out(i.answers_json, {}), source_page=i.source_page,
                      utm=json_out(i.utm_json, {}), consent=i.consent, notified_at=iso(i.notified_at))
    return result


def assessment_out(a: AssessmentDefinition):
    return {"id": a.id, "slug": a.slug, "title": a.title, "intro": a.intro,
            "disclaimer": a.disclaimer, "questions": json_out(a.questions_json, []),
            "results": json_out(a.results_json, {}), "cta_label": a.cta_label,
            "cta_url": a.cta_url, "is_active": a.is_active, "updated_at": iso(a.updated_at)}


def revision(db, kind, entry_id, snapshot, actor):
    db.add(ContentRevision(entity_type=kind, entity_id=entry_id,
                           snapshot_json=json.dumps(snapshot, ensure_ascii=False), actor_user_id=actor.id))


def lead_settings(db):
    settings = db.get(LeadSettings, "primary")
    if not settings:
        settings = LeadSettings(id="primary", recipient_email="muaghauri@gmail.com")
        db.add(settings)
        db.flush()
    return settings


def ensure_email(raw: str) -> str:
    # Strong validation by the same email validator used in public Pydantic payloads.
    class EmailOnly(BaseModel):
        email: EmailStr
    try:
        return str(EmailOnly(email=raw).email)
    except ValueError:
        raise HTTPException(422, "Invalid email address")


def validate_submission(fields: list[dict], payload: PublicFormSubmission):
    field_ids = {f["id"] for f in fields}
    if set(payload.data) - field_ids:
        raise HTTPException(422, "Unexpected form fields")
    cleaned = {}
    for field in fields:
        key = field["id"]
        val = payload.data.get(key, "")
        if field["type"] == "checkbox":
            if not isinstance(val, bool):
                raise HTTPException(422, f"{key}: expected checkbox")
            if field["required"] and not val:
                raise HTTPException(422, f"{key}: required")
        else:
            if not isinstance(val, str) or len(val) > field.get("max_length", 400):
                raise HTTPException(422, f"{key}: invalid value or too long")
            val = val.strip()
            if field["required"] and not val:
                raise HTTPException(422, f"{key}: required")
            if val and field["type"] == "email":
                val = ensure_email(val)
            if val and field["type"] == "select" and val not in field["options"]:
                raise HTTPException(422, f"{key}: invalid selection")
        cleaned[key] = val
    return cleaned


def smtp_sender(settings, route: LeadSettings, form: FormDefinition, inquiry: Inquiry):
    if not settings.smtp_host or not settings.mail_from:
        return "not_configured"
    msg = EmailMessage()
    msg["From"] = settings.mail_from
    msg["To"] = route.recipient_email
    cc = json_out(route.cc_json, [])
    if cc:
        msg["Cc"] = ", ".join(cc)
    if inquiry.email:
        msg["Reply-To"] = inquiry.email
    msg["Subject"] = f"{route.subject_prefix} — {form.title}"
    body = ["New Auvorent website inquiry", f"Form: {form.title}", f"Inquiry ID: {inquiry.id}",
            f"Submitted (UTC): {iso(inquiry.created_at)}", "", "Submitted fields:"]
    answers = json_out(inquiry.answers_json, {})
    for key, value in answers.items():
        body.append(f"{key}: {value}")
    body.extend(["", f"Source page: {inquiry.source_page}", "Contact consent: yes"])
    msg.set_content("\n".join(body))
    if settings.smtp_port == 465:
        with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
            if settings.smtp_username:
                smtp.login(settings.smtp_username, settings.smtp_password)
            smtp.send_message(msg)
    else:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.ehlo()
            if settings.smtp_username:
                smtp.login(settings.smtp_username, settings.smtp_password)
            smtp.send_message(msg)
    if route.reply_enabled and inquiry.email:
        acknowledgement = EmailMessage()
        acknowledgement["From"] = settings.mail_from
        acknowledgement["To"] = inquiry.email
        acknowledgement["Subject"] = "We received your Auvorent inquiry"
        acknowledgement.set_content("Thank you for contacting Auvorent Advisory. We will review your message and respond if an appropriate next step is identified.\n")
        # Auto-replies are optional and best-effort; do not block the client's notification.
        try:
            if settings.smtp_port == 465:
                with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
                    if settings.smtp_username: smtp.login(settings.smtp_username, settings.smtp_password)
                    smtp.send_message(acknowledgement)
            else:
                with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
                    smtp.starttls()
                    if settings.smtp_username: smtp.login(settings.smtp_username, settings.smtp_password)
                    smtp.send_message(acknowledgement)
        except (OSError, smtplib.SMTPException):
            pass
    return "sent"


def notify(request, db: Session, inquiry: Inquiry, form: FormDefinition):
    route = lead_settings(db)
    inquiry.notification_attempts += 1
    try:
        sender = getattr(request.app.state, "notification_sender", smtp_sender)
        status = sender(request.app.state.settings, route, form, inquiry)
        inquiry.notification_status = status if status in {"sent", "not_configured"} else "failed"
    except Exception:
        # Do not put provider diagnostics/secrets into responses or database content.
        inquiry.notification_status = "failed"
    if inquiry.notification_status == "sent":
        inquiry.notified_at = utcnow()
    db.commit()


@router.get("/forms")
def list_forms(actor: User = Depends(require_permission("content:read")), db: Session = Depends(get_db)):
    return {"items": [form_out(f) for f in db.query(FormDefinition).order_by(FormDefinition.title).all()]}


@router.post("/forms", status_code=201, dependencies=[Depends(require_csrf)])
def create_form(payload: FormCreate, actor: User = Depends(require_permission("content:edit")), db: Session = Depends(get_db)):
    if db.query(FormDefinition).filter_by(slug=payload.slug).first():
        raise HTTPException(409, "Form slug exists")
    f = FormDefinition(id=str(uuid.uuid4()), slug=payload.slug, title=payload.title,
                       intro=payload.intro, success_message=payload.success_message,
                       fields_json=json.dumps([x.model_dump() for x in payload.fields]), is_active=payload.is_active)
    db.add(f); audit(db, "form.created", actor=actor.id, target_type="form", target_id=f.id)
    db.commit()
    return {"form": form_out(f)}


@router.get("/forms/settings")
def get_lead_settings(actor: User = Depends(require_permission("settings:manage")), db: Session = Depends(get_db)):
    s = lead_settings(db)
    return {"settings": lead_out(s)}


@router.patch("/forms/settings", dependencies=[Depends(require_csrf)])
def update_lead_settings(payload: LeadSettingsPatch, actor: User = Depends(require_permission("settings:manage")), db: Session = Depends(get_db)):
    s = lead_settings(db)
    revision(db, "lead_settings", "primary", lead_out(s), actor)
    s.recipient_email = str(payload.recipient_email)
    s.cc_json = json.dumps([str(x) for x in payload.cc])
    s.reply_enabled = payload.reply_enabled
    s.subject_prefix = payload.subject_prefix.strip()
    audit(db, "leads.routing_updated", actor=actor.id, target_type="settings", target_id="lead")
    db.commit()
    return {"settings": lead_out(s)}


@router.get("/forms/{form_id}")
def get_form(form_id: str, actor: User = Depends(require_permission("content:read")), db: Session = Depends(get_db)):
    f = db.get(FormDefinition, form_id)
    if not f: raise HTTPException(404, "Form not found")
    return {"form": form_out(f)}


@router.patch("/forms/{form_id}", dependencies=[Depends(require_csrf)])
def patch_form(form_id: str, payload: FormPatch, actor: User = Depends(require_permission("content:edit")), db: Session = Depends(get_db)):
    f = db.get(FormDefinition, form_id)
    if not f: raise HTTPException(404, "Form not found")
    revision(db, "form", f.id, form_out(f), actor)
    changes = payload.model_dump(exclude_unset=True)
    for key, value in changes.items():
        if value is None: continue
        if key == "fields": f.fields_json = json.dumps(value)
        else: setattr(f, key, value)
    audit(db, "form.updated", actor=actor.id, target_type="form", target_id=f.id, fields=list(changes))
    db.commit()
    return {"form": form_out(f)}


@router.delete("/forms/{form_id}", dependencies=[Depends(require_csrf)])
def delete_form(form_id: str, actor: User = Depends(require_permission("content:edit")), db: Session = Depends(get_db)):
    f = db.get(FormDefinition, form_id)
    if not f: raise HTTPException(404, "Form not found")
    if db.query(Inquiry).filter_by(form_id=f.id).first(): raise HTTPException(409, "Form has inquiries. Disable it instead of deleting.")
    if f.is_active: raise HTTPException(409, "Disable active forms before deleting")
    audit(db, "form.deleted", actor=actor.id, target_type="form", target_id=f.id)
    db.delete(f); db.commit()
    return {"status": "deleted"}


@router.get("/public/forms/{slug}")
def public_form(slug: str, db: Session = Depends(get_db)):
    f = db.query(FormDefinition).filter_by(slug=slug, is_active=True).first()
    if not f: raise HTTPException(404, "Form unavailable")
    return {"slug": f.slug, "title": f.title, "intro": f.intro,
            "fields": json_out(f.fields_json, []), "success_message": f.success_message}


@router.post("/public/forms/{slug}/submit", status_code=202)
def submit_form(slug: str, payload: PublicFormSubmission, request: Request, db: Session = Depends(get_db)):
    f = db.query(FormDefinition).filter_by(slug=slug, is_active=True).first()
    if not f: raise HTTPException(404, "Form unavailable")
    if payload.website: return {"status": "accepted", "message": f.success_message}
    if not payload.consent: raise HTTPException(422, "Consent to be contacted is required")
    # Restrict cross-origin browser submissions. Direct server-to-server requests do not carry Origin.
    origin = request.headers.get("origin")
    allowed_origin = request.app.state.settings.public_site_origin
    if origin and (not allowed_origin or origin.rstrip("/") != allowed_origin.rstrip("/")):
        raise HTTPException(403, "Origin not allowed")
    # Local development uses the actual peer address; proxy configuration must be controlled by deployment.
    peer = request.client.host if request.client else "unknown"
    salt = request.app.state.settings.secret_key
    ip_hash = hashlib.sha256((salt + peer).encode()).hexdigest()
    recent = db.query(Inquiry).filter(Inquiry.ip_hash == ip_hash,
                                      Inquiry.created_at >= utcnow() - timedelta(hours=1)).count()
    if recent >= request.app.state.settings.public_form_rate_limit:
        raise HTTPException(429, "Too many inquiries from this connection. Try again later")
    cleaned = validate_submission(json_out(f.fields_json, []), payload)
    entry = Inquiry(id=str(uuid.uuid4()), form_id=f.id, name=cleaned.get("name", cleaned.get("full_name", "")),
                    email=cleaned.get("email", cleaned.get("work_email", "")), company=cleaned.get("company", ""),
                    priority=cleaned.get("priority", cleaned.get("main_priority", "")), answers_json=json.dumps(cleaned,ensure_ascii=False),
                    consent=True, source_page=payload.source_page, utm_json=json.dumps(payload.utm),
                    ip_hash=ip_hash, notification_status="pending")
    db.add(entry); db.commit()
    notify(request, db, entry, f)
    # Never disclose email delivery status to public callers.
    return {"status": "accepted", "message": f.success_message, "reference": entry.id}


@router.get("/inquiries")
def list_inquiries(status: str = Query("", max_length=24), search: str = Query("", max_length=120),
                   limit: int = Query(30, ge=1, le=100), offset: int = Query(0, ge=0),
                   actor: User = Depends(require_permission("inquiries:read")), db: Session = Depends(get_db)):
    q = db.query(Inquiry)
    if status:
        if status not in INQUIRY_STATUSES: raise HTTPException(422, "Invalid status")
        q = q.filter(Inquiry.status == status)
    if search: q = q.filter(Inquiry.name.ilike(f"%{search}%") | Inquiry.email.ilike(f"%{search}%") | Inquiry.company.ilike(f"%{search}%"))
    return {"items": [inquiry_out(i) for i in q.order_by(Inquiry.created_at.desc()).offset(offset).limit(limit).all()],
            "total": q.count(), "offset": offset, "limit": limit}


@router.get("/inquiries/export")
def export_inquiries(actor: User = Depends(require_permission("inquiries:read")), db: Session = Depends(get_db)):
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(["id", "date_utc", "name", "email", "company", "priority", "status", "challenge", "source_page"])
    rows = db.query(Inquiry).order_by(Inquiry.created_at.desc()).limit(5000).all()
    def safe(x):
        s = str(x or "")
        return "'" + s if s.startswith(("=", "+", "-", "@", "\t", "\r")) else s
    for i in rows:
        answers = json_out(i.answers_json, {})
        writer.writerow([safe(i.id), iso(i.created_at), safe(i.name), safe(i.email), safe(i.company),
                         safe(i.priority), safe(i.status), safe(answers.get("challenge", "")), safe(i.source_page)])
    audit(db, "inquiries.exported", actor=actor.id, target_type="inquiry", count=len(rows))
    db.commit()
    return StreamingResponse(iter([stream.getvalue()]), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": "attachment; filename=auvorent-inquiries.csv"})


@router.get("/inquiries/assignees")
def inquiry_assignees(actor: User = Depends(require_permission("inquiries:read")), db: Session = Depends(get_db)):
    users = db.query(User).filter(User.is_active.is_(True)).order_by(User.full_name).all()
    return {"items": [{"id": u.id, "full_name": u.full_name, "role": u.role} for u in users]}


@router.get("/inquiries/{inquiry_id}")
def get_inquiry(inquiry_id: str, actor: User = Depends(require_permission("inquiries:read")), db: Session = Depends(get_db)):
    i = db.get(Inquiry, inquiry_id)
    if not i: raise HTTPException(404, "Inquiry not found")
    notes = db.query(InquiryNote).filter_by(inquiry_id=i.id).order_by(InquiryNote.created_at.desc()).all()
    return {"inquiry": inquiry_out(i, True), "notes": [
        {"id": n.id, "text": n.text, "author_id": n.author_id, "created_at": iso(n.created_at)} for n in notes]}


@router.patch("/inquiries/{inquiry_id}", dependencies=[Depends(require_csrf)])
def patch_inquiry(inquiry_id: str, payload: InquiryPatch, actor: User = Depends(require_permission("inquiries:read")), db: Session = Depends(get_db)):
    i = db.get(Inquiry, inquiry_id)
    if not i: raise HTTPException(404, "Inquiry not found")
    values = payload.model_dump(exclude_unset=True)
    if "assigned_user_id" in values and values["assigned_user_id"] is not None:
        target = db.get(User, values["assigned_user_id"])
        if not target or not target.is_active: raise HTTPException(422, "Assignee must be an active CMS user")
    for k, v in values.items(): setattr(i, k, v)
    audit(db, "inquiry.updated", actor=actor.id, target_type="inquiry", target_id=i.id, fields=list(values))
    db.commit()
    return {"inquiry": inquiry_out(i, True)}


@router.post("/inquiries/{inquiry_id}/notes", dependencies=[Depends(require_csrf)], status_code=201)
def add_note(inquiry_id: str, payload: NoteCreate, actor: User = Depends(require_permission("inquiries:read")), db: Session = Depends(get_db)):
    i = db.get(Inquiry, inquiry_id)
    if not i: raise HTTPException(404, "Inquiry not found")
    note = InquiryNote(id=str(uuid.uuid4()), inquiry_id=i.id, author_id=actor.id, text=payload.text)
    db.add(note)
    audit(db, "inquiry.note_added", actor=actor.id, target_type="inquiry", target_id=i.id)
    db.commit()
    return {"note": {"id": note.id, "text": note.text, "author_id": actor.id, "created_at": iso(note.created_at)}}


@router.post("/inquiries/{inquiry_id}/resend", dependencies=[Depends(require_csrf)])
def resend_notification(inquiry_id: str, request: Request, actor: User = Depends(require_permission("settings:manage")), db: Session = Depends(get_db)):
    i = db.get(Inquiry, inquiry_id)
    if not i: raise HTTPException(404, "Inquiry not found")
    if i.notification_status == "sent": raise HTTPException(409, "Notification already sent")
    f = db.get(FormDefinition, i.form_id)
    if not f: raise HTTPException(409, "Associated form unavailable")
    notify(request, db, i, f)
    audit(db, "inquiry.notification_retried", actor=actor.id, target_type="inquiry", target_id=i.id, status=i.notification_status)
    db.commit()
    return {"notification_status": i.notification_status, "attempts": i.notification_attempts}


@router.get("/assessments")
def list_assessments(actor: User = Depends(require_permission("content:read")), db: Session = Depends(get_db)):
    return {"items": [assessment_out(a) for a in db.query(AssessmentDefinition).order_by(AssessmentDefinition.title).all()]}


@router.post("/assessments", status_code=201, dependencies=[Depends(require_csrf)])
def create_assessment(payload: AssessmentCreate, actor: User = Depends(require_permission("content:edit")), db: Session = Depends(get_db)):
    if db.query(AssessmentDefinition).filter_by(slug=payload.slug).first(): raise HTTPException(409, "Assessment slug exists")
    a = AssessmentDefinition(id=str(uuid.uuid4()), **{
        k: v for k, v in payload.model_dump().items() if k not in {"questions", "results"}},
        questions_json=json.dumps([q.model_dump() for q in payload.questions]),
        results_json=json.dumps({key: value.model_dump() for key, value in payload.results.items()}))
    db.add(a); audit(db, "assessment.created", actor=actor.id, target_type="assessment", target_id=a.id)
    db.commit()
    return {"assessment": assessment_out(a)}


@router.get("/assessments/{assessment_id}")
def get_assessment(assessment_id: str, actor: User = Depends(require_permission("content:read")), db: Session = Depends(get_db)):
    a = db.get(AssessmentDefinition, assessment_id)
    if not a: raise HTTPException(404, "Assessment not found")
    return {"assessment": assessment_out(a)}


@router.patch("/assessments/{assessment_id}", dependencies=[Depends(require_csrf)])
def patch_assessment(assessment_id: str, payload: AssessmentPatch, actor: User = Depends(require_permission("content:edit")), db: Session = Depends(get_db)):
    a = db.get(AssessmentDefinition, assessment_id)
    if not a: raise HTTPException(404, "Assessment not found")
    values = payload.model_dump(exclude_unset=True)
    combined = assessment_out(a)
    combined.update(values)
    # Validate the entire resulting assessment after edits; avoid dangling result rules.
    try:
        AssessmentCreate.model_validate({k: v for k, v in combined.items() if k in AssessmentCreate.model_fields})
    except ValidationError as exc:
        raise HTTPException(422, "Assessment has invalid or disconnected answer rules") from exc
    revision(db, "assessment", a.id, assessment_out(a), actor)
    for k, v in values.items():
        if v is None: continue
        if k == "questions": a.questions_json = json.dumps(v)
        elif k == "results": a.results_json = json.dumps(v)
        else: setattr(a, k, v)
    audit(db, "assessment.updated", actor=actor.id, target_type="assessment", target_id=a.id, fields=list(values))
    db.commit()
    return {"assessment": assessment_out(a)}


@router.get("/public/assessments/{slug}")
def public_assessment(slug: str, db: Session = Depends(get_db)):
    a = db.query(AssessmentDefinition).filter_by(slug=slug, is_active=True).first()
    if not a: raise HTTPException(404, "Assessment unavailable")
    # Omit rules to avoid treating client-controlled data as authoritative.
    public = assessment_out(a)
    public.pop("results", None)
    return {k: v for k, v in public.items() if k not in {"id", "updated_at", "is_active"}}


@router.post("/public/assessments/{slug}/evaluate")
def evaluate_assessment(slug: str, payload: AssessmentAnswers, db: Session = Depends(get_db)):
    a = db.query(AssessmentDefinition).filter_by(slug=slug, is_active=True).first()
    if not a: raise HTTPException(404, "Assessment unavailable")
    questions = json_out(a.questions_json, [])
    known = {q["id"]: q for q in questions}
    if set(payload.answers) - set(known): raise HTTPException(422, "Unknown assessment question")
    rules = json_out(a.results_json, {})
    selected = []
    for q in questions:
        answer = payload.answers.get(q["id"])
        if not answer:
            if q["required"]: raise HTTPException(422, f"{q['id']}: required")
            continue
        if answer not in {o["id"] for o in q["options"]}:
            raise HTTPException(422, f"{q['id']}: invalid option")
        rule = rules.get(f"{q['id']}.{answer}")
        if rule and rule not in selected:
            selected.append(rule)
    return {"title": "Areas for further investigation", "recommendations": selected[:5],
            "disclaimer": a.disclaimer, "cta_label": a.cta_label, "cta_url": a.cta_url,
            "note": "These suggestions are based only on your responses; no root cause has been verified."}

@router.get("/leads/summary")
def lead_summary(actor: User = Depends(require_permission("inquiries:read")), db: Session = Depends(get_db)):
    return {
        "total": db.query(Inquiry).count(),
        "new": db.query(Inquiry).filter(Inquiry.status == "new").count(),
        "sent": db.query(Inquiry).filter(Inquiry.notification_status == "sent").count(),
        "active_forms": db.query(FormDefinition).filter(FormDefinition.is_active.is_(True)).count(),
    }


@router.get("/leads/email-health")
def lead_email_health(request: Request, actor: User = Depends(require_permission("settings:manage"))):
    config = request.app.state.settings
    return {"configured": bool(config.smtp_host and config.mail_from),
            "method": "smtp", "sender_configured": bool(config.mail_from),
            "smtp_host_configured": bool(config.smtp_host)}



@router.delete("/inquiries/{inquiry_id}", dependencies=[Depends(require_csrf)])
def delete_inquiry(inquiry_id: str, actor: User = Depends(require_permission("settings:manage")), db: Session = Depends(get_db)):
    """Privacy/retention deletion. Exports must be secured and deletion is audited without PII."""
    i = db.get(Inquiry, inquiry_id)
    if not i: raise HTTPException(404, "Inquiry not found")
    db.query(InquiryNote).filter_by(inquiry_id=i.id).delete()
    audit(db, "inquiry.deleted", actor=actor.id, target_type="inquiry", target_id=i.id)
    db.delete(i)
    db.commit()
    return {"status": "deleted"}
