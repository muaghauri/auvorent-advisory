import json
from backend.app.models import Page, PageSection, NavigationItem, SiteSetting


def csrf(client):
    return client.get('/api/v1/auth/csrf').json()['csrf_token']

def headers(client):
    return {'X-CSRF-Token': csrf(client)}


def test_create_update_page_and_sections(logged_client):
    r=logged_client.post('/api/v1/pages',headers=headers(logged_client),json={
        'title':'Test Advisory Page','route':'/test-advisory/','slug':'test-advisory','template':'standard'
    })
    assert r.status_code==201, r.text
    page=r.json()['page']; pid=page['id']
    assert page['status']=='draft'
    r=logged_client.post(f'/api/v1/pages/{pid}/sections',headers=headers(logged_client),json={
        'section_key':'hero','section_type':'hero','position':0,'content':{'heading':'Clearer decisions'}
    })
    assert r.status_code==201, r.text
    sec=r.json()['section']
    assert sec['content']['heading']=='Clearer decisions'
    r=logged_client.patch(f'/api/v1/pages/{pid}',headers=headers(logged_client),json={'seo_title':'Test SEO','meta_description':'A useful test page.'})
    assert r.status_code==200
    assert r.json()['page']['seo_title']=='Test SEO'
    r=logged_client.get(f'/api/v1/pages/{pid}')
    assert r.status_code==200
    assert len(r.json()['page']['sections'])==1


def test_route_collision_is_rejected(logged_client):
    payload={'title':'First','route':'/same/','slug':'same','template':'standard'}
    assert logged_client.post('/api/v1/pages',headers=headers(logged_client),json=payload).status_code==201
    payload['title']='Second'
    assert logged_client.post('/api/v1/pages',headers=headers(logged_client),json=payload).status_code==409


def test_navigation_replace(logged_client):
    items=[{'location':'header','label':'Services','url':'/services/','position':0,'is_visible':True,'open_new_tab':False},
           {'location':'header','label':'About','url':'/about/','position':1,'is_visible':True,'open_new_tab':False}]
    r=logged_client.patch('/api/v1/navigation',headers=headers(logged_client),json={'items':items})
    assert r.status_code==200, r.text
    out=logged_client.get('/api/v1/navigation').json()['items']
    assert [x['label'] for x in out]==['Services','About']


def test_settings_update_for_super_admin(logged_client):
    r=logged_client.patch('/api/v1/settings',headers=headers(logged_client),json={'values':{
        'brand.display_name':'Auvorent Advisory','contact.primary_cta_label':'Request a strategy call'
    }})
    assert r.status_code==200, r.text
    values=logged_client.get('/api/v1/settings').json()['values']
    assert values['brand.display_name']=='Auvorent Advisory'


def test_unknown_setting_rejected(logged_client):
    r=logged_client.patch('/api/v1/settings',headers=headers(logged_client),json={'values':{'secret.key':'x'}})
    assert r.status_code==422
