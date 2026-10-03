"""Phase 5 — private SEO/review studio and immutable LOCAL staging publisher.

This module does not deploy to a public domain. Phase 6 connects the final V6
renderer, hosted assets, and production deployment pipeline.
"""
from __future__ import annotations

import hashlib
import html
import json
import os
import re
import secrets
import shutil
import tempfile
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy.orm import Session
from .models import (Page, PageSection, CollectionEntry, MediaAsset, NavigationItem, SiteSetting,
                     SeoRecord, RedirectRule, EditorialReview, PrivatePreview, PublishDeployment,
                     User, ContentRevision, utcnow)
from .security import audit, get_db, require_csrf, require_permission

router=APIRouter(prefix='/api/v1',tags=['SEO, Review & Publishing'])
ALLOWED_TYPES={'page','service','industry','insight','author','case_study','team_member'}
PUBLIC_COLLECTION_TYPES={'service','industry','insight'}
SCHEMAS={'WebPage','Article','Service','Organization','AboutPage','ContactPage','FAQPage'}
ROOT=Path(__file__).resolve().parents[2]
SEED=(ROOT/'seed'/'v6_page_content.json')
PUBLISH_LOCK=threading.RLock()
_PREVIEW_TOKEN_RE=re.compile(r'^[A-Za-z0-9_-]{32,128}$')
_RELEASE_ID_RE=re.compile(r'^[0-9a-f]{32}$')
_ROUTE_RE=re.compile(r'^/[A-Za-z0-9/_-]*/?$')
_PUBLIC_REPORT_KEYS={'release_id','published_count','skipped_non_public_collections','sitemap_url_count','staging_only','restored_release_id'}
_SAFE_FAILURE_PREFIXES=(
    'Nothing approved to publish',
    'Approval stale or missing for ',
    'SEO blocks ',
    'Generated HTML missing critical SEO elements',
    'Managed release contains unsupported symbolic links',
)


def json_safe(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))


def entity(db:Session, kind:str, entity_id:str):
    if kind not in ALLOWED_TYPES: raise HTTPException(422,'Unsupported content type')
    row=db.get(Page if kind=='page' else CollectionEntry,entity_id)
    if not row or (kind!='page' and row.kind!=kind): raise HTTPException(404,'Content not found')
    return row


def seo_for(db,kind,id):
    return db.query(SeoRecord).filter_by(entity_type=kind,entity_id=id).first()


def effective_seo(row,record=None):
    return {'seo_title':record.seo_title if record else row.seo_title,
            'meta_description':record.meta_description if record else row.meta_description,
            'canonical_override':record.canonical_override if record else '',
            'robots_index':record.robots_index if record else (row.is_indexable if isinstance(row,Page) else False),
            'robots_follow':record.robots_follow if record else True,
            'og_title':record.og_title if record else '',
            'og_description':record.og_description if record else '',
            'og_image_media_id':record.og_image_media_id if record else None,
            'schema_type':record.schema_type if record else ('Article' if getattr(row,'kind','')=='insight' else 'WebPage'),
            'breadcrumb_title':record.breadcrumb_title if record else ''}


def entity_payload(db,kind,id):
    row=entity(db,kind,id)
    if kind=='page':
        body={'title':row.title,'route':row.route,'slug':row.slug,'template':row.template,
              'show_in_navigation':row.show_in_navigation,'is_indexable':row.is_indexable,
              'sections':[{'key':s.section_key,'type':s.section_type,'enabled':s.is_enabled,'position':s.position,
                           'content':json.loads(s.content_json or '{}')} for s in row.sections]}
    else:
        body={'title':row.title,'slug':row.slug,'kind':row.kind,'summary':row.summary,'body':row.body_markdown,
              'content':json.loads(row.content_json or '{}'),'hero_media_id':row.hero_media_id,
              'icon_media_id':row.icon_media_id,'featured':row.is_featured}
    body['seo']=effective_seo(row,seo_for(db,kind,id))
    return body


def fingerprint(db,kind,id):
    return hashlib.sha256(json_safe(entity_payload(db,kind,id)).encode()).hexdigest()


def reset_approval(db,kind,id):
    """Called on substantive content/SEO edits so old approvals cannot be reused."""
    db.query(EditorialReview).filter(EditorialReview.entity_type==kind,EditorialReview.entity_id==id,
                                    EditorialReview.state.in_(['in_review','approved'])).update({'state':'invalidated'},synchronize_session=False)
    row=entity(db,kind,id)
    if row.status in {'in_review','approved','published'}: row.status='draft'


def canonical_base(db):
    row=db.get(SiteSetting,'seo.canonical_base')
    try: raw=json.loads(row.value_json) if row else ''
    except (json.JSONDecodeError,TypeError): raw=''
    parsed=urlparse(str(raw))
    if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.path not in ('','/'):
        raise HTTPException(422,'Set an HTTPS canonical base in Site settings before publishing')
    return parsed.scheme+'://'+parsed.netloc


def entity_route(row,kind):
    if kind=='page': return row.route
    return ('/insights/' if kind=='insight' else '/'+kind.replace('_','-')+'s/') + row.slug+'/'


def entity_issues(db,kind,id):
    row=entity(db,kind,id); meta=effective_seo(row,seo_for(db,kind,id)); problems=[]
    title=meta['seo_title'].strip(); desc=meta['meta_description'].strip()
    if not title: problems.append({'level':'error','code':'seo_title','message':'SEO title is required before an indexable publish.'})
    elif len(title)<28 or len(title)>65: problems.append({'level':'warning','code':'title_length','message':f'SEO title length is {len(title)}; review the search-result snippet.'})
    if not desc: problems.append({'level':'error','code':'meta_description','message':'Meta description is required before an indexable publish.'})
    elif len(desc)<70 or len(desc)>165: problems.append({'level':'warning','code':'description_length','message':f'Meta description length is {len(desc)}; confirm relevance and readability.'})
    canonical=meta['canonical_override']
    if canonical:
        p=urlparse(canonical)
        if p.scheme!='https' or not p.hostname or p.username or p.password or p.fragment:
            problems.append({'level':'error','code':'canonical','message':'Canonical URL must be a full HTTPS URL without credentials or fragment.'})
    if kind=='page':
        headings=[json.loads(s.content_json or '{}').get('heading','').strip() for s in row.sections if s.is_enabled]
        headings=[h for h in headings if h]
        if not headings: problems.append({'level':'error','code':'heading','message':'At least one visible section heading is required.'})
        if not row.sections: problems.append({'level':'error','code':'empty','message':'A page needs at least one section.'})
    elif not row.summary.strip() and not row.body_markdown.strip():
        problems.append({'level':'error','code':'empty','message':'Provide substantive collection content.'})
    for slot in ('og_image_media_id',):
        media_id=meta[slot]
        if media_id:
            asset=db.get(MediaAsset,media_id)
            if not asset: problems.append({'level':'error','code':'image_missing','message':'Social image does not exist.'})
            elif not asset.alt_text.strip() and not asset.decorative: problems.append({'level':'warning','code':'alt_text','message':'Social image is missing alt text.'})
    if kind!='page' and row.hero_media_id:
        asset=db.get(MediaAsset,row.hero_media_id)
        if asset and not asset.alt_text.strip() and not asset.decorative:
            problems.append({'level':'warning','code':'hero_alt','message':'Hero image needs descriptive alt text.'})
    return {'entity_type':kind,'entity_id':id,'title':row.title,'route':entity_route(row,kind),
            'index_requested':bool(meta['robots_index']), 'issues':problems,
            'errors':sum(1 for p in problems if p['level']=='error'),
            'warnings':sum(1 for p in problems if p['level']=='warning')}


class SeoPatch(BaseModel):
    model_config=ConfigDict(extra='forbid')
    seo_title:str=Field(default='',max_length=180)
    meta_description:str=Field(default='',max_length=320)
    canonical_override:str=Field(default='',max_length=512)
    robots_index:bool=False
    robots_follow:bool=True
    og_title:str=Field(default='',max_length=180)
    og_description:str=Field(default='',max_length=320)
    og_image_media_id:str|None=None
    schema_type:str='WebPage'
    breadcrumb_title:str=Field(default='',max_length=180)

    @field_validator('seo_title','meta_description','og_title','og_description','breadcrumb_title')
    @classmethod
    def plain(cls,val):
        if re.search(r'<\s*[/!]?[a-z]|javascript\s*:',val,re.I):raise ValueError('Use plain text, not HTML')
        return val.strip()
    @field_validator('canonical_override')
    @classmethod
    def canonical(cls,val):
        if val:
            p=urlparse(val)
            if p.scheme!='https' or not p.hostname or p.username or p.password or p.fragment:
                raise ValueError('Use a full HTTPS canonical URL with no credentials or fragment')
        return val
    @field_validator('schema_type')
    @classmethod
    def schema(cls,val):
        if val not in SCHEMAS:raise ValueError('Unsupported structured-data type')
        return val


class NoteInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    note:str=Field(default='',max_length=1000)


class ReviewDecisionInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    decision:str=Field(max_length=16)
    note:str=Field(default='',max_length=1000)

    @field_validator('decision')
    @classmethod
    def valid_decision(cls,value):
        if value not in {'approve','reject'}:raise ValueError('Decision must be approve or reject')
        return value


class RedirectInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    old_path:str=Field(min_length=2,max_length=255)
    new_path:str=Field(min_length=1,max_length=255)
    status_code:int=301
    is_active:bool=True
    note:str=Field(default='',max_length=300)

    @field_validator('old_path','new_path')
    @classmethod
    def safe_path(cls,p):
        if not p.startswith('/') or p.startswith('//') or '\\' in p or '..' in p or '#' in p or '?' in p or not re.fullmatch(r'/[a-zA-Z0-9/_-]*',p):
            raise ValueError('Redirect paths must be safe local paths')
        return p
    @field_validator('status_code')
    @classmethod
    def status(cls,v):
        if v not in (301,302):raise ValueError('Only 301 or 302 redirects allowed')
        return v


class PublishInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    scheduled_for:datetime|None=None


def seo_out(meta):
    return {key:getattr(meta,key) for key in ('entity_type','entity_id','seo_title','meta_description','canonical_override',
        'robots_index','robots_follow','og_title','og_description','og_image_media_id','schema_type','breadcrumb_title')}


@router.get('/seo/{kind}/{entity_id}')
def get_seo(kind:str,entity_id:str,actor:User=Depends(require_permission('content:read')),db:Session=Depends(get_db)):
    row=entity(db,kind,entity_id);values=effective_seo(row,seo_for(db,kind,entity_id))
    return {'entity_type':kind,'entity_id':entity_id,'seo':values,'validation':entity_issues(db,kind,entity_id)}


@router.put('/seo/{kind}/{entity_id}',dependencies=[Depends(require_csrf)])
def put_seo(kind:str,entity_id:str,payload:SeoPatch,actor:User=Depends(require_permission('content:edit')),db:Session=Depends(get_db)):
    row=entity(db,kind,entity_id)
    if payload.og_image_media_id and not db.get(MediaAsset,payload.og_image_media_id):raise HTTPException(422,'Unknown OG media ID')
    record=seo_for(db,kind,entity_id)
    old=effective_seo(row,record)
    if not record:
        record=SeoRecord(id=str(uuid.uuid4()),entity_type=kind,entity_id=entity_id)
        db.add(record)
    db.add(ContentRevision(entity_type='seo',entity_id=entity_id,snapshot_json=json_safe(old),actor_user_id=actor.id))
    for key,value in payload.model_dump().items():setattr(record,key,value)
    row.seo_title=payload.seo_title;row.meta_description=payload.meta_description
    if kind=='page':row.is_indexable=payload.robots_index
    reset_approval(db,kind,entity_id)
    audit(db,'seo.updated',actor=actor.id,target_type=kind,target_id=entity_id)
    db.commit()
    return get_seo(kind,entity_id,actor,db)


@router.get('/seo-issues')
def validation_summary(actor:User=Depends(require_permission('content:read')),db:Session=Depends(get_db)):
    rows=[entity_issues(db,'page',p.id) for p in db.query(Page).all()]
    rows += [entity_issues(db,c.kind,c.id) for c in db.query(CollectionEntry).all()]
    return {'items':rows,'total':len(rows),'with_errors':sum(x['errors']>0 for x in rows),'with_warnings':sum(x['warnings']>0 for x in rows)}


@router.get('/seo/validate/{kind}/{entity_id}')
def validate_entity(kind:str,entity_id:str,actor:User=Depends(require_permission('content:read')),db:Session=Depends(get_db)):
    return entity_issues(db,kind,entity_id)


@router.post('/reviews/{kind}/{entity_id}/submit',dependencies=[Depends(require_csrf)])
def submit_review(kind:str,entity_id:str,payload:NoteInput,actor:User=Depends(require_permission('content:edit')),db:Session=Depends(get_db)):
    row=entity(db,kind,entity_id)
    if row.status not in {'draft','unpublished'}:raise HTTPException(409,'Move content to draft before requesting review')
    existing=db.query(EditorialReview).filter_by(entity_type=kind,entity_id=entity_id,state='in_review').first()
    if existing:raise HTTPException(409,'Review already requested')
    check=entity_issues(db,kind,entity_id)
    if check['index_requested'] and check['errors']:
        raise HTTPException(422,{'message':'Correct blocking SEO issues before review','issues':check['issues']})
    review=EditorialReview(id=str(uuid.uuid4()),entity_type=kind,entity_id=entity_id,state='in_review',
        content_hash=fingerprint(db,kind,entity_id),requested_by=actor.id,note=payload.note)
    db.add(review);row.status='in_review';audit(db,'review.submitted',actor=actor.id,target_type=kind,target_id=entity_id)
    db.commit();return {'review':review_out(review)}


def review_out(review):
    return {'id':review.id,'entity_type':review.entity_type,'entity_id':review.entity_id,'state':review.state,
            'requested_by':review.requested_by,'reviewed_by':review.reviewed_by,'note':review.note,
            'requested_at':review.requested_at.isoformat()+'Z','decided_at':review.decided_at.isoformat()+'Z' if review.decided_at else None}


@router.get('/reviews')
def reviews(state:str=Query('',max_length=24),actor:User=Depends(require_permission('content:read')),db:Session=Depends(get_db)):
    q=db.query(EditorialReview)
    if state:q=q.filter(EditorialReview.state==state)
    return {'items':[review_out(r) for r in q.order_by(EditorialReview.requested_at.desc()).limit(100).all()]}


@router.post('/reviews/{review_id}/decision',dependencies=[Depends(require_csrf)])
def review_decision(review_id:str,payload:ReviewDecisionInput,actor:User=Depends(require_permission('content:approve')),db:Session=Depends(get_db)):
    decision=payload.decision;note=payload.note
    r=db.get(EditorialReview,review_id)
    if not r or r.state!='in_review':raise HTTPException(409,'Review unavailable or already decided')
    if r.requested_by==actor.id:
        raise HTTPException(403,'Two-person review required: author cannot approve own submission')
    current=fingerprint(db,r.entity_type,r.entity_id)
    if current!=r.content_hash:
        r.state='invalidated';entity(db,r.entity_type,r.entity_id).status='draft';db.commit()
        raise HTTPException(409,'Content changed since review; resubmit')
    row=entity(db,r.entity_type,r.entity_id)
    r.state='approved' if decision=='approve' else 'rejected';r.reviewed_by=actor.id;r.decided_at=utcnow();r.note=note
    row.status='approved' if decision=='approve' else 'draft'
    audit(db,'review.'+decision,actor=actor.id,target_type=r.entity_type,target_id=r.entity_id)
    db.commit();return {'review':review_out(r)}


@router.post('/preview/{kind}/{entity_id}',dependencies=[Depends(require_csrf)])
def create_preview(kind:str,entity_id:str,actor:User=Depends(require_permission('content:read')),db:Session=Depends(get_db)):
    snap=entity_payload(db,kind,entity_id)
    if snap['seo'].get('og_image_media_id'):
        snap['og_image_url']='/api/v1/preview/media/'+snap['seo']['og_image_media_id']
    # Snapshot-based preview remains consistent even if someone edits afterward.
    raw=secrets.token_urlsafe(36)
    row=PrivatePreview(id=str(uuid.uuid4()),token_hash=hashlib.sha256(raw.encode()).hexdigest(),
        entity_type=kind,entity_id=entity_id,snapshot_json=json_safe(snap),created_by=actor.id,
        expires_at=utcnow()+timedelta(minutes=30))
    db.add(row);db.commit()
    return {'preview_url':'/api/v1/preview/view/'+raw,'expires_in_seconds':1800,'private':True}


@router.get('/preview/media/{media_id}',include_in_schema=False)
def preview_media(media_id:str,request:Request,actor:User=Depends(require_permission('media:read')),db:Session=Depends(get_db)):
    asset=db.get(MediaAsset,media_id)
    if not asset:raise HTTPException(404,'Asset not found')
    media_file=request.app.state.media_root/asset.storage_name
    if not media_file.is_file():raise HTTPException(404,'Media unavailable')
    return FileResponse(media_file,media_type=asset.mime_type,headers={'Cache-Control':'private, no-store'})


@router.get('/preview/view/{token}',response_class=HTMLResponse,include_in_schema=False)
def view_preview(token:str,actor:User=Depends(require_permission('content:read')),db:Session=Depends(get_db)):
    if not _PREVIEW_TOKEN_RE.fullmatch(token or ''):raise HTTPException(404,'Preview expired')
    row=db.query(PrivatePreview).filter_by(token_hash=hashlib.sha256(token.encode()).hexdigest()).first()
    if not row or row.expires_at < utcnow():raise HTTPException(404,'Preview expired')
    try:snap=json.loads(row.snapshot_json)
    except (TypeError,json.JSONDecodeError):raise HTTPException(404,'Preview expired')
    if not isinstance(snap,dict):raise HTTPException(404,'Preview expired')
    if row.entity_type=='page':
        from .phase6_renderer import integrate_page
        try: base=canonical_base(db)
        except HTTPException:base='https://auvorent.com'
        source=integrate_page(snap,db,base=base,staging=True)
        source=source.replace('<main ', '<div role="status" class="cms-private-preview">Private CMS preview · Not published</div><main ',1)
    else: source=render_document(snap,preview=True)
    return HTMLResponse(source,headers={'Cache-Control':'no-store','X-Robots-Tag':'noindex, nofollow'})


def redirect_cycle(db,old,new,exclude_id=None):
    graph={r.old_path:r.new_path for r in db.query(RedirectRule).filter_by(is_active=True).all() if r.id!=exclude_id}
    graph[old]=new
    for start in graph:
        p=start;seen=set()
        while p in graph:
            if p in seen:return True
            seen.add(p);p=graph[p]
    return False


def redirect_out(r):
    return {'id':r.id,'old_path':r.old_path,'new_path':r.new_path,'status_code':r.status_code,'is_active':r.is_active,'note':r.note}


@router.get('/redirects')
def redirects(actor:User=Depends(require_permission('content:read')),db:Session=Depends(get_db)):
    return {'items':[redirect_out(r) for r in db.query(RedirectRule).order_by(RedirectRule.old_path).all()]}


@router.post('/redirects',dependencies=[Depends(require_csrf)],status_code=201)
def create_redirect(payload:RedirectInput,actor:User=Depends(require_permission('content:edit')),db:Session=Depends(get_db)):
    if payload.old_path==payload.new_path or redirect_cycle(db,payload.old_path,payload.new_path):raise HTTPException(422,'Redirect loop detected')
    if db.query(RedirectRule).filter_by(old_path=payload.old_path).first(): raise HTTPException(409,"Redirect already exists")
    row=RedirectRule(id=str(uuid.uuid4()),**payload.model_dump())
    db.add(row);audit(db,'redirect.created',actor=actor.id,target_type='redirect',target_id=row.id);db.commit()
    return {'redirect':redirect_out(row)}


@router.patch('/redirects/{id}',dependencies=[Depends(require_csrf)])
def edit_redirect(id:str,payload:RedirectInput,actor:User=Depends(require_permission('content:edit')),db:Session=Depends(get_db)):
    row=db.get(RedirectRule,id)
    if not row:raise HTTPException(404,'Redirect not found')
    if payload.is_active and (payload.old_path==payload.new_path or redirect_cycle(db,payload.old_path,payload.new_path,id)):
        raise HTTPException(422,'Redirect loop detected')
    if db.query(RedirectRule).filter(RedirectRule.old_path==payload.old_path,RedirectRule.id!=id).first():
        raise HTTPException(409,'Redirect source already exists')
    for k,v in payload.model_dump().items():setattr(row,k,v)
    audit(db,'redirect.updated',actor=actor.id,target_type='redirect',target_id=id);db.commit()
    return {'redirect':redirect_out(row)}


@router.delete('/redirects/{id}',dependencies=[Depends(require_csrf)])
def delete_redirect(id:str,actor:User=Depends(require_permission('content:edit')),db:Session=Depends(get_db)):
    row=db.get(RedirectRule,id)
    if not row:raise HTTPException(404,'Redirect not found')
    db.delete(row);audit(db,'redirect.deleted',actor=actor.id,target_type='redirect',target_id=id);db.commit()
    return {'status':'deleted'}


# Approved HTML seed fragments are allowed only if they still match the exact
# original package. User-edited HTML is NEVER rendered raw by this module.
def approved_seed_html(route,key,provided):
    try:
        seed=json.loads(SEED.read_text(encoding='utf-8'))
        for page in seed['pages']:
            if page['route']!=route:continue
            for section in page['sections']:
                if section['section_key']==key and section['content'].get('html')==provided:return provided
    except (OSError,ValueError):pass
    return None


def render_section(section,route):
    content=section['content']
    if not section.get('enabled',True):return ''
    fragment=approved_seed_html(route,section['key'],content.get('html',''))
    if fragment:return fragment
    heading=html.escape(str(content.get('heading','')))
    description=html.escape(str(content.get('description',content.get('text',''))))
    return ('<section class="section"><div class="wrap"><div class="cms-preview-section">'
            + (f'<h2>{heading}</h2>' if heading else '')
            + (f'<p>{description}</p>' if description else '')
            + '</div></div></section>')


def render_document(snap,preview=False,base='https://auvorent.com',staging=False):
    meta=snap['seo']; route=snap.get('route') or ('/insights/'+snap['slug']+'/')
    canonical=meta.get('canonical_override') or base+route
    title=html.escape(meta.get('seo_title') or snap['title'],quote=True)
    description=html.escape(meta.get('meta_description') or '',quote=True)
    og_title=html.escape(meta.get('og_title') or meta.get('seo_title') or snap['title'],quote=True)
    og_desc=html.escape(meta.get('og_description') or meta.get('meta_description') or '',quote=True)
    intended_robot=('index' if meta.get('robots_index') else 'noindex')+(',follow' if meta.get('robots_follow') else ',nofollow')
    robot='noindex,nofollow' if preview or staging else intended_robot
    robot_planned=f' data-planned-robots="{intended_robot}"' if staging else ''
    schema={'@context':'https://schema.org','@type':meta.get('schema_type','WebPage'),
            'name':meta.get('seo_title') or snap['title'],'url':canonical,'description':meta.get('meta_description','')}
    data=f'<script type="application/ld+json">{json.dumps(schema,ensure_ascii=False).replace("<","\\u003c")}</script>'
    if 'sections' in snap:
        body=''.join(render_section(s,route) for s in snap['sections'])
    else:
        body=f'<section class="section"><div class="wrap"><h1>{html.escape(snap["title"])}</h1><p>{html.escape(snap.get("summary", ""))}</p><div style="white-space:pre-line">{html.escape(snap.get("body", ""))}</div></div></section>'
    og_image=snap.get('og_image_url','')
    nav='<nav aria-label="Primary"><a href="/services/">Services</a> <a href="/industries/">Industries</a> <a href="/our-approach/">Our approach</a> <a href="/insights/">Insights</a> <a href="/about/">About</a></nav>'
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        +f'<title>{title}</title><meta name="description" content="{description}"><meta name="robots" content="{robot}"{robot_planned}>'
        +f'<link rel="canonical" href="{html.escape(canonical,quote=True)}"><meta property="og:type" content="website">'
        +f'<meta property="og:title" content="{og_title}"><meta property="og:description" content="{og_desc}">'
        +f'<meta property="og:url" content="{html.escape(canonical,quote=True)}">'
        +(f'<meta property="og:image" content="{html.escape(og_image,quote=True)}">' if og_image else '')
        + '<link rel="stylesheet" href="/assets/style.css">'+data+'</head><body>'
        +'<a class="skip-link" href="#content">Skip to content</a><header class="site-header"><div class="wrap nav-wrap">'
        +'<a href="/" aria-label="Auvorent Advisory"><img src="/assets/logo.svg" alt="Auvorent Advisory" style="width:178px;height:auto"></a>'
        +nav+'<a class="button primary" href="/contact/">Request a strategy call</a></div></header>'
        +('<div role="status" style="padding:10px;background:#E5EBE8;text-align:center">Private CMS preview · Not published</div>' if preview else '')
        +'<main id="content">'+body+'</main><footer class="site-footer"><div class="wrap">Auvorent Advisory · Business clarity. Intelligent growth.</div></footer></body></html>')


def stage_root(request):
    return request.app.state.publish_root


def _safe_failure_text(value):
    if value is None:return None
    text=str(value).strip()
    for prefix in _SAFE_FAILURE_PREFIXES:
        if text.startswith(prefix):return text[:500]
    return 'Publication failed safely; no staging release was changed'


def _safe_report(raw):
    try:data=json.loads(raw or '{}')
    except (TypeError,json.JSONDecodeError):return {}
    if not isinstance(data,dict):return {}
    return {key:data[key] for key in _PUBLIC_REPORT_KEYS if key in data}


def deployment_out(job):
    return {'id':job.id,'release_id':job.release_id,'status':job.status,'environment':job.environment,
            'scheduled_for':job.scheduled_for.isoformat()+'Z' if job.scheduled_for else None,
            'created_at':job.created_at.isoformat()+'Z','completed_at':job.completed_at.isoformat()+'Z' if job.completed_at else None,
            'error_message':_safe_failure_text(job.error_message),'report':_safe_report(job.report_json)}


def active_release(root:Path):
    pointer=root/'current'
    if not pointer.is_symlink():return None
    target=pointer.resolve()
    if target.parent!=(root/'releases').resolve():return None
    return target if target.is_dir() else None


def _assert_release_tree_safe(root:Path):
    root=root.resolve()
    if not root.is_dir():raise RuntimeError('Invalid managed release')
    for item in root.rglob('*'):
        if item.is_symlink():
            raise RuntimeError('Managed release contains unsupported symbolic links')


def switch_release(root:Path,target:Path):
    releases=(root/'releases').resolve()
    if target.is_symlink():raise RuntimeError('Invalid managed release')
    resolved=target.resolve()
    if resolved.parent!=releases or not resolved.is_dir():
        raise RuntimeError('Invalid managed release')
    _assert_release_tree_safe(resolved)
    link=root/('.next-'+uuid.uuid4().hex)
    link.symlink_to(resolved,target_is_directory=True)
    os.replace(link,root/'current')


def _valid_release_manifest(target:Path,release_id:str):
    manifest=target/'manifest.json'
    if manifest.is_symlink() or not manifest.is_file():return False
    try:data=json.loads(manifest.read_text(encoding='utf-8'))
    except (OSError,TypeError,json.JSONDecodeError):return False
    return isinstance(data,dict) and data.get('release_id')==release_id and data.get('environment')=='local_staging'


def _route_file(root:Path,route:str):
    if not isinstance(route,str) or not route.startswith('/') or route.startswith('//') or '..' in route or '\\' in route or not _ROUTE_RE.fullmatch(route):
        raise ValueError('Invalid managed route')
    candidate=(root/'index.html') if route=='/' else (root/route.lstrip('/')/'index.html')
    resolved_parent=candidate.parent.resolve()
    if not resolved_parent.is_relative_to(root.resolve()):raise ValueError('Invalid managed route')
    return candidate


def _manifest_items(release:Path|None):
    if not release:return []
    manifest=release/'manifest.json'
    try:data=json.loads(manifest.read_text(encoding='utf-8'))
    except (OSError,TypeError,json.JSONDecodeError):return []
    items=data.get('published',[]) if isinstance(data,dict) else []
    return items if isinstance(items,list) else []


def _prune_nonpublic_routes(db:Session,target:Path,old:Path|None):
    """Remove only routes that were previously CMS-published but are no longer public.

    The V6 baseline intentionally contains static, non-CMS-published pages. Those
    pages must remain present until they have actually entered the CMS publishing
    lifecycle; otherwise a first publish of one page would erase the rest of the
    approved V6 website shell.
    """
    public_status={'published','approved'}
    rows=[('page',p) for p in db.query(Page).all()]+[(c.kind,c) for c in db.query(CollectionEntry).all() if c.kind in PUBLIC_COLLECTION_TYPES]
    by_key={(kind,row.id):row for kind,row in rows}
    for item in _manifest_items(old):
        if not isinstance(item,dict):continue
        kind=item.get('type');ident=item.get('id');route=item.get('route')
        if kind!='page' and kind not in PUBLIC_COLLECTION_TYPES:continue
        row=by_key.get((kind,ident))
        keep=bool(row and row.status in public_status and entity_route(row,kind)==route)
        if not keep:
            try:_route_file(target,route).unlink(missing_ok=True)
            except ValueError:raise RuntimeError('Invalid managed route')


def _managed_manifest_entries(db:Session,target:Path):
    result=[]
    rows=[('page',p) for p in db.query(Page).all()]+[(c.kind,c) for c in db.query(CollectionEntry).all() if c.kind in PUBLIC_COLLECTION_TYPES]
    for kind,row in rows:
        if row.status not in {'published','approved'}:continue
        route=entity_route(row,kind)
        try:exists=_route_file(target,route).is_file()
        except ValueError:raise RuntimeError('Invalid managed route')
        if exists:result.append({'type':kind,'id':row.id,'route':route})
    return result


def compile_release(db:Session,root:Path,job:PublishDeployment,media_root:Path|None=None):
    """Build immutable release; pointer changes only after every page passes validation."""
    root.mkdir(parents=True,exist_ok=True)
    releases=root/'releases';releases.mkdir(exist_ok=True)
    old=active_release(root)
    release_id=uuid.uuid4().hex
    target=releases/release_id
    base=canonical_base(db)
    try:
        if old:
            _assert_release_tree_safe(old)
            shutil.copytree(old,target,symlinks=False)
        else:
            from .phase6_renderer import copy_baseline
            copy_baseline(target)
        _assert_release_tree_safe(target)
        _prune_nonpublic_routes(db,target,old)
        assets=target/'assets';assets.mkdir(exist_ok=True)
        bundled=ROOT/'seed'/'v6_assets'
        for source in bundled.rglob('*'):
            if source.is_file():
                if source.is_symlink():raise RuntimeError('Managed release contains unsupported symbolic links')
                destination=assets/source.relative_to(bundled)
                destination.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(source,destination)
        approved=[];skipped=[]
        for kind,row in [('page',p) for p in db.query(Page).all()] + [(c.kind,c) for c in db.query(CollectionEntry).all()]:
            if row.status!='approved':continue
            review=db.query(EditorialReview).filter_by(entity_type=kind,entity_id=row.id,state='approved').order_by(EditorialReview.requested_at.desc()).first()
            if not review or review.content_hash!=fingerprint(db,kind,row.id):
                raise ValueError(f'Approval stale or missing for {kind}:{row.id}')
            val=entity_issues(db,kind,row.id)
            security_errors=[x for x in val['issues'] if x['level']=='error' and x['code'] in {'canonical','image_missing'}]
            if (val['index_requested'] and val['errors']) or security_errors:
                raise ValueError(f'SEO blocks {kind}:{row.id}: '+', '.join(x['code'] for x in val['issues'] if x['level']=='error'))
            if kind!='page' and kind not in PUBLIC_COLLECTION_TYPES:
                skipped.append(kind+':'+row.id);continue
            snap=entity_payload(db,kind,row.id)
            og_id=snap['seo'].get('og_image_media_id')
            if og_id:
                asset=db.get(MediaAsset,og_id)
                media_source=(media_root or (root.parent/'media'))/asset.storage_name if asset else None
                if media_source and media_source.is_file():
                    media_dest=assets/'media'/asset.storage_name
                    media_dest.parent.mkdir(parents=True,exist_ok=True)
                    shutil.copy2(media_source,media_dest)
                    snap['og_image_url']=base+'/assets/media/'+asset.storage_name
            route=entity_route(row,kind)
            outfile=_route_file(target,route)
            outfile.parent.mkdir(parents=True,exist_ok=True)
            if kind=='page':
                from .phase6_renderer import integrate_page
                html_output=integrate_page(snap,db,base=base,staging=True)
            else:
                from .phase6_renderer import integrate_collection
                html_output=integrate_collection(snap,db,base=base,staging=True)
            outfile.write_text(html_output,encoding='utf-8')
            approved.append((kind,row.id,route,review.id))
        if not approved:
            raise ValueError('Nothing approved to publish')
        from .phase6_renderer import apply_global_changes,copy_media,write_site_bridge
        apply_global_changes(target,db,base=base,staging=True)
        copy_media(db,media_root or (root.parent/'media'),target)
        import os as _env
        write_site_bridge(target,_env.environ.get('CMS_PUBLIC_API_BASE','http://127.0.0.1:8900'))
        # Build sitemap from the current release and indexable CMS records only.
        urls=[]
        for kind,row in [('page',p) for p in db.query(Page).all()]+[(c.kind,c) for c in db.query(CollectionEntry).filter(CollectionEntry.kind.in_(list(PUBLIC_COLLECTION_TYPES))).all()]:
            if row.status not in ('published','approved'):continue
            route=entity_route(row,kind)
            filepath=_route_file(target,route)
            if not filepath.exists():continue
            meta=effective_seo(row,seo_for(db,kind,row.id))
            if meta['robots_index']:urls.append(meta['canonical_override'] or base+route)
        sitemap='<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'+''.join('<url><loc>'+html.escape(u)+'</loc></url>' for u in sorted(set(urls)))+'</urlset>'
        (target/'sitemap.xml').write_text(sitemap,encoding='utf-8')
        # LOCAL staging remains non-indexable even when final canonical/robots values are modeled.
        (target/'robots.txt').write_text('User-agent: *\nDisallow: /\n',encoding='utf-8')
        redirects=[r for r in db.query(RedirectRule).all() if r.is_active]
        (target/'_redirects').write_text(''.join(f'{r.old_path} {r.new_path} {r.status_code}\n' for r in redirects),encoding='utf-8')
        managed=_managed_manifest_entries(db,target)
        (target/'manifest.json').write_text(json_safe({'release_id':release_id,'created_at':utcnow().isoformat()+'Z',
             'environment':'local_staging','published':managed,
             'robots':'staging_disallow_all','base':base}),encoding='utf-8')
        # Test output exists and expected metadata appears before changing current.
        for kind,id,route,_ in approved:
            filepath=_route_file(target,route)
            source=filepath.read_text(encoding='utf-8')
            dom=BeautifulSoup(source,'html.parser')
            if not dom.find('link',rel='canonical') or not dom.title or not dom.find('meta',attrs={'name':'description'}):
                raise ValueError('Generated HTML missing critical SEO elements')
        _assert_release_tree_safe(target)
        switch_release(root,target)
        for kind,id,route,review_id in approved:
            entity(db,kind,id).status='published'
        return {'release_id':release_id,'published_count':len(approved),'skipped_non_public_collections':skipped,
                'sitemap_url_count':len(set(urls)),'staging_only':True}
    except Exception:
        # Leave previously active release intact if anything fails before pointer swap.
        if active_release(root)!=target:shutil.rmtree(target,ignore_errors=True)
        raise


def perform_publish(db,root,job,media_root=None):
    with PUBLISH_LOCK:
        previous=active_release(root)
        job.status='building';db.commit()
        try:
            report=compile_release(db,root,job,media_root)
            job.release_id=report['release_id'];job.status='completed';job.report_json=json_safe(report)
            job.completed_at=utcnow();audit(db,'publish.completed',actor=job.requested_by,target_type='deployment',target_id=job.id,
                                            release=job.release_id,count=report['published_count'])
            db.commit()
        except Exception as exc:
            db.rollback()
            # If a DB/audit failure occurred after the atomic pointer swap,
            # restore the previous site; the prior immutable release is retained.
            if active_release(root)!=previous:
                if previous:switch_release(root,previous)
                else:(root/'current').unlink(missing_ok=True)
            existing=db.get(PublishDeployment,job.id)
            existing.status='failed';existing.error_message=_safe_failure_text(exc);existing.completed_at=utcnow()
            audit(db,'publish.failed',actor=existing.requested_by,target_type='deployment',target_id=existing.id,reason=existing.error_message)
            db.commit()
        return db.get(PublishDeployment,job.id)


@router.post('/publishing/build',dependencies=[Depends(require_csrf)])
def build(payload:PublishInput,request:Request,actor:User=Depends(require_permission('content:publish')),db:Session=Depends(get_db)):
    if payload.scheduled_for and payload.scheduled_for.tzinfo is None:
        raise HTTPException(422,'Scheduled publication requires a timezone offset')
    scheduled=payload.scheduled_for.astimezone(__import__('datetime').timezone.utc).replace(tzinfo=None) if payload.scheduled_for else None
    if scheduled and scheduled<utcnow():raise HTTPException(422,'Schedule must be in the future')
    job=PublishDeployment(id=str(uuid.uuid4()),status='scheduled' if scheduled else 'queued',
         environment='local_staging',scheduled_for=scheduled,requested_by=actor.id)
    db.add(job);audit(db,'publish.requested',actor=actor.id,target_type='deployment',target_id=job.id,scheduled=bool(scheduled));db.commit()
    if not scheduled:job=perform_publish(db,stage_root(request),job,request.app.state.media_root)
    return {'deployment':deployment_out(job)}


@router.post('/publishing/run-due',dependencies=[Depends(require_csrf)])
def run_due(request:Request,actor:User=Depends(require_permission('content:publish')),db:Session=Depends(get_db)):
    due=db.query(PublishDeployment).filter(PublishDeployment.status=='scheduled',PublishDeployment.scheduled_for<=utcnow()).order_by(PublishDeployment.scheduled_for).limit(5).all()
    return {'items':[deployment_out(perform_publish(db,stage_root(request),job,request.app.state.media_root)) for job in due]}


@router.get('/publishing/deployments')
def deployments(actor:User=Depends(require_permission('content:read')),db:Session=Depends(get_db)):
    return {'items':[deployment_out(j) for j in db.query(PublishDeployment).order_by(PublishDeployment.created_at.desc()).limit(100).all()]}


@router.get('/publishing/current')
def current_release(request:Request,actor:User=Depends(require_permission('content:read'))):
    release=active_release(stage_root(request))
    return {'release_id':release.name if release else None,'staging_only':True}


@router.post('/publishing/rollback/{release_id}',dependencies=[Depends(require_csrf)])
def rollback(release_id:str,request:Request,actor:User=Depends(require_permission('content:publish')),db:Session=Depends(get_db)):
    root=stage_root(request);target=root/'releases'/release_id
    known=db.query(PublishDeployment).filter_by(release_id=release_id,status='completed').first() if _RELEASE_ID_RE.fullmatch(release_id or '') else None
    if not known or target.is_symlink() or not target.is_dir() or not _valid_release_manifest(target,release_id):
        raise HTTPException(404,'Managed release not found')
    with PUBLISH_LOCK:
        previous=active_release(root)
        try:
            switch_release(root,target)
            job=PublishDeployment(id=str(uuid.uuid4()),release_id=None,status='rolled_back',environment='local_staging',
                 requested_by=actor.id,report_json=json_safe({'restored_release_id':release_id,'staging_only':True}),completed_at=utcnow())
            db.add(job);audit(db,'publish.rolled_back',actor=actor.id,target_type='deployment',target_id=job.id,release=release_id)
            db.commit()
        except Exception:
            db.rollback()
            if active_release(root)!=previous:
                if previous:switch_release(root,previous)
                else:(root/'current').unlink(missing_ok=True)
            raise
    return {'restored_release_id':release_id,'staging_only':True}

@router.get('/publishing/entities')
def publishable_entities(actor:User=Depends(require_permission('content:read')),db:Session=Depends(get_db)):
    items=[{'id':p.id,'type':'page','title':p.title,'route':p.route,'status':p.status} for p in db.query(Page).order_by(Page.route).all()]
    items += [{'id':c.id,'type':c.kind,'title':c.title,'route':entity_route(c,c.kind),'status':c.status}
              for c in db.query(CollectionEntry).order_by(CollectionEntry.kind,CollectionEntry.title).all()]
    return {'items':items}

@router.get('/publishing/versions/{kind}/{entity_id}')
def list_versions(kind:str,entity_id:str,actor:User=Depends(require_permission('content:read')),db:Session=Depends(get_db)):
    entity(db,kind,entity_id)
    from sqlalchemy import and_, or_
    filters=[and_(ContentRevision.entity_type.in_([kind,'seo']),ContentRevision.entity_id==entity_id)]
    if kind=='page':
        ids=[r.id for r in db.query(PageSection).filter(PageSection.page_id==entity_id).all()]
        if ids:filters.append(and_(ContentRevision.entity_type=='section',ContentRevision.entity_id.in_(ids)))
    rows=db.query(ContentRevision).filter(or_(*filters)).order_by(ContentRevision.created_at.desc(),ContentRevision.id.desc()).limit(40).all()
    return {'items':[{'id':r.id,'type':r.entity_type,'created_at':r.created_at.isoformat()+'Z',
        'actor_user_id':r.actor_user_id} for r in rows]}


def _revision_snapshot(row):
    try:snap=json.loads(row.snapshot_json)
    except (TypeError,json.JSONDecodeError):raise HTTPException(422,'Revision snapshot is invalid')
    if not isinstance(snap,dict):raise HTTPException(422,'Revision snapshot is invalid')
    return snap


def _validated_model(model,data):
    try:return model(**data)
    except ValidationError:raise HTTPException(422,'Revision failed current safety validation')


def _valid_revision_uuid(value):
    try:return str(uuid.UUID(str(value)))==str(value).lower()
    except (ValueError,TypeError,AttributeError):return False


@router.post('/publishing/versions/{revision_id}/restore',dependencies=[Depends(require_csrf)])
def restore_version(revision_id:int,actor:User=Depends(require_permission('content:edit')),db:Session=Depends(get_db)):
    row=db.get(ContentRevision,revision_id)
    if not row or row.entity_type not in ALLOWED_TYPES|{'seo','section'}:
        raise HTTPException(404,'Supported content revision not found')
    snap=_revision_snapshot(row)
    if row.entity_type=='section':
        section=db.get(PageSection,row.entity_id)
        if not section:raise HTTPException(404,'Section no longer exists')
        from .phase2 import _section_out
        from .schemas import UpdateSectionInput
        selected={key:snap[key] for key in ('section_key','section_type','position','is_enabled','content') if key in snap}
        changes=_validated_model(UpdateSectionInput,selected).model_dump(exclude_unset=True)
        db.add(ContentRevision(entity_type='section',entity_id=section.id,
            snapshot_json=json_safe(_section_out(section)),actor_user_id=actor.id))
        if 'content' in changes:section.content_json=json_safe(changes.pop('content'))
        for field,value in changes.items():setattr(section,field,value)
        kind='page';target=entity(db,kind,section.page_id)
    elif row.entity_type=='seo':
        target=db.get(Page,row.entity_id) or db.get(CollectionEntry,row.entity_id)
        if not target:raise HTTPException(404,'Content no longer exists')
        kind='page' if isinstance(target,Page) else target.kind
        before=effective_seo(target,seo_for(db,kind,target.id))
        candidate={key:snap.get(key,before[key]) for key in ('seo_title','meta_description','canonical_override','robots_index','robots_follow','og_title',
                    'og_description','og_image_media_id','schema_type','breadcrumb_title')}
        validated=_validated_model(SeoPatch,candidate)
        if validated.og_image_media_id and not db.get(MediaAsset,validated.og_image_media_id):raise HTTPException(422,'Revision references unavailable media')
        record=seo_for(db,kind,target.id)
        if not record:
            record=SeoRecord(id=str(uuid.uuid4()),entity_type=kind,entity_id=target.id)
            db.add(record)
        db.add(ContentRevision(entity_type='seo',entity_id=target.id,snapshot_json=json_safe(before),actor_user_id=actor.id))
        for key,value in validated.model_dump().items():setattr(record,key,value)
        target.seo_title=record.seo_title;target.meta_description=record.meta_description
        if kind=='page':target.is_indexable=record.robots_index
    else:
        kind=row.entity_type;target=entity(db,kind,row.entity_id)
        if kind=='page':
            from .phase2 import _page_out, _norm_route
            from .schemas import UpdatePageInput, UpdateSectionInput
            selected={key:snap[key] for key in ('route','slug','title','template','show_in_navigation','is_indexable','seo_title','meta_description') if key in snap}
            changes=_validated_model(UpdatePageInput,selected).model_dump(exclude_unset=True)
            db.add(ContentRevision(entity_type=kind,entity_id=target.id,snapshot_json=json_safe(_page_out(target,True)),actor_user_id=actor.id))
            if 'route' in changes:
                new_route=_norm_route(changes['route'])
                occupied=db.query(Page).filter(Page.route==new_route,Page.id!=target.id).first()
                if occupied:raise HTTPException(409,'Restoring this version would duplicate an existing page route')
                changes['route']=new_route
            for field,value in changes.items():setattr(target,field,value)
            existing={s.id:s for s in target.sections}
            retained=set()
            sections=snap.get('sections',[])
            if not isinstance(sections,list) or len(sections)>200:raise HTTPException(422,'Revision failed current safety validation')
            for info in sections:
                if not isinstance(info,dict):raise HTTPException(422,'Revision failed current safety validation')
                ident=info.get('id') or str(uuid.uuid4())
                if not _valid_revision_uuid(ident) or ident in retained:raise HTTPException(422,'Revision failed current safety validation')
                retained.add(ident)
                selected_section={key:info[key] for key in ('section_key','section_type','position','is_enabled','content') if key in info}
                section_changes=_validated_model(UpdateSectionInput,selected_section).model_dump(exclude_unset=True)
                section=existing.get(ident)
                if not section:
                    section=PageSection(id=ident,page_id=target.id);db.add(section)
                if 'content' in section_changes:section.content_json=json_safe(section_changes.pop('content'))
                for key,value in section_changes.items():setattr(section,key,value)
            for sid,section in existing.items():
                if sid not in retained:db.delete(section)
        else:
            from .phase3 import CollectionPatch, _check_media, _collection_out, _safe_content, _set_usage
            db.add(ContentRevision(entity_type=kind,entity_id=target.id,
                    snapshot_json=json_safe(_collection_out(target,db,True)),actor_user_id=actor.id))
            selected={key:snap[key] for key in ('title','slug','summary','body_markdown','sort_order','is_featured',
                          'hero_media_id','icon_media_id','seo_title','meta_description','content') if key in snap}
            changes=_validated_model(CollectionPatch,selected).model_dump(exclude_unset=True)
            if 'slug' in changes:
                collision=db.query(CollectionEntry).filter(CollectionEntry.kind==kind,CollectionEntry.slug==changes['slug'],
                               CollectionEntry.id!=target.id).first()
                if collision:raise HTTPException(409,'Restoring this version would duplicate a collection slug')
            _check_media(db,changes.get('hero_media_id',target.hero_media_id),'hero')
            _check_media(db,changes.get('icon_media_id',target.icon_media_id),'icon')
            if 'content' in changes:target.content_json=_safe_content(changes.pop('content'))
            for field,value in changes.items():setattr(target,field,value)
            if 'hero_media_id' in selected:_set_usage(db,target.hero_media_id,'collection',target.id,'hero')
            if 'icon_media_id' in selected:_set_usage(db,target.icon_media_id,'collection',target.id,'icon')
    reset_approval(db,kind,target.id)
    audit(db,'content.revision_restored',actor=actor.id,target_type=kind,target_id=target.id,revision_id=row.id)
    db.commit()
    return {'status':'draft','entity_type':kind,'entity_id':target.id,'restored_revision_id':row.id,
            'note':'Changes require a new independent editorial approval before publication.'}


@router.get('/publishing/site/{subpath:path}',include_in_schema=False)
def browse_local_staging(subpath:str,request:Request,actor:User=Depends(require_permission('content:read'))):
    """Authenticated browser view of current staging release; not a public host."""
    root=active_release(stage_root(request))
    if not root:raise HTTPException(404,'No staging release is active')
    root=root.resolve()
    candidate=(root/subpath).resolve()
    if not candidate.is_relative_to(root):raise HTTPException(404,'Invalid path')
    if candidate.is_dir():candidate=(candidate/'index.html').resolve()
    if not candidate.is_relative_to(root):raise HTTPException(404,'Invalid path')
    if not candidate.is_file():raise HTTPException(404,'File not found in staging release')
    if candidate.suffix.lower()=='.html':
        source=candidate.read_text(encoding='utf-8')
        # Only our generated asset and navigation URLs are rewritten. HTML is
        # rendered from trusted V6 source fragments or escaped CMS fields.
        source=re.sub(r'((?:href|src)=")/(?!api/v1/)',r'\1/api/v1/publishing/site/',source)
        return HTMLResponse(source,headers={'Cache-Control':'private, no-store','X-Robots-Tag':'noindex, nofollow'})
    return FileResponse(candidate,headers={'Cache-Control':'private, no-store','X-Robots-Tag':'noindex, nofollow'})
