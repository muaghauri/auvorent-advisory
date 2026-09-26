from __future__ import annotations
import json, uuid
from pathlib import Path
from .config import Settings
from .db import make_engine, make_session_factory
from .models import Page, PageSection, NavigationItem, SiteSetting

SEED_FILE = Path(__file__).resolve().parents[2] / 'seed' / 'v6_page_content.json'


def seed(settings=None):
    settings = settings or Settings.from_env()
    dbf = make_session_factory(make_engine(settings.database_url))
    data = json.loads(SEED_FILE.read_text(encoding='utf8'))
    with dbf() as db:
        for source in data['pages']:
            page = db.query(Page).filter(Page.route == source['route']).first()
            if not page:
                route = source['route']
                page = Page(
                    id=str(uuid.uuid4()), route=route,
                    slug=route.strip('/').split('/')[-1] or 'home',
                    title=source['title'], template=source['template'], status='draft',
                    show_in_navigation=source['show_in_navigation'], is_indexable=False,
                    seo_title=source['seo_title'], meta_description=source['meta_description'],
                )
                db.add(page); db.flush()
            if not db.query(PageSection).filter(PageSection.page_id == page.id).count():
                for section in source['sections']:
                    db.add(PageSection(
                        id=str(uuid.uuid4()), page_id=page.id,
                        section_key=section['section_key'], section_type=section['section_type'],
                        position=section['position'], is_enabled=section['is_enabled'],
                        content_json=json.dumps(section['content'], ensure_ascii=False),
                    ))
        if not db.query(NavigationItem).count():
            for i, (label, url) in enumerate([
                ('Services','/services/'), ('Industries','/industries/'), ('Our approach','/our-approach/'),
                ('Insights','/insights/'), ('About','/about/')
            ]):
                db.add(NavigationItem(id=str(uuid.uuid4()), location='header', label=label, url=url, position=i, is_visible=True, open_new_tab=False))
        defaults = {
            'brand.display_name':'Auvorent Advisory',
            'brand.tagline':'Business clarity. Intelligent improvement. Measurable growth.',
            'brand.logo_dark':'/assets/logo.svg',
            'brand.logo_light':'/assets/logo-light.svg',
            'contact.primary_cta_label':'Request a strategy call',
            'contact.primary_cta_url':'/contact/',
            'seo.default_title':'Auvorent Advisory',
            'seo.default_description':'Business-first advisory for clearer decisions and measurable improvement.',
            'seo.canonical_base':'https://auvorent.com',
            'footer.copyright':'© 2026 Auvorent Advisory',
        }
        for key, value in defaults.items():
            if not db.get(SiteSetting, key):
                db.add(SiteSetting(key=key, value_json=json.dumps(value), group_name=key.split('.')[0]))
        db.commit()

if __name__ == '__main__':
    seed()
