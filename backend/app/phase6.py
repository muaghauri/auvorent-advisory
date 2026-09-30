"""Phase 6 — visual editor, full V6 rendering, deployment readiness/export.

Production export is deliberately gated: no DNS mutation, no live publish, no
false email delivery claims, no public indexing until all release gates pass.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import uuid
from pathlib import Path
from bs4 import BeautifulSoup
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session
from .models import Page, PageSection, MediaAsset, SiteSetting, utcnow
from .security import audit, get_db, require_csrf, require_permission
from .phase5 import active_release, reset_approval, PUBLISH_LOCK, canonical_base
from .phase6_renderer import section_fields, safe_local_url

router=APIRouter(prefix='/api/v1',tags=['V6 Integration & Deployment'])


class VisualEdit(BaseModel):
    model_config=ConfigDict(extra='forbid')
    text_overrides: dict[str,str] = Field(default_factory=dict,max_length=250)
    image_overrides: dict[str,str] = Field(default_factory=dict,max_length=30)
    alt_overrides: dict[str,str] = Field(default_factory=dict,max_length=30)
    icon_overrides: dict[str,str] = Field(default_factory=dict,max_length=80)
    link_overrides: dict[str,str] = Field(default_factory=dict,max_length=100)


def get_section(db, section_id):
    section=db.get(PageSection,section_id)
    if not section:raise HTTPException(404,'Section not found')
    return section


def content_of(section):
    try:return json.loads(section.content_json or '{}')
    except json.JSONDecodeError:raise HTTPException(422,'Section JSON is invalid')


@router.get('/integration/sections/{section_id}/fields')
def visual_fields(section_id:str,actor=Depends(require_permission('content:edit')),db:Session=Depends(get_db)):
    section=get_section(db,section_id);content=content_of(section)
    fields=section_fields(content.get('html',''),content)
    media=db.query(MediaAsset).filter(MediaAsset.kind.in_(['image','icon','brand'])).order_by(MediaAsset.original_name).all()
    return {'section_id':section.id,'page_id':section.page_id,'section_key':section.section_key,
            'fields':fields,'media':[{'id':m.id,'name':m.original_name,'kind':m.kind,
                                     'url':'/assets/media/'+m.storage_name,'alt':m.alt_text} for m in media]}


@router.patch('/integration/sections/{section_id}/visual',dependencies=[Depends(require_csrf)])
def edit_visual(section_id:str,payload:VisualEdit,actor=Depends(require_permission('content:edit')),db:Session=Depends(get_db)):
    section=get_section(db,section_id);content=content_of(section)
    fields=section_fields(content.get('html',''),content)
    texts={f['key'] for f in fields if f['kind']=='text'}
    images={f['key'] for f in fields if f['kind']=='image'}
    links={f['key'] for f in fields if f['kind']=='link'}
    icons={f['key'] for f in fields if f['kind']=='icon'}
    if set(payload.text_overrides)-texts or set(payload.image_overrides)-images or set(payload.alt_overrides)-images or set(payload.link_overrides)-links or set(payload.icon_overrides)-icons:
        raise HTTPException(422,'Unknown visual field key')
    if any(len(x)>12000 for x in payload.text_overrides.values()):raise HTTPException(422,'Visual text is too long')
    if any(len(x)>300 for x in payload.alt_overrides.values()):raise HTTPException(422,'Image alt text is too long')
    for key,url in payload.link_overrides.items():
        if not safe_local_url(url):raise HTTPException(422,f'Links must use safe website-relative paths: {key}')
    resolved={}
    for key,value in payload.image_overrides.items():
        media=db.get(MediaAsset,value)
        if media and media.kind in ('image','icon','brand'):
            resolved[key]='/assets/media/'+media.storage_name
        elif value.startswith('/assets/') and safe_local_url(value):
            resolved[key]=value
        else:raise HTTPException(422,f'Image must be a valid media ID or website asset: {key}')
    resolved_icons={}
    for key,value in payload.icon_overrides.items():
        media=db.get(MediaAsset,value)
        if media and media.kind=='icon' and media.mime_type=='image/svg+xml':
            resolved_icons[key]='/assets/media/'+media.storage_name
        else:raise HTTPException(422,f'Icons must be selected from sanitized SVG icon assets: {key}')
    for field,changes in [('icon_overrides',resolved_icons),('text_overrides',payload.text_overrides),('image_overrides',resolved),
                          ('alt_overrides',payload.alt_overrides),('link_overrides',payload.link_overrides)]:
        if changes:content[field]={**content.get(field,{}),**changes}
    from .models import ContentRevision
    old=content_of(section)
    db.add(ContentRevision(entity_type='section',entity_id=section.id,
        snapshot_json=json.dumps(old,ensure_ascii=False),actor_user_id=actor.id))
    reset_approval(db,'page',section.page_id)
    section.content_json=json.dumps(content,ensure_ascii=False)
    audit(db,'section.visual_updated',actor=actor.id,target_type='section',target_id=section.id,
          fields=sum(map(len,(payload.text_overrides,payload.image_overrides,payload.alt_overrides,payload.icon_overrides,payload.link_overrides))))
    db.commit()
    return visual_fields(section.id,actor,db)


def readiness(app,db):
    root=app.state.publish_root;current=active_release(root);settings=app.state.settings
    env=os.environ
    checks={
        'staging_release':bool(current),
        'production_export_opt_in':env.get('CMS_ENABLE_PRODUCTION_EXPORT')=='true',
        'brand_trademark_clearance_confirmed':env.get('CMS_BRAND_CLEARANCE_CONFIRMED')=='true',
        'legal_review_confirmed':env.get('CMS_LEGAL_REVIEW_CONFIRMED')=='true',
        'smtp_configured':all([settings.smtp_host,settings.mail_from]),
        'public_api_https':env.get('CMS_PUBLIC_API_BASE','').startswith('https://'),
        'admin_secure_session':settings.session_secure and len(settings.secret_key)>=32,
        'database_production':not settings.database_url.startswith('sqlite:'),
        'website_canonical_https':False,
        'legal_pages_published':False,
        'legal_pages_not_placeholders':False,
    }
    try:checks['website_canonical_https']=canonical_base(db).startswith('https://')
    except HTTPException:pass
    legal={p.route:p for p in db.query(Page).filter(Page.route.in_(['/privacy/','/terms/'])).all()}
    checks['legal_pages_published']=all(legal.get(route) and legal[route].status=='published' for route in ['/privacy/','/terms/'])
    if current:
        source=[current/route.lstrip('/')/'index.html' for route in ['/privacy/','/terms/']]
        checks['legal_pages_not_placeholders']=all(p.is_file() and
            not re.search(r'DRAFT / LEGAL REVIEW REQUIRED|drafting placeholder|must be replaced|pending formal clearance',p.read_text(encoding='utf8'),re.I) for p in source)
    return {'ready':all(checks.values()),'checks':checks,'active_staging_release':current.name if current else None,
            'note':'Readiness checks are mechanical. Domain ownership, live mail deliverability, privacy counsel, trademark rights and end-to-end hosted acceptance require external verification.'}


@router.get('/integration/readiness')
def deployment_readiness(request:Request,actor=Depends(require_permission('content:read')),db:Session=Depends(get_db)):
    return readiness(request.app,db)


@router.post('/integration/export-production',dependencies=[Depends(require_csrf)])
def export_release(request:Request,actor=Depends(require_permission('content:publish')),db:Session=Depends(get_db)):
    if actor.role!='super_admin':raise HTTPException(403,'Only Super Admin may export a public release')
    state=readiness(request.app,db)
    if not state['ready']:
        raise HTTPException(409,detail={'message':'Production readiness gate blocked export','checks':state['checks']})
    root=request.app.state.publish_root
    with PUBLISH_LOCK:
        active=active_release(root)
        if not active:raise HTTPException(409,'No staging release')
        exports=root/'exports';exports.mkdir(exist_ok=True,parents=True)
        out=exports/('production-'+uuid.uuid4().hex)
        try:
            shutil.copytree(active,out)
            # Only approved, explicitly indexable pages carry a planned index directive.
            for page in out.rglob('index.html'):
                soup=BeautifulSoup(page.read_text(encoding='utf8'),'html.parser')
                robots=soup.find('meta',attrs={'name':'robots'})
                if robots and robots.get('data-planned-robots'):
                    robots['content']=robots.pop('data-planned-robots')
                from .phase6_renderer import serialize_html
                page.write_text(serialize_html(soup),encoding='utf8')
            base=canonical_base(db)
            (out/'robots.txt').write_text('User-agent: *\nAllow: /\nSitemap: '+base+'/sitemap.xml\n',encoding='utf8')
            (out/'manifest.json').write_text(json.dumps({'source_release':active.name,
                'exported_at':utcnow().isoformat()+'Z','status':'export_ready_not_deployed',
                'requires':'manual host deployment and live smoke test'},indent=2),encoding='utf8')
            audit(db,'production.exported',actor=actor.id,target_type='deployment',target_id=active.name,
                  export_id=out.name)
            db.commit()
            return {'status':'export_ready_not_deployed','folder':str(out),'source_release':active.name,
                    'next_step':'Deploy the export to your verified hosting account. No live website has been modified.'}
        except Exception:
            shutil.rmtree(out,ignore_errors=True)
            raise
