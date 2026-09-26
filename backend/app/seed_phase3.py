"""Idempotent draft-only import of V6 services, industries, insights and four existing V6 images.

Never seeds fake clients, consultant profiles, reviews, certifications or outcomes.
"""
from __future__ import annotations
import hashlib
import html
import json
import re
import uuid
from pathlib import Path
from bs4 import BeautifulSoup
from PIL import Image
from .config import Settings
from .db import make_engine, make_session_factory
from .models import CollectionEntry, MediaAsset, MediaUsage
from .phase3 import _thumbnail

SEED_ROOT=Path(__file__).resolve().parents[2]/'seed'
ASSETS=SEED_ROOT/'v6_assets'
V6=SEED_ROOT/'v6_page_content.json'
IMAGES={
    'executive-hero.webp':'Executive reviewing business intelligence in a modern office',
    'diagnostic-session.webp':'Business consulting discussion at a meeting table',
    'executive-city.webp':'Modern corporate meeting space overlooking a city',
    'assessment-workspace.webp':'Laptop and planning materials arranged on a business desk',
}
KINDS=(('service','/services/'),('industry','/industries/'),('insight','/insights/'))

def first_lead(source):
    for section in source['sections']:
        markup=section.get('content',{}).get('html','')
        if markup:
            lead=BeautifulSoup(markup,'html.parser').select_one('.lead')
            if lead:return lead.get_text(' ',strip=True)
    return source.get('meta_description','')

def clean_title(value):
    for suffix in [' AI & Business Consulting', ' Operations AI & Business Consulting',' Consulting']:
        if value.endswith(suffix):return value[:-len(suffix)]
    return value

def markdown_from_html(source,kind):
    parts=[]
    for section in source['sections']:
        markup=section.get('content',{}).get('html','')
        if not markup:continue
        soup=BeautifulSoup(markup,'html.parser')
        body=soup.select_one('.article-body') if kind=='insight' else soup
        if body is None:continue
        for el in body.find_all(['h2','h3','p']):
            if el.find_parent(['a','button']) or 'article-meta' in el.get('class',[]):continue
            text=el.get_text(' ',strip=True)
            if not text:continue
            if el.name=='h2':parts.append('## '+text)
            elif el.name=='h3':parts.append('### '+text)
            elif len(text)>65:parts.append(text)
    # Source markup has duplicated CTA text; avoid copying navigation into article body.
    return '\n\n'.join(parts)[:35000]

def seed(settings: Settings | None=None):
    settings=settings or Settings.from_env()
    engine=make_engine(settings.database_url)
    factory=make_session_factory(engine)
    media_root=Path(settings.media_root or (Path(settings.database_url.removeprefix('sqlite:///')).resolve().parent/'media') if settings.database_url.startswith('sqlite:///') else 'instance/media').resolve()
    media_root.mkdir(parents=True,exist_ok=True)
    pages=json.loads(V6.read_text(encoding='utf-8'))['pages']
    created={'services':0,'industries':0,'insights':0,'images':0}
    with factory() as db:
        image_by_name={}
        for name,alt in IMAGES.items():
            path=ASSETS/name
            raw=path.read_bytes()
            checksum=hashlib.sha256(raw).hexdigest()
            existing=db.query(MediaAsset).filter(MediaAsset.sha256==checksum, MediaAsset.kind=='image').first()
            if existing:
                image_by_name[name]=existing
                if not (media_root/(existing.storage_name+'.thumb.webp')).exists():
                    _thumbnail(raw,media_root,existing.storage_name,existing.mime_type)
                continue
            storage_name=str(uuid.uuid4())+'.webp'
            (media_root/storage_name).write_bytes(raw)
            _thumbnail(raw,media_root,storage_name,"image/webp")
            with Image.open(path) as image:width,height=image.size
            entry=MediaAsset(id=str(uuid.uuid4()),original_name=name,storage_name=storage_name,sha256=checksum,
                             mime_type='image/webp',kind='image',icon_style=None,byte_size=len(raw),width=width,height=height,
                             alt_text=alt,caption='',source_notes='Imported from the V6 website; verify image usage rights before launch.',
                             decorative=False,created_by=None)
            db.add(entry);db.flush();image_by_name[name]=entry;created['images']+=1
        for kind,prefix in KINDS:
            routes=[p for p in pages if p['route'].startswith(prefix) and p['route']!=prefix]
            for index,source in enumerate(routes):
                slug=source['route'].rstrip('/').split('/')[-1]
                if db.query(CollectionEntry).filter_by(kind=kind,slug=slug).first():continue
                summary=first_lead(source)
                body=markdown_from_html(source,kind)
                image=image_by_name.get('diagnostic-session.webp') if kind=='service' and slug=='business-diagnostics' else None
                if kind=='industry':image=image_by_name.get('executive-city.webp')
                item=CollectionEntry(id=str(uuid.uuid4()),kind=kind,title=clean_title(source['title']),slug=slug,
                                     summary=summary,body_markdown=body,content_json=json.dumps({'source':'V6 editorial import','source_route':source['route']},ensure_ascii=False),
                                     status='draft',sort_order=index,is_featured=False,hero_media_id=image.id if image else None,
                                     seo_title=source['seo_title'],meta_description=source['meta_description'])
                db.add(item);db.flush()
                if image:db.add(MediaUsage(id=str(uuid.uuid4()),media_id=image.id,owner_type='collection',owner_id=item.id,slot='hero'))
                created[{'service':'services','industry':'industries','insight':'insights'}[kind]]+=1
        db.commit()
    engine.dispose()
    return created

if __name__=='__main__':
    print(json.dumps(seed(),indent=2))
