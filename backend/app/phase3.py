"""Phase 3 — collection, media and asset-management endpoints.

All data remains a CMS draft until the Phase 5 publish pipeline exists.
Media is served only behind a CMS session; no public URLs are exposed.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import uuid
from pathlib import Path

from defusedxml import ElementTree as SafeET
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .models import (CollectionEntry, CollectionRelationship, ContentRevision, MediaAsset,
                     MediaUsage, PageSection, User)
from .security import audit, get_db, require_csrf, require_permission

router = APIRouter(prefix="/api/v1", tags=["Collections, Media & Assets"])
KINDS = {"service", "industry", "insight", "author", "case_study", "team_member"}
ALIASES = {"services":"service", "industries":"industry", "insights":"insight",
           "authors":"author", "case-studies":"case_study", "team-members":"team_member"}
STATUSES = {"draft", "unpublished", "archived"}
SLOTS = {"hero", "icon", "illustration", "image"}
RELATIONS = {"related", "author", "featured", "supports", "relevant_to"}
MAX_UPLOAD = 10 * 1024 * 1024
MAX_SVG = 200 * 1024
PALETTE = {"#102638", "#18765f", "#75d4ae", "#f7f7f3", "#344b5c", "#e5ebe8",
           "#ffffff", "#fff", "#000000", "none", "currentcolor", "transparent"}
SVG_TAGS = {"svg", "g", "path", "circle", "rect", "ellipse", "line", "polyline", "polygon", "title", "desc"}
SVG_ATTRS = {"xmlns", "viewBox", "width", "height", "d", "fill", "stroke", "stroke-width",
             "stroke-linecap", "stroke-linejoin", "fill-rule", "clip-rule", "cx", "cy", "r", "rx", "ry",
             "x", "y", "x1", "y1", "x2", "y2", "points", "opacity", "stroke-opacity", "fill-opacity",
             "transform", "role", "aria-label"}
IMAGE_TYPES = {"image/jpeg":".jpg", "image/png":".png", "image/webp":".webp"}
EXT_MIME = {".jpg":"image/jpeg", ".jpeg":"image/jpeg", ".png":"image/png", ".webp":"image/webp",
            ".svg":"image/svg+xml", ".pdf":"application/pdf"}

class CollectionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=2, max_length=200)
    slug: str = Field(min_length=2, max_length=180, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    summary: str = Field(default="", max_length=1600)
    body_markdown: str = Field(default="", max_length=40000)
    content: dict = Field(default_factory=dict)
    status: str = "draft"
    sort_order: int = Field(default=0, ge=0, le=100000)
    is_featured: bool = False
    hero_media_id: str | None = None
    icon_media_id: str | None = None
    seo_title: str = Field(default="", max_length=180)
    meta_description: str = Field(default="", max_length=320)

    @field_validator("status")
    @classmethod
    def check_status(cls, value: str) -> str:
        if value not in STATUSES:
            raise ValueError("Publishing is enabled in Phase 5; save content as a CMS draft or approval state")
        return value

    @field_validator("title", "summary", "body_markdown", "seo_title", "meta_description")
    @classmethod
    def no_inline_html(cls, value: str) -> str:
        value = value.strip()
        if re.search(r"<\s*[/!]?[a-z]", value, re.I) or re.search(r"\b(?:javascript|vbscript|data)\s*:", value, re.I):
            raise ValueError("HTML and JavaScript are not permitted; use plain text or Markdown")
        return value

class CollectionPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, min_length=2, max_length=200)
    slug: str | None = Field(default=None, min_length=2, max_length=180, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    summary: str | None = Field(default=None, max_length=1600)
    body_markdown: str | None = Field(default=None, max_length=40000)
    content: dict | None = None
    status: str | None = None
    sort_order: int | None = Field(default=None, ge=0, le=100000)
    is_featured: bool | None = None
    hero_media_id: str | None = None
    icon_media_id: str | None = None
    seo_title: str | None = Field(default=None, max_length=180)
    meta_description: str | None = Field(default=None, max_length=320)

    @field_validator("status")
    @classmethod
    def check_status(cls, value: str | None) -> str | None:
        if value is not None and value not in STATUSES:
            raise ValueError("Publishing is enabled in Phase 5")
        return value

    @field_validator("title", "summary", "body_markdown", "seo_title", "meta_description")
    @classmethod
    def no_inline_html(cls, value: str | None) -> str | None:
        return CollectionCreate.no_inline_html(value) if value is not None else value

class LinkInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_id: str
    relation: str = "related"

class MediaPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    alt_text: str | None = Field(default=None, max_length=300)
    caption: str | None = Field(default=None, max_length=500)
    source_notes: str | None = Field(default=None, max_length=500)
    decorative: bool | None = None

    @field_validator("alt_text", "caption", "source_notes")
    @classmethod
    def plain_text_only(cls,value: str | None) -> str | None:
        if value is not None and (re.search(r"<\s*[/!]?[a-z]", value, re.I) or re.search(r"\b(?:javascript|vbscript|data)\s*:",value,re.I)):
            raise ValueError("HTML and executable URLs are not allowed in asset metadata")
        return value

class UsageInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    owner_type: str
    owner_id: str
    slot: str


def _json(data):
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))

def _safe_content(data: dict) -> str:
    raw = _json(data)
    if len(raw.encode("utf-8")) > 64 * 1024:
        raise HTTPException(422, "Structured content exceeds 64 KB")
    def walk(value):
        if isinstance(value, str) and (re.search(r"<\s*[/!]?[a-z]", value, re.I) or re.search(r"\b(?:javascript|vbscript|data)\s*:",value,re.I)):
            raise HTTPException(422, "Embedded HTML and JavaScript are not permitted in content fields")
        if isinstance(value, list):
            for v in value: walk(v)
        if isinstance(value, dict):
            for k,v in value.items():
                if len(k) > 120: raise HTTPException(422, "Content key too long")
                walk(v)
    walk(data)
    return raw

def _kind(kind):
    if kind not in KINDS: raise HTTPException(404, "Collection not found")
    return kind

def _entry(db, kind, entry_id):
    item = db.get(CollectionEntry, entry_id)
    if not item or item.kind != kind: raise HTTPException(404, "Content record not found")
    return item

def _relations(db, entry_id):
    rows = db.query(CollectionRelationship).filter(CollectionRelationship.source_id==entry_id).order_by(CollectionRelationship.created_at).all()
    return [{"id":r.id,"target_id":r.target_id,"target_kind":db.get(CollectionEntry,r.target_id).kind if db.get(CollectionEntry,r.target_id) else None,"relation":r.relation} for r in rows]

def _collection_out(item, db, full=False):
    result={"id":item.id,"kind":item.kind,"title":item.title,"slug":item.slug,"summary":item.summary,
            "status":item.status,"sort_order":item.sort_order,"is_featured":item.is_featured,
            "hero_media_id":item.hero_media_id,"icon_media_id":item.icon_media_id,
            "seo_title":item.seo_title,"meta_description":item.meta_description,
            "created_at":item.created_at.isoformat()+"Z","updated_at":item.updated_at.isoformat()+"Z"}
    if full:
        result["body_markdown"]=item.body_markdown
        result["content"]=json.loads(item.content_json or "{}")
        result["relationships"]=_relations(db,item.id)
    return result

def _check_media(db: Session, media_id: str | None, slot: str):
    if not media_id: return
    asset=db.get(MediaAsset, media_id)
    if not asset: raise HTTPException(422, f"{slot} media was not found")
    if slot == "hero" and asset.kind not in {"image","brand"}:
        raise HTTPException(422, "Hero media must be an image")
    if slot == "icon" and asset.kind != "icon":
        raise HTTPException(422, "Icon media must be a sanitized custom icon")

def _set_usage(db, media_id, owner_type, owner_id, slot):
    db.query(MediaUsage).filter(MediaUsage.owner_type==owner_type, MediaUsage.owner_id==owner_id, MediaUsage.slot==slot).delete()
    if media_id:
        db.add(MediaUsage(id=str(uuid.uuid4()), media_id=media_id,owner_type=owner_type,owner_id=owner_id,slot=slot))

def _revision(db, item, actor):
    db.add(ContentRevision(entity_type=item.kind, entity_id=item.id, snapshot_json=_json(_collection_out(item,db,True)), actor_user_id=actor.id))

def list_collection(kind, search, status, limit, offset, actor, db):
    _kind(kind)
    q=db.query(CollectionEntry).filter(CollectionEntry.kind==kind)
    if search: q=q.filter(or_(CollectionEntry.title.ilike(f"%{search}%"),CollectionEntry.summary.ilike(f"%{search}%"),CollectionEntry.slug.ilike(f"%{search}%")))
    if status: q=q.filter(CollectionEntry.status==status)
    return {"items":[_collection_out(r,db) for r in q.order_by(CollectionEntry.sort_order,CollectionEntry.title).offset(offset).limit(limit).all()],
            "total":q.count(),"limit":limit,"offset":offset}

def create_collection(kind, payload, actor, db):
    _kind(kind)
    _check_media(db,payload.hero_media_id,"hero")
    _check_media(db,payload.icon_media_id,"icon")
    data=payload.model_dump()
    data["content_json"]=_safe_content(data.pop("content"))
    item=CollectionEntry(id=str(uuid.uuid4()),kind=kind,**data)
    db.add(item)
    try:
        db.flush()
        _set_usage(db,item.hero_media_id,"collection",item.id,"hero")
        _set_usage(db,item.icon_media_id,"collection",item.id,"icon")
        audit(db,"collection.created",actor=actor.id,target_type=kind,target_id=item.id,slug=item.slug)
        db.commit()
    except IntegrityError: db.rollback(); raise HTTPException(409,"A collection entry with this slug already exists")
    return {"item":_collection_out(item,db,True)}

def update_collection(kind, entry_id, payload, actor, db):
    item=_entry(db,kind,entry_id)
    changes=payload.model_dump(exclude_unset=True)
    _check_media(db,changes.get("hero_media_id",item.hero_media_id),"hero")
    _check_media(db,changes.get("icon_media_id",item.icon_media_id),"icon")
    _revision(db,item,actor)
    from .phase5 import reset_approval
    reset_approval(db,kind,item.id)
    if 'content' in changes:
        item.content_json=_safe_content(changes.pop("content"))
    for field,value in changes.items(): setattr(item,field,value)
    if "hero_media_id" in changes: _set_usage(db,item.hero_media_id,"collection",item.id,"hero")
    if "icon_media_id" in changes: _set_usage(db,item.icon_media_id,"collection",item.id,"icon")
    audit(db,"collection.updated",actor=actor.id,target_type=kind,target_id=item.id,fields=list(payload.model_dump(exclude_unset=True)))
    try: db.commit()
    except IntegrityError: db.rollback(); raise HTTPException(409,"A collection entry with this slug already exists")
    return {"item":_collection_out(item,db,True)}

def delete_collection(kind, entry_id, actor, db):
    item=_entry(db,kind,entry_id)
    if item.status in {"approved","in_review"}:
        raise HTTPException(409,"Move approved or in-review content to draft before deleting")
    referenced=db.query(CollectionRelationship).filter(CollectionRelationship.target_id==item.id).count()
    if referenced: raise HTTPException(409,"Remove other content relationships first")
    db.query(CollectionRelationship).filter(CollectionRelationship.source_id==item.id).delete()
    db.query(MediaUsage).filter(MediaUsage.owner_type=="collection",MediaUsage.owner_id==item.id).delete()
    audit(db,"collection.deleted",actor=actor.id,target_type=kind,target_id=item.id,slug=item.slug)
    db.delete(item);db.commit()
    return {"status":"deleted"}

@router.get("/collections/{kind}")
def list_collections(kind:str,search:str=Query("",max_length=120),status:str=Query("",max_length=24),limit:int=Query(60,ge=1,le=200),offset:int=Query(0,ge=0),actor:User=Depends(require_permission("content:read")),db:Session=Depends(get_db)):
    return list_collection(kind,search,status,limit,offset,actor,db)

@router.post("/collections/{kind}",status_code=201,dependencies=[Depends(require_csrf)])
def new_collection(kind:str,payload:CollectionCreate,actor:User=Depends(require_permission("content:edit")),db:Session=Depends(get_db)):
    return create_collection(kind,payload,actor,db)

@router.get("/collections/{kind}/{entry_id}")
def get_collection(kind:str,entry_id:str,actor:User=Depends(require_permission("content:read")),db:Session=Depends(get_db)):
    return {"item":_collection_out(_entry(db,_kind(kind),entry_id),db,True)}

@router.patch("/collections/{kind}/{entry_id}",dependencies=[Depends(require_csrf)])
def patch_collection(kind:str,entry_id:str,payload:CollectionPatch,actor:User=Depends(require_permission("content:edit")),db:Session=Depends(get_db)):
    return update_collection(kind,entry_id,payload,actor,db)

@router.delete("/collections/{kind}/{entry_id}",dependencies=[Depends(require_csrf)])
def remove_collection(kind:str,entry_id:str,actor:User=Depends(require_permission("content:edit")),db:Session=Depends(get_db)):
    return delete_collection(kind,entry_id,actor,db)

@router.post("/collections/{kind}/{entry_id}/relationships",status_code=201,dependencies=[Depends(require_csrf)])
def link_collection(kind:str,entry_id:str,payload:LinkInput,actor:User=Depends(require_permission("content:edit")),db:Session=Depends(get_db)):
    source=_entry(db,_kind(kind),entry_id)
    target=db.get(CollectionEntry,payload.target_id)
    if not target or target.id==source.id:raise HTTPException(422,"Choose a different existing content record")
    if payload.relation not in RELATIONS:raise HTTPException(422,"Unsupported relationship")
    if payload.relation=="author" and not (source.kind=="insight" and target.kind=="author"):
        raise HTTPException(422,"Author relationships connect an insight to an author profile")
    existing=db.query(CollectionRelationship).filter_by(source_id=source.id,target_id=target.id,relation=payload.relation).first()
    if existing:raise HTTPException(409,"Relationship already exists")
    r=CollectionRelationship(id=str(uuid.uuid4()),source_id=source.id,target_id=target.id,relation=payload.relation)
    db.add(r);audit(db,"collection.linked",actor=actor.id,target_type=kind,target_id=entry_id,related_id=target.id)
    db.commit();return {"relationship":{"id":r.id,"target_id":target.id,"target_kind":target.kind,"relation":r.relation}}

@router.delete("/collections/{kind}/{entry_id}/relationships/{relationship_id}",dependencies=[Depends(require_csrf)])
def unlink_collection(kind:str,entry_id:str,relationship_id:str,actor:User=Depends(require_permission("content:edit")),db:Session=Depends(get_db)):
    _entry(db,_kind(kind),entry_id)
    r=db.get(CollectionRelationship,relationship_id)
    if not r or r.source_id!=entry_id:raise HTTPException(404,"Relationship not found")
    db.delete(r);audit(db,"collection.unlinked",actor=actor.id,target_type=kind,target_id=entry_id,related_id=r.target_id)
    db.commit();return {"status":"deleted"}

# Also expose the documented service/industry/insight URLs rather than making integrations rely on a generic route.
for _segment, _target in ALIASES.items():
    def _aliases(kind, segment):
        def collection_list(search:str=Query("",max_length=120),status:str=Query("",max_length=24),limit:int=Query(60,ge=1,le=200),offset:int=Query(0,ge=0),actor:User=Depends(require_permission("content:read")),db:Session=Depends(get_db)):
            return list_collection(kind,search,status,limit,offset,actor,db)
        def collection_new(payload:CollectionCreate,actor:User=Depends(require_permission("content:edit")),db:Session=Depends(get_db)):
            return create_collection(kind,payload,actor,db)
        def collection_get(entry_id:str,actor:User=Depends(require_permission("content:read")),db:Session=Depends(get_db)):
            return {"item":_collection_out(_entry(db,kind,entry_id),db,True)}
        def collection_patch(entry_id:str,payload:CollectionPatch,actor:User=Depends(require_permission("content:edit")),db:Session=Depends(get_db)):
            return update_collection(kind,entry_id,payload,actor,db)
        def collection_remove(entry_id:str,actor:User=Depends(require_permission("content:edit")),db:Session=Depends(get_db)):
            return delete_collection(kind,entry_id,actor,db)
        router.add_api_route('/'+segment,collection_list,methods=['GET'],tags=['Collections'],name=f'List {segment}')
        router.add_api_route('/'+segment,collection_new,methods=['POST'],status_code=201,dependencies=[Depends(require_csrf)],tags=['Collections'],name=f'Create {segment}')
        router.add_api_route('/'+segment+'/{entry_id}',collection_get,methods=['GET'],tags=['Collections'],name=f'Get {segment}')
        router.add_api_route('/'+segment+'/{entry_id}',collection_patch,methods=['PATCH'],dependencies=[Depends(require_csrf)],tags=['Collections'],name=f'Update {segment}')
        router.add_api_route('/'+segment+'/{entry_id}',collection_remove,methods=['DELETE'],dependencies=[Depends(require_csrf)],tags=['Collections'],name=f'Delete {segment}')
    _aliases(_target,_segment)

# ------------------ secure media library ------------------

def _media_root(request:Request):
    root=request.app.state.media_root
    root.mkdir(parents=True,exist_ok=True)
    return root

def _media_out(asset,db):
    return {"id":asset.id,"original_name":asset.original_name,"mime_type":asset.mime_type,"kind":asset.kind,
            "icon_style":asset.icon_style,"byte_size":asset.byte_size,"width":asset.width,"height":asset.height,
            "alt_text":asset.alt_text,"caption":asset.caption,"source_notes":asset.source_notes,"decorative":asset.decorative,
            "usage_count":db.query(MediaUsage).filter(MediaUsage.media_id==asset.id).count(),
            "preview_url":f"/api/v1/media/{asset.id}/file" if asset.kind!="document" else None,
            "thumbnail_url":f"/api/v1/media/{asset.id}/thumbnail" if asset.kind in {"image","brand"} and asset.mime_type in IMAGE_TYPES else None,
            "created_at":asset.created_at.isoformat()+"Z","updated_at":asset.updated_at.isoformat()+"Z"}

def _svg_local_name(name:str):
    return name.split("}")[-1]

def _sanitize_icon(raw:bytes)->bytes:
    if len(raw)>MAX_SVG: raise HTTPException(413,"SVG icon is too large")
    try: root=SafeET.fromstring(raw)
    except Exception: raise HTTPException(422,"Invalid or unsafe SVG document")
    if _svg_local_name(root.tag)!="svg": raise HTTPException(422,"SVG root element required")
    if len(list(root.iter()))>120:raise HTTPException(422,"SVG is too complex")
    for node in root.iter():
        if _svg_local_name(node.tag) not in SVG_TAGS:raise HTTPException(422,"SVG contains prohibited elements")
        if node.tail and node.tail.strip():raise HTTPException(422,"SVG text outside title/description is not allowed")
        if node.text and node.text.strip() and _svg_local_name(node.tag) not in {"title","desc"}:
            raise HTTPException(422,"SVG text is not allowed")
        for attr,val in node.attrib.items():
            name=_svg_local_name(attr)
            if name not in SVG_ATTRS:raise HTTPException(422,f"SVG attribute '{name}' is not allowed")
            if name in {"fill","stroke"} and val.strip().lower() not in PALETTE:
                raise HTTPException(422,"Icon colors must use the approved Auvorent palette")
            if "url(" in val.lower() or "javascript:" in val.lower() or len(val)>16000:
                raise HTTPException(422,"External references or oversized SVG attributes prohibited")
            if name in {"width","height"} and not re.fullmatch(r"\d+(?:\.\d+)?(?:px)?",val.strip()):
                raise HTTPException(422,"Icon dimensions must be fixed numeric values")
    return SafeET.tostring(root,encoding="utf-8",xml_declaration=False)

def _inspect_bytes(raw:bytes, ext:str, kind:str):
    if kind=="icon":
        if ext!=".svg":raise HTTPException(422,"Custom icons must be SVG")
        return _sanitize_icon(raw),"image/svg+xml",None,None
    if kind=="document":
        if ext!=".pdf" or not raw.startswith(b"%PDF-"):
            raise HTTPException(422,"Downloadable documents must be valid PDF files")
        return raw,"application/pdf",None,None
    if kind in {"image","brand"}:
        if ext not in IMAGE_TYPES.values():raise HTTPException(422,"Upload JPG, PNG or WebP images")
        try:
            with Image.open(io.BytesIO(raw)) as image:
                image.verify()
            with Image.open(io.BytesIO(raw)) as image:
                width,height=image.size
                mime=Image.MIME.get(image.format)
                if width<32 or height<32 or width>6000 or height>6000 or width*height>24_000_000:
                    raise HTTPException(422,"Image dimensions must be 32–6000px, max 24 megapixels")
        except (UnidentifiedImageError, Image.DecompressionBombError, Image.DecompressionBombWarning, OSError):
            raise HTTPException(422,"Image file could not be validated")
        if mime!=EXT_MIME.get(ext):raise HTTPException(422,"File extension does not match image content")
        return raw,mime,width,height
    raise HTTPException(422,"Unsupported media kind")

def _thumbnail(raw:bytes,root:Path,storage_name:str,mime:str):
    if mime not in IMAGE_TYPES:return
    try:
        with Image.open(io.BytesIO(raw)) as img:
            img=ImageOps.exif_transpose(img)
            img.thumbnail((600,450))
            if img.mode not in {"RGB","RGBA"}:img=img.convert("RGB")
            img.save(root/(storage_name+".thumb.webp"),"WEBP",quality=82,method=5)
    except OSError: pass  # Upload has already passed image verification.

def _safe_filename(name):
    name=Path(name or "upload").name.strip()
    if any(ord(c)<32 for c in name):raise HTTPException(422,"Invalid filename")
    return name[:240]

async def _save_uploaded(file,kind,alt_text,caption,source_notes,decorative,icon_style,request,db,actor,existing=None):
    if kind not in {"image","icon","document","brand"}:raise HTTPException(422,"Unsupported asset category")
    if kind=="icon" and icon_style not in {"line","filled"}:raise HTTPException(422,"Select a line or filled icon style")
    if kind!="icon":icon_style=None
    if kind in {"image","brand"} and not decorative and not alt_text.strip():
        raise HTTPException(422,"Alt text is required for informative images")
    filename=_safe_filename(file.filename)
    ext=Path(filename).suffix.lower()
    if ext not in EXT_MIME:raise HTTPException(422,"File type is not supported")
    raw=await file.read(MAX_UPLOAD+1)
    if len(raw)>MAX_UPLOAD:raise HTTPException(413,"Maximum upload size is 10 MB")
    if not raw:raise HTTPException(422,"File is empty")
    raw,mime,width,height=_inspect_bytes(raw,ext,kind)
    # User-provided Content-Type may be omitted; if set, disallow inconsistent values.
    if file.content_type and file.content_type not in {mime,"application/octet-stream"}:
        raise HTTPException(422,"Uploaded Content-Type does not match the file")
    root=_media_root(request)
    uid=str(uuid.uuid4())
    name=uid+(".svg" if kind=="icon" else ext)
    temp=root/(name+".upload")
    temp.write_bytes(raw)
    os.replace(temp,root/name)
    _thumbnail(raw,root,name,mime)
    if existing:
        before=_media_out(existing,db)
        old_name=existing.storage_name
        existing.original_name=filename
        existing.storage_name=name
        existing.sha256=hashlib.sha256(raw).hexdigest()
        existing.mime_type=mime
        existing.byte_size=len(raw)
        existing.width=width;existing.height=height
        existing.kind=kind;existing.icon_style=icon_style
        existing.alt_text=alt_text.strip();existing.caption=caption.strip();existing.source_notes=source_notes.strip()
        existing.decorative=decorative
        db.add(ContentRevision(entity_type="media",entity_id=existing.id,snapshot_json=_json(before),actor_user_id=actor.id))
        audit(db,"media.replaced",actor=actor.id,target_type="media",target_id=existing.id,previous_checksum=before.get("sha256"),file_type=mime)
        try:db.commit()
        except Exception:
            db.rollback();(root/name).unlink(missing_ok=True);(root/(name+".thumb.webp")).unlink(missing_ok=True);raise
        (root/old_name).unlink(missing_ok=True)
        (root/(old_name+".thumb.webp")).unlink(missing_ok=True)
        return existing
    asset=MediaAsset(id=str(uuid.uuid4()),original_name=filename,storage_name=name,sha256=hashlib.sha256(raw).hexdigest(),
                     mime_type=mime,kind=kind,icon_style=icon_style,byte_size=len(raw),width=width,height=height,
                     alt_text=alt_text.strip(),caption=caption.strip(),source_notes=source_notes.strip(),decorative=decorative,created_by=actor.id)
    db.add(asset);audit(db,"media.uploaded",actor=actor.id,target_type="media",target_id=asset.id,kind=kind,size=len(raw))
    try:db.commit()
    except Exception:
        db.rollback();(root/name).unlink(missing_ok=True);(root/(name+".thumb.webp")).unlink(missing_ok=True);raise
    return asset

@router.get("/media")
def list_media(search:str=Query("",max_length=120),kind:str=Query("",max_length=24),limit:int=Query(48,ge=1,le=150),offset:int=Query(0,ge=0),actor:User=Depends(require_permission("media:read")),db:Session=Depends(get_db)):
    q=db.query(MediaAsset)
    if search:q=q.filter(or_(MediaAsset.original_name.ilike(f"%{search}%"),MediaAsset.alt_text.ilike(f"%{search}%")))
    if kind:q=q.filter(MediaAsset.kind==kind)
    return {"items":[_media_out(a,db) for a in q.order_by(MediaAsset.created_at.desc()).offset(offset).limit(limit).all()],"total":q.count(),"limit":limit,"offset":offset}

@router.post("/media",status_code=201,dependencies=[Depends(require_csrf)])
async def upload_media(request:Request,file:UploadFile=File(...),kind:str=Form("image"),alt_text:str=Form(""),caption:str=Form(""),source_notes:str=Form(""),decorative:bool=Form(False),icon_style:str=Form("line"),actor:User=Depends(require_permission("media:manage")),db:Session=Depends(get_db)):
    if len(alt_text)>300 or len(caption)>500 or len(source_notes)>500:raise HTTPException(422,"Media metadata too long")
    for value in (alt_text, caption, source_notes):
        if re.search(r"<\s*[/!]?[a-z]",value,re.I) or re.search(r"\b(?:javascript|vbscript|data)\s*:",value,re.I):
            raise HTTPException(422,"HTML and executable URLs are not permitted in media metadata")
    asset=await _save_uploaded(file,kind,alt_text,caption,source_notes,decorative,icon_style,request,db,actor)
    return {"media":_media_out(asset,db)}

@router.get("/media/{media_id}")
def get_media(media_id:str,actor:User=Depends(require_permission("media:read")),db:Session=Depends(get_db)):
    asset=db.get(MediaAsset,media_id)
    if not asset:raise HTTPException(404,"Media not found")
    return {"media":_media_out(asset,db)}

@router.get("/media/{media_id}/file",include_in_schema=True)
def get_media_file(media_id:str,request:Request,actor:User=Depends(require_permission("media:read")),db:Session=Depends(get_db)):
    asset=db.get(MediaAsset,media_id)
    if not asset:raise HTTPException(404,"Media not found")
    path=_media_root(request)/asset.storage_name
    if not path.is_file():raise HTTPException(404,"Asset file unavailable")
    return FileResponse(path,media_type=asset.mime_type,filename=asset.original_name,content_disposition_type="attachment" if asset.kind=="document" else "inline",headers={"X-Content-Type-Options":"nosniff","Cache-Control":"private, no-store"})

@router.get("/media/{media_id}/thumbnail")
def get_thumbnail(media_id:str,request:Request,actor:User=Depends(require_permission("media:read")),db:Session=Depends(get_db)):
    asset=db.get(MediaAsset,media_id)
    if not asset:raise HTTPException(404,"Media not found")
    path=_media_root(request)/(asset.storage_name+".thumb.webp")
    if not path.is_file():raise HTTPException(404,"Thumbnail unavailable")
    return FileResponse(path,media_type="image/webp",headers={"Cache-Control":"private, no-store"})

@router.patch("/media/{media_id}",dependencies=[Depends(require_csrf)])
def patch_media(media_id:str,payload:MediaPatch,actor:User=Depends(require_permission("media:manage")),db:Session=Depends(get_db)):
    asset=db.get(MediaAsset,media_id)
    if not asset:raise HTTPException(404,"Media not found")
    changes=payload.model_dump(exclude_unset=True)
    alt=changes.get("alt_text",asset.alt_text)
    decorative=changes.get("decorative",asset.decorative)
    if asset.kind in {"image","brand"} and not decorative and not alt.strip():raise HTTPException(422,"Alt text is required")
    db.add(ContentRevision(entity_type="media",entity_id=asset.id,snapshot_json=_json(_media_out(asset,db)),actor_user_id=actor.id))
    for field,value in changes.items():setattr(asset,field,value.strip() if isinstance(value,str) else value)
    audit(db,"media.updated",actor=actor.id,target_type="media",target_id=asset.id,fields=list(changes));db.commit()
    return {"media":_media_out(asset,db)}

@router.post("/media/{media_id}/replace",dependencies=[Depends(require_csrf)])
async def replace_media(media_id:str,request:Request,file:UploadFile=File(...),actor:User=Depends(require_permission("media:manage")),db:Session=Depends(get_db)):
    asset=db.get(MediaAsset,media_id)
    if not asset:raise HTTPException(404,"Media not found")
    replacement=await _save_uploaded(file,asset.kind,asset.alt_text,asset.caption,asset.source_notes,asset.decorative,asset.icon_style,request,db,actor,existing=asset)
    return {"media":_media_out(replacement,db)}

@router.delete("/media/{media_id}",dependencies=[Depends(require_csrf)])
def delete_media(media_id:str,request:Request,actor:User=Depends(require_permission("media:manage")),db:Session=Depends(get_db)):
    asset=db.get(MediaAsset,media_id)
    if not asset:raise HTTPException(404,"Media not found")
    if db.query(MediaUsage).filter(MediaUsage.media_id==media_id).count() or db.query(CollectionEntry).filter(or_(CollectionEntry.hero_media_id==media_id,CollectionEntry.icon_media_id==media_id)).count():
        raise HTTPException(409,"Asset is in use; remove or replace its references first")
    name=asset.storage_name
    audit(db,"media.deleted",actor=actor.id,target_type="media",target_id=asset.id,file_type=asset.mime_type)
    db.delete(asset);db.commit()
    root=_media_root(request)
    (root/name).unlink(missing_ok=True)
    (root/(name+".thumb.webp")).unlink(missing_ok=True)
    return {"status":"deleted"}

@router.get("/media/{media_id}/usages")
def media_usages(media_id:str,actor:User=Depends(require_permission("media:read")),db:Session=Depends(get_db)):
    if not db.get(MediaAsset,media_id):raise HTTPException(404,"Media not found")
    rows=db.query(MediaUsage).filter(MediaUsage.media_id==media_id).order_by(MediaUsage.created_at).all()
    return {"items":[{"id":r.id,"owner_type":r.owner_type,"owner_id":r.owner_id,"slot":r.slot} for r in rows]}

@router.post("/media/{media_id}/usages",status_code=201,dependencies=[Depends(require_csrf)])
def attach_section_media(media_id:str,payload:UsageInput,actor:User=Depends(require_permission("content:edit")),db:Session=Depends(get_db)):
    asset=db.get(MediaAsset,media_id)
    if not asset:raise HTTPException(404,"Media not found")
    if payload.owner_type!="page_section" or payload.slot not in {"illustration","image","icon"}:
        raise HTTPException(422,"Use this endpoint to link a page-section image or icon")
    section=db.get(PageSection,payload.owner_id)
    if not section:raise HTTPException(404,"Page section not found")
    if payload.slot=="icon" and asset.kind!="icon":raise HTTPException(422,"Icon slot requires a sanitized SVG")
    if payload.slot in {"image","illustration"} and asset.kind not in {"image","brand"}:
        raise HTTPException(422,"Image slot requires image media")
    db.query(MediaUsage).filter(MediaUsage.owner_type=="page_section",MediaUsage.owner_id==section.id,MediaUsage.slot==payload.slot).delete()
    usage=MediaUsage(id=str(uuid.uuid4()),media_id=asset.id,owner_type="page_section",owner_id=section.id,slot=payload.slot)
    db.add(usage)
    audit(db,"media.assigned",actor=actor.id,target_type="page_section",target_id=section.id,media_id=asset.id,slot=payload.slot)
    db.commit();return {"usage":{"id":usage.id,"media_id":asset.id,"owner_id":section.id,"slot":usage.slot}}

@router.delete("/media/{media_id}/usages/{usage_id}",dependencies=[Depends(require_csrf)])
def remove_media_usage(media_id:str,usage_id:str,actor:User=Depends(require_permission("content:edit")),db:Session=Depends(get_db)):
    usage=db.get(MediaUsage,usage_id)
    if not usage or usage.media_id!=media_id:raise HTTPException(404,"Usage not found")
    if usage.owner_type=="collection":raise HTTPException(409,"Detach collection assets using the collection editor")
    db.delete(usage);audit(db,"media.unassigned",actor=actor.id,target_type=usage.owner_type,target_id=usage.owner_id,media_id=media_id)
    db.commit();return {"status":"deleted"}
