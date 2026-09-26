from __future__ import annotations
import io
import uuid
from PIL import Image
from backend.app.models import CollectionEntry, MediaAsset, Page, PageSection
from backend.app.seed_phase3 import seed
from backend.app.security import hash_password
from backend.app.models import User


def post(client,path,payload):
    return client.post('/api/v1'+path,headers={'X-CSRF-Token':client.csrf_token},json=payload)
def patch(client,path,payload):
    return client.patch('/api/v1'+path,headers={'X-CSRF-Token':client.csrf_token},json=payload)
def delete(client,path):
    return client.delete('/api/v1'+path,headers={'X-CSRF-Token':client.csrf_token})
def image_bytes(fmt='PNG',size=(140,96),color='teal'):
    colors={'teal':(24,118,95),'navy':(16,38,56)}
    im=Image.new('RGB',size,colors[color]);b=io.BytesIO();im.save(b,format=fmt);return b.getvalue()
def upload(client,name='business.png',raw=None,kind='image',alt='Business consulting meeting',extra=None):
    if raw is None:raw=image_bytes()
    data={'kind':kind,'alt_text':alt,**(extra or {})}
    media_type='image/png' if name.endswith('.png') else 'image/svg+xml' if name.endswith('.svg') else 'application/pdf' if name.endswith('.pdf') else 'image/jpeg'
    return client.post('/api/v1/media',data=data,files={'file':(name,raw,media_type)},headers={'X-CSRF-Token':client.csrf_token})
def new(client,kind='service',title='Business Diagnostics',slug='business-diagnostics',**changes):
    return post(client,'/collections/'+kind,{'title':title,'slug':slug,'summary':'Diagnose the current business situation.',**changes})

def test_phase3_routes_are_private_and_administration_is_role_gated(client,logged_client,app):
    from fastapi.testclient import TestClient
    with TestClient(app) as stranger:
        assert stranger.get('/api/v1/media').status_code == 401
        assert stranger.get('/api/v1/collections/service').status_code == 401
    assert logged_client.get('/api/v1/collections/service').status_code==200
    assert logged_client.get('/api/v1/media').status_code==200
    with app.state.db_factory() as db:
        db.add(User(id=str(uuid.uuid4()),email='viewer@example.com',full_name='Review Only',password_hash=hash_password('View-Password-2026-@'),role='viewer',is_active=True,must_change_password=False));db.commit()
    from fastapi.testclient import TestClient
    with TestClient(app) as viewer:
        token=viewer.get('/api/v1/auth/csrf').json()['csrf_token']
        assert viewer.post('/api/v1/auth/login',json={'email':'viewer@example.com','password':'View-Password-2026-@'},headers={'X-CSRF-Token':token}).status_code==200
        assert viewer.get('/api/v1/collections/service').status_code==200
        assert viewer.get('/api/v1/media').status_code==200
        assert viewer.post('/api/v1/collections/service',json={'title':'Read only','slug':'read-only'},headers={'X-CSRF-Token':token}).status_code==403
        assert viewer.post('/api/v1/media',data={'kind':'image'},files={'file':('x.png',image_bytes(),'image/png')},headers={'X-CSRF-Token':token}).status_code==403

def test_collections_crud_stable_ids_revisions_and_aliases(logged_client):
    c=logged_client
    result=new(c);assert result.status_code==201,result.text
    item=result.json()['item'];id=item['id']
    assert c.get('/api/v1/services').json()['total']==1
    assert c.get('/api/v1/collections/service/'+id).json()['item']['title']=='Business Diagnostics'
    res=patch(c,'/collections/service/'+id,{'summary':'New carefully reviewed business summary','is_featured':True,'content':{'deliverables':['Diagnostic report','Roadmap']}})
    assert res.status_code==200,res.text
    assert res.json()['item']['content']['deliverables']==['Diagnostic report','Roadmap']
    assert c.get('/api/v1/content/revisions?entity_type=service&entity_id='+id).json()['items']
    assert delete(c,'/services/'+id).status_code==200
    assert c.get('/api/v1/services').json()['total']==0

def test_slug_uniqueness_kind_scoped_and_html_rejected(logged_client):
    c=logged_client
    assert new(c).status_code==201
    assert new(c).status_code==409
    assert new(c,kind='industry',title='Business Diagnostics',slug='business-diagnostics').status_code==201
    assert new(c,title='<script>alert(1)</script>',slug='danger').status_code==422
    assert new(c,title='Unsafe Body',slug='unsafe-body',body_markdown='[click](javascript:alert(1))').status_code==422
    assert new(c,title='Unsafe JSON',slug='unsafe-json',content={'description':'<img onerror=alert(1)>'}).status_code==422
    assert new(c,title='Premature publish',slug='published',status='published').status_code==422

def test_relationships_author_validation_delete_guard(logged_client):
    c=logged_client
    article=new(c,'insight','Why Diagnose Before Automation','diagnose-before-automation').json()['item']
    author=new(c,'author','Named Author','named-author').json()['item']
    industry=new(c,'industry','Professional Services','professional-services').json()['item']
    assert post(c,f"/collections/insight/{article['id']}/relationships",{'target_id':industry['id'],'relation':'author'}).status_code==422
    linked=post(c,f"/collections/insight/{article['id']}/relationships",{'target_id':author['id'],'relation':'author'})
    assert linked.status_code==201,linked.text
    assert post(c,f"/collections/insight/{article['id']}/relationships",{'target_id':author['id'],'relation':'author'}).status_code==409
    assert delete(c,f"/authors/{author['id']}").status_code==409
    rel=linked.json()['relationship']['id']
    assert delete(c,f"/collections/insight/{article['id']}/relationships/{rel}").status_code==200
    assert delete(c,f"/authors/{author['id']}").status_code==200

def test_media_image_upload_thumbnail_protected_and_replace(logged_client,app):
    c=logged_client
    result=upload(c)
    assert result.status_code==201,result.text
    item=result.json()['media'];mid=item['id'];assert item['width']==140 and item['height']==96
    assert c.get('/api/v1/media/'+mid+'/file').content==image_bytes()
    assert c.get('/api/v1/media/'+mid+'/thumbnail').status_code==200
    assert c.get('/api/v1/media/'+mid+'/thumbnail').headers['content-type']=='image/webp'
    assert (app.state.media_root).is_dir()
    replaced=c.post('/api/v1/media/'+mid+'/replace',files={'file':('replacement.png',image_bytes(color='navy'),'image/png')},headers={'X-CSRF-Token':c.csrf_token})
    assert replaced.status_code==200,replaced.text
    assert replaced.json()['media']['id']==mid
    assert c.get('/api/v1/media/'+mid+'/file').content==image_bytes(color='navy')
    assert delete(c,'/media/'+mid).status_code==200
    assert c.get('/api/v1/media/'+mid+'/file').status_code==404

def test_media_alt_required_mime_verified_and_upload_size(logged_client):
    c=logged_client
    assert upload(c,alt='').status_code==422
    assert upload(c,alt='',extra={'decorative':'true'}).status_code==201
    assert upload(c,name='corrupt.png',raw=b'not-an-image').status_code==422
    assert upload(c,name='a.pdf',raw=image_bytes(),kind='document',alt='').status_code==422
    assert upload(c,name='a.png',raw=b'x'*(10*1024*1024+1)).status_code==413

def test_theme_only_svg_and_forbidden_external_references(logged_client):
    c=logged_client
    good=b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24"><path d="M2 3 L19 20" stroke="#18765F" fill="none" stroke-width="2"/></svg>'
    valid=upload(c,name='root-cause.svg',raw=good,kind='icon',alt='',extra={'icon_style':'line'})
    assert valid.status_code==201,valid.text
    icon=valid.json()['media']; assert icon['icon_style']=='line'
    assert b'<script' not in c.get('/api/v1/media/'+icon['id']+'/file').content
    scripts=b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><script>alert(1)</script></svg>'
    assert upload(c,name='bad.svg',raw=scripts,kind='icon').status_code==422
    wrong=b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><rect width="10" height="10" fill="#FF00FF" /></svg>'
    assert upload(c,name='wrong.svg',raw=wrong,kind='icon').status_code==422
    ref=b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><image href="http://example.com/i" /></svg>'
    assert upload(c,name='external.svg',raw=ref,kind='icon').status_code==422

def test_collection_media_references_and_usage_guards(logged_client):
    c=logged_client
    img=upload(c).json()['media']
    created=new(c,hero_media_id=img['id'])
    assert created.status_code==201,created.text
    record=created.json()['item']
    usages=c.get('/api/v1/media/'+img['id']+'/usages').json()['items']
    assert len(usages)==1 and usages[0]['slot']=='hero'
    assert delete(c,'/media/'+img['id']).status_code==409
    assert patch(c,'/collections/service/'+record['id'],{'hero_media_id':None}).status_code==200
    assert c.get('/api/v1/media/'+img['id']+'/usages').json()['items']==[]
    assert delete(c,'/media/'+img['id']).status_code==200

def test_assign_page_section_media_and_prevent_wrong_slot(logged_client,app):
    c=logged_client
    with app.state.db_factory() as db:
        p=Page(id=str(uuid.uuid4()),route='/test/',slug='test',title='Test',template='standard',status='draft',show_in_navigation=False,is_indexable=False,seo_title='',meta_description='')
        db.add(p);db.flush()
        s=PageSection(id=str(uuid.uuid4()),page_id=p.id,section_key='test',section_type='split_content',position=0,content_json='{}')
        db.add(s);db.commit();sid=s.id
    img=upload(c).json()['media'];mid=img['id']
    assert post(c,f'/media/{mid}/usages',{'owner_type':'page_section','owner_id':sid,'slot':'icon'}).status_code==422
    assigned=post(c,f'/media/{mid}/usages',{'owner_type':'page_section','owner_id':sid,'slot':'illustration'})
    assert assigned.status_code==201,assigned.text
    assert delete(c,'/media/'+mid).status_code==409
    assert delete(c,f"/media/{mid}/usages/{assigned.json()['usage']['id']}").status_code==200
    assert delete(c,'/media/'+mid).status_code==200

def test_seed_v6_collections_and_media_idempotently(app):
    a=seed(app.state.settings)
    assert a=={'services':4,'industries':2,'insights':3,'images':4}
    b=seed(app.state.settings)
    assert b=={'services':0,'industries':0,'insights':0,'images':0}
    with app.state.db_factory() as db:
        assert db.query(CollectionEntry).count()==9
        assert db.query(MediaAsset).count()==4
        assert all(x.status=='draft' for x in db.query(CollectionEntry).all())
        assert all(x.source_notes for x in db.query(MediaAsset).all())

def test_deleting_page_section_cleans_media_usage(logged_client,app):
    c=logged_client
    with app.state.db_factory() as db:
        page=Page(id=str(uuid.uuid4()),route='/temporary/',slug='temporary',title='Temporary page',template='standard',status='draft',show_in_navigation=False,is_indexable=False,seo_title='',meta_description='')
        db.add(page);db.flush()
        section=PageSection(id=str(uuid.uuid4()),page_id=page.id,section_key='temporary',section_type='split_content',position=0,content_json='{}')
        db.add(section);db.commit();pid=page.id;sid=section.id
    mid=upload(c).json()['media']['id']
    assigned=post(c,f'/media/{mid}/usages',{'owner_type':'page_section','owner_id':sid,'slot':'image'})
    assert assigned.status_code==201,assigned.text
    assert delete(c,f'/media/{mid}').status_code==409
    removed=delete(c,f'/pages/{pid}/sections/{sid}')
    assert removed.status_code==200,removed.text
    assert c.get(f'/api/v1/media/{mid}/usages').json()['items']==[]
    assert delete(c,f'/media/{mid}').status_code==200
