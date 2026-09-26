"""Phase 5 actual API and atomic local staging verification."""
import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from fastapi.testclient import TestClient
from backend.app.models import User, SiteSetting, PublishDeployment, Page
from backend.app.security import hash_password

META='Our advisors investigate operational bottlenecks and help business owners build practical improvement roadmaps backed by clear evidence.'
TITLE='Auvorent Advisory | Practical Business Optimization Consulting'


def call(c,method,path,body=None):
    headers={'X-CSRF-Token':c.csrf_token} if method.upper() not in ('GET','HEAD') else {}
    return c.request(method,path,json=body,headers=headers)


def canonical(app):
    with app.state.db_factory() as db:
        db.add(SiteSetting(key='seo.canonical_base',group_name='seo',value_json=json.dumps('https://auvorent.com')))
        db.commit()


def create_page(c,route='/strategy/'):  # controls remain drafts until gated approval
    r=call(c,'POST','/api/v1/pages',{'title':'Strategic Business Advisory','route':route,'slug':route.strip('/'),'template':'standard','status':'draft'})
    assert r.status_code==201,r.text
    pid=r.json()['page']['id']
    sec=call(c,'POST',f'/api/v1/pages/{pid}/sections',{'section_key':'intro','section_type':'hero','position':0,'is_enabled':True,
        'content':{'heading':'Strategic advice that begins with evidence','description':'We diagnose business bottlenecks.'}})
    assert sec.status_code==201,sec.text
    seo=call(c,'PUT',f'/api/v1/seo/page/{pid}',{'seo_title':TITLE,'meta_description':META,'robots_index':True,'robots_follow':True,
        'og_title':'Strategic business consulting','og_description':META,'schema_type':'WebPage','breadcrumb_title':'Strategy'})
    assert seo.status_code==200,seo.text
    return pid


def reviewer(app):
    with app.state.db_factory() as db:
        u=User(id=str(uuid.uuid4()),email='reviewer@example.com',full_name='Content Reviewer',
            password_hash=hash_password('Independent-Reviewer-2026!'),role='reviewer',is_active=True,must_change_password=False)
        db.add(u);db.commit()
    c=TestClient(app)
    csrf=c.get('/api/v1/auth/csrf').json()['csrf_token']
    assert c.post('/api/v1/auth/login',json={'email':'reviewer@example.com','password':'Independent-Reviewer-2026!'},headers={'X-CSRF-Token':csrf}).status_code==200
    c.csrf_token=csrf
    return c


def approve(c,reviewer_client,pid):
    r=call(c,'POST',f'/api/v1/reviews/page/{pid}/submit',{'note':'Please review the SEO and claims.'})
    assert r.status_code==200,r.text
    rid=r.json()['review']['id']
    r=call(reviewer_client,'POST',f'/api/v1/reviews/{rid}/decision',{'decision':'approve','note':'Content verified for local staging'})
    assert r.status_code==200,r.text
    return rid


def test_seo_validation_and_save(logged_client,app):
    canonical(app);pid=create_page(logged_client)
    d=logged_client.get(f'/api/v1/seo/page/{pid}').json()
    assert d['seo']['seo_title']==TITLE
    assert d['validation']['errors']==0
    result=logged_client.get('/api/v1/seo-issues').json()
    assert result['total']==1


def test_metadata_rejects_unsafe_canonical(logged_client,app):
    canonical(app);pid=create_page(logged_client)
    bad=call(logged_client,'PUT',f'/api/v1/seo/page/{pid}',{'seo_title':TITLE,'meta_description':META,
        'canonical_override':'javascript:alert(1)'})
    assert bad.status_code==422


def test_direct_publishing_blocked(logged_client,app):
    pid=create_page(logged_client)
    assert call(logged_client,'PATCH',f'/api/v1/pages/{pid}',{'status':'published'}).status_code==422
    assert call(logged_client,'PATCH',f'/api/v1/pages/{pid}',{'status':'approved'}).status_code==422


def test_two_person_review_and_stale_approval(logged_client,app):
    canonical(app);pid=create_page(logged_client)
    r=call(logged_client,'POST',f'/api/v1/reviews/page/{pid}/submit',{})
    assert r.status_code==200;r_id=r.json()['review']['id']
    own=call(logged_client,'POST',f'/api/v1/reviews/{r_id}/decision',{'decision':'approve'})
    assert own.status_code==403
    # A new content edit invalidates the outstanding review.
    assert call(logged_client,'PATCH',f'/api/v1/pages/{pid}',{'title':'Updated strategic advisory'}).status_code==200
    independent=reviewer(app)
    assert call(independent,'POST',f'/api/v1/reviews/{r_id}/decision',{'decision':'approve'}).status_code==409
    assert logged_client.get('/api/v1/reviews').json()['items'][0]['state']=='invalidated'
    independent.close()


def test_reviewer_cannot_publish(logged_client,app):
    canonical(app);pid=create_page(logged_client)
    independent=reviewer(app)
    approve(logged_client,independent,pid)
    assert call(independent,'POST','/api/v1/publishing/build',{}).status_code==403
    independent.close()


def test_private_preview_is_authenticated_and_snapshot_safe(logged_client,app,client):
    canonical(app);pid=create_page(logged_client)
    response=call(logged_client,'POST',f'/api/v1/preview/page/{pid}')
    assert response.status_code==200
    url=response.json()['preview_url']
    with TestClient(app) as anonymous:
        assert anonymous.get(url).status_code==401
    page=logged_client.get(url)
    assert page.status_code==200 and 'Private CMS preview' in page.text
    assert 'noindex' in page.text
    assert logged_client.get('/assets/style.css').status_code==200
    # User-supplied raw HTML is escaped/falls back to safe structured content.
    sections=logged_client.get(f'/api/v1/pages/{pid}/sections').json()['items']
    assert call(logged_client,'PATCH',f'/api/v1/pages/{pid}/sections/{sections[0]["id"]}',
          {'content':{'heading':'Safe text','html':'<script>alert(1)</script>'}}).status_code==200
    url2=call(logged_client,'POST',f'/api/v1/preview/page/{pid}').json()['preview_url']
    assert '<script>alert(1)</script>' not in logged_client.get(url2).text


def test_publish_atomic_and_metadata(logged_client,app):
    canonical(app);pid=create_page(logged_client);independent=reviewer(app);approve(logged_client,independent,pid)
    r=call(logged_client,'POST','/api/v1/publishing/build',{})
    assert r.status_code==200,r.text
    deploy=r.json()['deployment'];assert deploy['status']=='completed',deploy
    root=app.state.publish_root;site=root/'current'
    assert site.is_symlink() and (site/'strategy/index.html').exists()
    content=(site/'strategy/index.html').read_text()
    assert '<link rel="canonical" href="https://auvorent.com/strategy/">' in content
    assert 'property="og:title"' in content
    assert 'application/ld+json' in content
    assert 'name="robots" content="noindex,nofollow"' in content and 'data-planned-robots="index,follow"' in content
    assert 'https://auvorent.com/strategy/' in (site/'sitemap.xml').read_text()
    assert 'Disallow: /' in (site/'robots.txt').read_text()
    assert (site/'assets/style.css').exists()
    with app.state.db_factory() as db:assert db.get(Page,pid).status=='published'
    independent.close()


def test_failed_build_does_not_replace_existing_release(logged_client,app):
    canonical(app);pid=create_page(logged_client);independent=reviewer(app);approve(logged_client,independent,pid)
    assert call(logged_client,'POST','/api/v1/publishing/build',{}).json()['deployment']['status']=='completed'
    before=(app.state.publish_root/'current').resolve()
    # Make a second approved item but remove canonical base to force render failure.
    second=create_page(logged_client,'/operations/');approve(logged_client,independent,second)
    with app.state.db_factory() as db:
        setting=db.get(SiteSetting,'seo.canonical_base');setting.value_json=json.dumps('http://unsafe.example');db.commit()
    fail=call(logged_client,'POST','/api/v1/publishing/build',{}).json()['deployment']
    assert fail['status']=='failed' and (app.state.publish_root/'current').resolve()==before
    assert not (before/'operations/index.html').exists()
    independent.close()


def test_rollback_to_prior_immutable_release(logged_client,app):
    canonical(app);p1=create_page(logged_client);independent=reviewer(app);approve(logged_client,independent,p1)
    release1=call(logged_client,'POST','/api/v1/publishing/build',{}).json()['deployment']['release_id']
    p2=create_page(logged_client,'/operations/');approve(logged_client,independent,p2)
    release2=call(logged_client,'POST','/api/v1/publishing/build',{}).json()['deployment']['release_id']
    assert release1!=release2
    assert (app.state.publish_root/'current'/'operations/index.html').exists()
    assert call(logged_client,'POST','/api/v1/publishing/rollback/'+release1).status_code==200
    assert not (app.state.publish_root/'current'/'operations/index.html').exists()
    assert (app.state.publish_root/'releases'/release2/'operations/index.html').exists()
    independent.close()


def test_redirect_prevents_cycles(logged_client):
    one=call(logged_client,'POST','/api/v1/redirects',{'old_path':'/old/','new_path':'/new/','status_code':301})
    assert one.status_code==201,one.text
    loop=call(logged_client,'POST','/api/v1/redirects',{'old_path':'/new/','new_path':'/old/','status_code':301})
    assert loop.status_code==422
    outside=call(logged_client,'POST','/api/v1/redirects',{'old_path':'/redirect/','new_path':'https://evil.com','status_code':301})
    assert outside.status_code==422


def test_scheduled_local_publish_requires_due_runner(logged_client,app):
    canonical(app);pid=create_page(logged_client);independent=reviewer(app);approve(logged_client,independent,pid)
    future=(datetime.now(timezone.utc)+timedelta(hours=2)).isoformat()
    job=call(logged_client,'POST','/api/v1/publishing/build',{'scheduled_for':future}).json()['deployment']
    assert job['status']=='scheduled'
    assert logged_client.get('/api/v1/publishing/current').json()['release_id'] is None
    with app.state.db_factory() as db:
        db.get(PublishDeployment,job['id']).scheduled_for=datetime.utcnow()-timedelta(minutes=1);db.commit()
    ran=call(logged_client,'POST','/api/v1/publishing/run-due').json()['items']
    assert len(ran)==1 and ran[0]['status']=='completed'
    independent.close()


def test_no_direct_content_edit_after_approval(logged_client,app):
    canonical(app);pid=create_page(logged_client);independent=reviewer(app);approve(logged_client,independent,pid)
    result=call(logged_client,'PATCH',f'/api/v1/pages/{pid}',{'title':'New information'})
    assert result.status_code==200
    with app.state.db_factory() as db:assert db.get(Page,pid).status=='draft'
    job=call(logged_client,'POST','/api/v1/publishing/build',{}).json()['deployment']
    assert job['status']=='failed' and 'Nothing approved' in job['error_message']
    independent.close()


def test_version_history_restore_full_page(logged_client,app):
    pid=create_page(logged_client)
    before=logged_client.get(f'/api/v1/pages/{pid}').json()['page']['title']
    assert call(logged_client,'PATCH',f'/api/v1/pages/{pid}',{'title':'Updated consulting positioning'}).status_code==200
    history=logged_client.get(f'/api/v1/publishing/versions/page/{pid}').json()['items']
    page_rev=next(x for x in history if x['type']=='page')
    restored=call(logged_client,'POST',f'/api/v1/publishing/versions/{page_rev["id"]}/restore')
    assert restored.status_code==200,restored.text
    assert logged_client.get(f'/api/v1/pages/{pid}').json()['page']['title']==before
    assert logged_client.get(f'/api/v1/pages/{pid}').json()['page']['status']=='draft'


def test_section_history_and_restore(logged_client,app):
    pid=create_page(logged_client)
    sid=logged_client.get(f'/api/v1/pages/{pid}/sections').json()['items'][0]['id']
    edited=call(logged_client,'PATCH',f'/api/v1/pages/{pid}/sections/{sid}',
        {'content':{'heading':'New headline','description':'Updated copy'}})
    assert edited.status_code==200
    history=logged_client.get(f'/api/v1/publishing/versions/page/{pid}').json()['items']
    old=next(x for x in history if x['type']=='section')
    assert call(logged_client,'POST',f'/api/v1/publishing/versions/{old["id"]}/restore').status_code==200
    restored=logged_client.get(f'/api/v1/pages/{pid}/sections').json()['items'][0]
    assert restored['content']['heading']=='Strategic advice that begins with evidence'


def test_authenticated_staging_browser_uses_private_asset_routes(logged_client,app):
    canonical(app);pid=create_page(logged_client);independent=reviewer(app);approve(logged_client,independent,pid)
    call(logged_client,'POST','/api/v1/publishing/build',{})
    page=logged_client.get('/api/v1/publishing/site/strategy/')
    assert page.status_code==200
    assert '/api/v1/publishing/site/assets/style.css' in page.text
    assert page.headers['x-robots-tag']=='noindex, nofollow'
    css=logged_client.get('/api/v1/publishing/site/assets/style.css')
    assert css.status_code==200 and len(css.content)>3000
    with TestClient(app) as anonymous:
        assert anonymous.get('/api/v1/publishing/site/strategy/').status_code==401
    independent.close()
