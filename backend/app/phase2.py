from __future__ import annotations
import json, re, uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .models import Page, PageSection, NavigationItem, SiteSetting, ContentRevision, User, MediaUsage
from .schemas import CreatePageInput, UpdatePageInput, CreateSectionInput, UpdateSectionInput, ReorderSectionsInput, ReplaceNavigationInput, UpdateSettingsInput
from .security import get_db, require_csrf, require_permission, audit

router = APIRouter(prefix="/api/v1", tags=["Page Studio"])

def _page_out(p: Page, include_sections=False):
    data={"id":p.id,"route":p.route,"slug":p.slug,"title":p.title,"template":p.template,"status":p.status,"show_in_navigation":p.show_in_navigation,"is_indexable":p.is_indexable,"seo_title":p.seo_title,"meta_description":p.meta_description,"created_at":p.created_at.isoformat()+"Z","updated_at":p.updated_at.isoformat()+"Z"}
    if include_sections: data["sections"]=[_section_out(s) for s in p.sections]
    return data

def _section_out(s: PageSection):
    try: content=json.loads(s.content_json or "{}")
    except json.JSONDecodeError: content={}
    return {"id":s.id,"page_id":s.page_id,"section_key":s.section_key,"section_type":s.section_type,"position":s.position,"is_enabled":s.is_enabled,"content":content,"updated_at":s.updated_at.isoformat()+"Z"}

def _norm_route(route:str):
    route=(route or "").strip()
    if not route.startswith("/"): route="/"+route
    if route!="/" and not route.endswith("/"): route += "/"
    if "//" in route or any(c in route for c in "?#") or not re.fullmatch(r"/[A-Za-z0-9/_-]*", route): raise HTTPException(422,"Invalid route")
    return route

def _save_revision(db, entity_type, entity_id, snapshot, actor):
    db.add(ContentRevision(entity_type=entity_type, entity_id=entity_id, snapshot_json=json.dumps(snapshot, separators=(",",":"), ensure_ascii=False), actor_user_id=actor.id))

@router.get("/pages")
def list_pages(search:str=Query("",max_length=120), status:str=Query("",max_length=24), limit:int=Query(100,ge=1,le=200), offset:int=Query(0,ge=0), actor:User=Depends(require_permission("content:edit")), db:Session=Depends(get_db)):
    q=db.query(Page)
    if search: q=q.filter(Page.title.ilike(f"%{search}%") | Page.route.ilike(f"%{search}%"))
    if status: q=q.filter(Page.status==status)
    total=q.count(); rows=q.order_by(Page.route.asc()).offset(offset).limit(limit).all()
    return {"items":[_page_out(p) for p in rows],"total":total,"limit":limit,"offset":offset}

@router.post("/pages",status_code=201,dependencies=[Depends(require_csrf)])
def create_page(payload:CreatePageInput, actor:User=Depends(require_permission("content:edit")), db:Session=Depends(get_db)):
    if payload.status!='draft':raise HTTPException(422,'New pages must begin as drafts')
    route=_norm_route(payload.route)
    if db.query(Page).filter(Page.route==route).first(): raise HTTPException(409,"Route already exists")
    p=Page(id=str(uuid.uuid4()), route=route, slug=payload.slug.strip("/"), title=payload.title.strip(), template=payload.template, status=payload.status, show_in_navigation=payload.show_in_navigation, is_indexable=payload.is_indexable, seo_title=payload.seo_title, meta_description=payload.meta_description)
    db.add(p); audit(db,"page.created",actor=actor.id,target_type="page",target_id=p.id,route=route); db.commit(); return {"page":_page_out(p)}

@router.get("/pages/{page_id}")
def get_page(page_id:str, actor:User=Depends(require_permission("content:edit")), db:Session=Depends(get_db)):
    p=db.get(Page,page_id)
    if not p: raise HTTPException(404,"Page not found")
    return {"page":_page_out(p,True)}

@router.patch("/pages/{page_id}",dependencies=[Depends(require_csrf)])
def update_page(page_id:str,payload:UpdatePageInput,actor:User=Depends(require_permission("content:edit")),db:Session=Depends(get_db)):
    p=db.get(Page,page_id)
    if not p: raise HTTPException(404,"Page not found")
    _save_revision(db,"page",p.id,_page_out(p,True),actor)
    changes=payload.model_dump(exclude_unset=True)
    if changes.get('status') not in (None,'draft','unpublished','archived'):
        raise HTTPException(422,'Use the review/publishing workflow for approval or publication')
    from .phase5 import reset_approval
    reset_approval(db,'page',p.id)
    if 'route' in changes: changes["route"]=_norm_route(changes["route"])
    if "slug" in changes: changes["slug"]=changes["slug"].strip("/")
    for k,v in changes.items(): setattr(p,k,v)
    audit(db,"page.updated",actor=actor.id,target_type="page",target_id=p.id,fields=list(changes.keys()))
    try: db.commit()
    except IntegrityError: db.rollback(); raise HTTPException(409,"Route already exists")
    return {"page":_page_out(p,True)}

@router.delete("/pages/{page_id}",dependencies=[Depends(require_csrf)])
def delete_page(page_id:str,actor:User=Depends(require_permission("settings:manage")),db:Session=Depends(get_db)):
    p=db.get(Page,page_id)
    if not p: raise HTTPException(404,"Page not found")
    if p.status=="published": raise HTTPException(409,"Published pages must be unpublished before deletion")
    for section in p.sections:
        db.query(MediaUsage).filter(MediaUsage.owner_type=="page_section",MediaUsage.owner_id==section.id).delete()
    audit(db,"page.deleted",actor=actor.id,target_type="page",target_id=p.id,route=p.route); db.delete(p); db.commit(); return {"status":"deleted"}

@router.get("/pages/{page_id}/sections")
def list_sections(page_id:str,actor:User=Depends(require_permission("content:edit")),db:Session=Depends(get_db)):
    if not db.get(Page,page_id): raise HTTPException(404,"Page not found")
    rows=db.query(PageSection).filter(PageSection.page_id==page_id).order_by(PageSection.position.asc()).all(); return {"items":[_section_out(s) for s in rows]}

@router.post("/pages/{page_id}/sections",status_code=201,dependencies=[Depends(require_csrf)])
def create_section(page_id:str,payload:CreateSectionInput,actor:User=Depends(require_permission("content:edit")),db:Session=Depends(get_db)):
    if not db.get(Page,page_id): raise HTTPException(404,"Page not found")
    s=PageSection(id=str(uuid.uuid4()),page_id=page_id,section_key=payload.section_key,section_type=payload.section_type,position=payload.position,is_enabled=payload.is_enabled,content_json=json.dumps(payload.content,ensure_ascii=False))
    from .phase5 import reset_approval
    reset_approval(db,'page',page_id)
    db.add(s); audit(db,"section.created",actor=actor.id,target_type="section",target_id=s.id,page_id=page_id); db.commit(); return {"section":_section_out(s)}

@router.patch("/pages/{page_id}/sections/{section_id}",dependencies=[Depends(require_csrf)])
def update_section(page_id:str,section_id:str,payload:UpdateSectionInput,actor:User=Depends(require_permission("content:edit")),db:Session=Depends(get_db)):
    s=db.get(PageSection,section_id)
    if not s or s.page_id!=page_id: raise HTTPException(404,"Section not found")
    from .phase5 import reset_approval
    reset_approval(db,'page',page_id)
    _save_revision(db,"section",s.id,_section_out(s),actor)
    changes=payload.model_dump(exclude_unset=True)
    if "content" in changes: s.content_json=json.dumps(changes.pop("content"),ensure_ascii=False)
    for k,v in changes.items(): setattr(s,k,v)
    audit(db,"section.updated",actor=actor.id,target_type="section",target_id=s.id,fields=list(payload.model_dump(exclude_unset=True).keys())); db.commit(); return {"section":_section_out(s)}

@router.delete("/pages/{page_id}/sections/{section_id}",dependencies=[Depends(require_csrf)])
def delete_section(page_id:str,section_id:str,actor:User=Depends(require_permission("content:edit")),db:Session=Depends(get_db)):
    s=db.get(PageSection,section_id)
    if not s or s.page_id!=page_id: raise HTTPException(404,"Section not found")
    from .phase5 import reset_approval
    reset_approval(db,'page',page_id)
    db.query(MediaUsage).filter(MediaUsage.owner_type=="page_section",MediaUsage.owner_id==s.id).delete()
    audit(db,"section.deleted",actor=actor.id,target_type="section",target_id=s.id,page_id=page_id); db.delete(s); db.commit(); return {"status":"deleted"}

@router.post("/pages/{page_id}/sections/reorder",dependencies=[Depends(require_csrf)])
def reorder_sections(page_id:str,payload:ReorderSectionsInput,actor:User=Depends(require_permission("content:edit")),db:Session=Depends(get_db)):
    rows=db.query(PageSection).filter(PageSection.page_id==page_id).all(); by={r.id:r for r in rows}
    if set(payload.section_ids)!=set(by): raise HTTPException(422,"section_ids must contain every section exactly once")
    from .phase5 import reset_approval
    reset_approval(db,'page',page_id)
    for i,sid in enumerate(payload.section_ids): by[sid].position=i
    audit(db,"sections.reordered",actor=actor.id,target_type="page",target_id=page_id,count=len(by)); db.commit(); return {"items":[_section_out(by[sid]) for sid in payload.section_ids]}

@router.get("/navigation")
def get_navigation(actor:User=Depends(require_permission("content:edit")),db:Session=Depends(get_db)):
    rows=db.query(NavigationItem).order_by(NavigationItem.location,NavigationItem.position).all(); return {"items":[{"id":r.id,"location":r.location,"label":r.label,"url":r.url,"position":r.position,"is_visible":r.is_visible,"open_new_tab":r.open_new_tab} for r in rows]}

@router.patch("/navigation",dependencies=[Depends(require_csrf)])
def replace_navigation(payload:ReplaceNavigationInput,actor:User=Depends(require_permission("content:edit")),db:Session=Depends(get_db)):
    old=db.query(NavigationItem).all(); _save_revision(db,"navigation","global",[{"id":r.id,"location":r.location,"label":r.label,"url":r.url,"position":r.position,"is_visible":r.is_visible} for r in old],actor); db.query(NavigationItem).delete()
    for i,item in enumerate(payload.items): db.add(NavigationItem(id=item.id or str(uuid.uuid4()),location=item.location,label=item.label,url=item.url,position=item.position if item.position is not None else i,is_visible=item.is_visible,open_new_tab=item.open_new_tab))
    audit(db,"navigation.replaced",actor=actor.id,target_type="navigation",target_id="global",count=len(payload.items)); db.commit(); return get_navigation(actor,db)

@router.get("/settings")
def get_settings(actor:User=Depends(require_permission("content:edit")),db:Session=Depends(get_db)):
    rows=db.query(SiteSetting).order_by(SiteSetting.group_name,SiteSetting.key).all(); values={};
    for r in rows:
        try: values[r.key]=json.loads(r.value_json)
        except json.JSONDecodeError: values[r.key]=None
    return {"values":values,"items":[{"key":r.key,"group":r.group_name} for r in rows]}

@router.patch("/settings",dependencies=[Depends(require_csrf)])
def update_settings(payload:UpdateSettingsInput,actor:User=Depends(require_permission("settings:manage")),db:Session=Depends(get_db)):
    allowed={"brand.display_name":"brand","brand.tagline":"brand","brand.logo_dark":"brand","brand.logo_light":"brand","contact.primary_cta_label":"contact","contact.primary_cta_url":"contact","seo.default_title":"seo","seo.default_description":"seo","seo.canonical_base":"seo","footer.copyright":"footer"}
    unknown=[k for k in payload.values if k not in allowed]
    if unknown: raise HTTPException(422,detail={"message":"Unknown setting keys","keys":unknown})
    before={}
    for key,val in payload.values.items():
        row=db.get(SiteSetting,key); before[key]=json.loads(row.value_json) if row else None
        if not row: row=SiteSetting(key=key,group_name=allowed[key],value_json="null"); db.add(row)
        row.value_json=json.dumps(val,ensure_ascii=False); row.group_name=allowed[key]
    _save_revision(db,"settings","global",before,actor); audit(db,"settings.updated",actor=actor.id,target_type="settings",target_id="global",keys=list(payload.values)); db.commit(); return get_settings(actor,db)

@router.get("/content/revisions")
def revisions(entity_type:str=Query("",max_length=40),entity_id:str=Query("",max_length=80),limit:int=Query(50,ge=1,le=100),actor:User=Depends(require_permission("content:edit")),db:Session=Depends(get_db)):
    q=db.query(ContentRevision)
    if entity_type:q=q.filter(ContentRevision.entity_type==entity_type)
    if entity_id:q=q.filter(ContentRevision.entity_id==entity_id)
    rows=q.order_by(ContentRevision.id.desc()).limit(limit).all(); return {"items":[{"id":r.id,"entity_type":r.entity_type,"entity_id":r.entity_id,"actor_user_id":r.actor_user_id,"created_at":r.created_at.isoformat()+"Z"} for r in rows]}
