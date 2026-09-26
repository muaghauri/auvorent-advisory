"""Phase 6: actual V6 renderer, public APIs, visual editor, and production guard."""
import json
from pathlib import Path
from bs4 import BeautifulSoup
from backend.app.seed_phase2 import seed as seed2
from backend.app.seed_phase3 import seed as seed3
from backend.app.seed_phase4 import seed as seed4
from backend.app.models import Page, User
from backend.app.security import hash_password
from backend.app.phase6_renderer import section_fields, render_section_fragment, clean_fragment
from backend.app.config import Settings
from fastapi.testclient import TestClient
import uuid


def authenticated(client):
    return {'X-CSRF-Token': client.csrf_token}


def approve_one(client,app,page):
    with app.state.db_factory() as db:
        reviewer=User(id=str(uuid.uuid4()),email='reviewer-six@example.com',full_name='Independent Reviewer',
          role='reviewer',password_hash=hash_password('Reviewer-P6-Test-2026!'),is_active=True,must_change_password=False)
        db.add(reviewer);db.commit()
    with TestClient(app) as reviewer_client:
        csrf=reviewer_client.get('/api/v1/auth/csrf').json()['csrf_token']
        r=reviewer_client.post('/api/v1/auth/login',json={'email':reviewer.email,'password':'Reviewer-P6-Test-2026!'},headers={'X-CSRF-Token':csrf})
        assert r.status_code==200,r.text
        submit=client.post(f'/api/v1/reviews/page/{page.id}/submit',headers=authenticated(client),json={})
        assert submit.status_code==200,submit.text
        review_id=submit.json()['review']['id']
        decision=reviewer_client.post(f'/api/v1/reviews/{review_id}/decision',headers={'X-CSRF-Token':csrf},json={'decision':'approve','note':'Validated original V6 copy and metadata'})
        assert decision.status_code==200,decision.text


def seed_instance(app,with_media=False):
    s=app.state.settings
    seed2(s)
    if with_media:seed3(s)
    with app.state.db_factory() as db: seed4(db)


def home(app):
    with app.state.db_factory() as db:
        p=db.query(Page).filter_by(route='/').first()
        db.expunge(p)
        return p


def build_one(logged_client,app,page):
    approve_one(logged_client,app,page)
    result=logged_client.post('/api/v1/publishing/build',headers=authenticated(logged_client),json={})
    assert result.status_code==200,result.text
    deployment=result.json()['deployment']
    assert deployment['status']=='completed',deployment
    return app.state.publish_root/'current'


def test_v6_full_design_preserved_and_site_bridge(logged_client,app):
    seed_instance(app)
    stage=build_one(logged_client,app,home(app))
    assert len(list(stage.rglob('index.html')))>=19
    assert (stage/'assets/images/executive-hero.webp').is_file()
    assert (stage/'assets/images/assessment-workspace.webp').is_file()
    assert (stage/'assets/cms-public.js').exists()
    assert (stage/'assets/cms-config.js').exists()
    assert '/api/v1/public/forms/strategy-consultation' in (stage/'assets/cms-public.js').read_text().replace("' + path", "' + path") or "forms/strategy-consultation" in (stage/'assets/cms-public.js').read_text()
    source=(stage/'index.html').read_text()
    dom=BeautifulSoup(source,'html.parser')
    assert dom.select_one('section.hero.executive-hero')
    assert len(dom.select('main > section'))==10
    assert len(dom.select('nav.desktop-nav a'))==5
    assert dom.select_one('header img')['src']=='/assets/logo.svg'
    assert dom.select_one('meta[name=robots]')['content']=='noindex,nofollow'
    assert dom.select_one('script[src="/assets/cms-public.js"]')
    assert dom.select_one('link[rel=canonical]')['href']=='https://auvorent.com/'
    assert (stage/'contact/index.html').exists()
    assert (stage/'assessment/index.html').exists()
    assert (stage/'robots.txt').read_text()=='User-agent: *\nDisallow: /\n'
    assert "connect-src 'self' http://127.0.0.1:8900;" in (stage/'_headers').read_text()


def test_visual_editor_updates_a_specific_v6_slot_without_damaging_markup(logged_client,app):
    seed_instance(app)
    p=home(app)
    info=logged_client.get(f'/api/v1/pages/{p.id}').json()['page']
    section=info['sections'][0]
    fields=logged_client.get(f'/api/v1/integration/sections/{section["id"]}/fields')
    assert fields.status_code==200
    slots=fields.json()['fields'];heading=next(x for x in slots if x['kind']=='text' and 'Turn business complexity' in x['value'])
    assert any(x['kind']=='image' for x in slots)
    payload={'text_overrides':{heading['key']:'Turn insight into a better operating business.'}}
    r=logged_client.patch(f'/api/v1/integration/sections/{section["id"]}/visual',json=payload,headers=authenticated(logged_client))
    assert r.status_code==200,r.text
    stage=build_one(logged_client,app,home(app))
    dom=BeautifulSoup((stage/'index.html').read_text(),'html.parser')
    h1=dom.select_one('h1')
    assert 'Turn insight into a better operating business.' in h1.get_text(' ',strip=True)
    assert dom.select_one('.executive-hero')
    assert dom.select_one('img[src="/assets/images/executive-hero.webp"]')
    assert 'data-cms-section' in dom.select_one('main > section').attrs


def test_editor_only_allows_approved_media_and_local_links(logged_client,app):
    seed_instance(app)
    p=home(app)
    section=logged_client.get(f'/api/v1/pages/{p.id}').json()['page']['sections'][0]
    endpoint=f'/api/v1/integration/sections/{section["id"]}/visual'
    image=logged_client.patch(endpoint,headers=authenticated(logged_client),json={'image_overrides':{'image_0':'https://malicious.example/i.png'}})
    assert image.status_code==422
    bad=logged_client.patch(endpoint,headers=authenticated(logged_client),json={'link_overrides':{'link_0':'javascript:alert(1)'}})
    assert bad.status_code==422
    invalid=logged_client.patch(endpoint,headers=authenticated(logged_client),json={'text_overrides':{'text_9000':'hello'}})
    assert invalid.status_code==422
    cleaned=clean_fragment('<section onclick="alert(1)"><h2>Hello</h2><img src="https://bad.example/i" onerror="alert(1)"><script>alert(1)</script></section>')
    assert 'onclick' not in cleaned and 'onerror' not in cleaned and '<script' not in cleaned and 'https://bad.example' not in cleaned


def test_public_form_inquiry_stored_but_not_falsely_claimed_delivered(client,app):
    seed_instance(app)
    schema=client.get('/api/v1/public/forms/strategy-consultation')
    assert schema.status_code==200
    assert any(f['label']=='Full name' for f in schema.json()['fields'])
    r=client.post('/api/v1/public/forms/strategy-consultation/submit',json={'data':{
        'name':'James Consultant','email':'james@example.com','company':'Acme Services','size':'15–49',
        'priority':'Operational inefficiency','message':'Please review our operating workflows, capacity and handoffs.'},
        'consent':True,'website':'','source_page':'/contact/'})
    assert r.status_code==202,r.text
    from backend.app.models import Inquiry,LeadSettings
    with app.state.db_factory() as db:
        inquiry=db.query(Inquiry).one();assert inquiry.email=='james@example.com'
        assert inquiry.notification_status!='sent'
        assert db.get(LeadSettings,'primary').recipient_email=='muaghauri@gmail.com'


def test_production_export_blocked_without_real_launch_gates(logged_client,app):
    seed_instance(app)
    stage=build_one(logged_client,app,home(app))
    result=logged_client.get('/api/v1/integration/readiness')
    assert result.status_code==200
    state=result.json()
    assert state['checks']['staging_release'] is True
    assert not state['ready']
    denied=logged_client.post('/api/v1/integration/export-production',headers=authenticated(logged_client),json={})
    assert denied.status_code==409
    assert (stage/'robots.txt').read_text().startswith('User-agent: *\nDisallow')


def test_full_website_seo_and_media_structure(logged_client,app):
    seed_instance(app,with_media=True)
    stage=build_one(logged_client,app,home(app))
    content=(stage/'about/index.html').read_text()
    assert 'Business insight' in content or 'Clear thinking' in content
    assert (stage/'assets/media').exists()
    assert len(list((stage/'assets/media').glob('*.webp')))>=4
    assert (stage/'sitemap.xml').exists()
    # V6 legal pages remain intentionally nonindexable until replaced and approved.
    for route in ['privacy','terms']:
        doc=BeautifulSoup((stage/route/'index.html').read_text(),'html.parser')
        assert 'noindex' in doc.select_one('meta[name=robots]')['content']


def test_private_preview_uses_actual_v6_page_design(logged_client,app):
    seed_instance(app)
    p=home(app)
    result=logged_client.post(f'/api/v1/preview/page/{p.id}',headers=authenticated(logged_client),json={})
    assert result.status_code==200
    url=result.json()['preview_url']
    doc=logged_client.get(url)
    assert doc.status_code==200
    assert 'Private CMS preview' in doc.text
    dom=BeautifulSoup(doc.text,'html.parser')
    assert dom.select_one('section.executive-hero')
    assert dom.select_one('nav.desktop-nav')
    assert logged_client.get('/assets/images/executive-hero.webp').status_code==200


def test_publishing_service_and_insight_collections_keeps_original_v6_shell(logged_client, app):
    """Collection edits must not degrade styled existing V6 pages into generic HTML."""
    from backend.app.models import CollectionEntry
    seed_instance(app,with_media=True)
    with app.state.db_factory() as db:
        service = db.query(CollectionEntry).filter_by(kind='service',slug='business-diagnostics').one()
        insight = db.query(CollectionEntry).filter_by(kind='insight',slug='diagnose-before-you-automate').one()
        service.summary = 'A specific operational diagnostic proposition for business owners.'
        service.body_markdown = '## What the diagnostic covers\n\nA focused analysis of operating constraints and decisions.'
        insight.title = 'Diagnose the Problem Before Buying Automation'
        insight.body_markdown = '## The first decision\n\nStart with current workflows and measurable constraints.'
        targets=[('service',service.id),('insight',insight.id)]
        db.commit()
    with app.state.db_factory() as db:
        reviewer=User(id=str(uuid.uuid4()),email='reviewer-collections@example.com',full_name='Independent Collections Reviewer',
            role='reviewer',password_hash=hash_password('Reviewer-Coll-P6-2026!'),is_active=True,must_change_password=False)
        db.add(reviewer);db.commit()
    with TestClient(app) as reviewer_client:
        csrf=reviewer_client.get('/api/v1/auth/csrf').json()['csrf_token']
        assert reviewer_client.post('/api/v1/auth/login',json={'email':reviewer.email,'password':'Reviewer-Coll-P6-2026!'},headers={'X-CSRF-Token':csrf}).status_code==200
        for kind,item_id in targets:
            submitted=logged_client.post(f'/api/v1/reviews/{kind}/{item_id}/submit',headers=authenticated(logged_client),json={})
            assert submitted.status_code==200,submitted.text
            decision=reviewer_client.post(f'/api/v1/reviews/{submitted.json()["review"]["id"]}/decision',headers={'X-CSRF-Token':csrf},json={'decision':'approve'})
            assert decision.status_code==200,decision.text
    published=logged_client.post('/api/v1/publishing/build',headers=authenticated(logged_client),json={})
    assert published.status_code==200,published.text
    release=app.state.publish_root/'current'
    service_doc=BeautifulSoup((release/'services/business-diagnostics/index.html').read_text(),'html.parser')
    article_doc=BeautifulSoup((release/'insights/diagnose-before-you-automate/index.html').read_text(),'html.parser')
    assert service_doc.select_one('nav.desktop-nav') and service_doc.select_one('header .brand img')
    assert 'business owners' in service_doc.select_one('.sub-hero .lead').get_text()
    assert 'What the diagnostic covers' in service_doc.select_one('.article-body').get_text()
    assert article_doc.select_one('.article-hero') and article_doc.select_one('nav.desktop-nav')
    assert 'Diagnose the Problem Before Buying Automation' in article_doc.select_one('h1').get_text()
    assert 'Start with current workflows' in article_doc.select_one('.article-body').get_text()
    assert article_doc.select_one('meta[name=robots]')['content']=='noindex,nofollow'
    assert (release/'index.html').read_text().lower().count('<!doctype html>')==1
    assert (release/'services/business-diagnostics/index.html').read_text().lower().count('<!doctype html>')==1
