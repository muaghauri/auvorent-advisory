import json
import uuid

from backend.app import phase6
from backend.app.models import ContentRevision, EditorialReview, Page, PublishDeployment, User
from backend.app.phase5 import fingerprint
from backend.app.seed_phase2 import seed as seed_pages


def call(client, method, path, body=None):
    headers={"X-CSRF-Token":client.csrf_token} if method.upper() not in {"GET","HEAD"} else {}
    return client.request(method,path,json=body,headers=headers)


def test_private_preview_rejects_malformed_tokens_before_lookup(logged_client):
    assert logged_client.get('/api/v1/preview/view/short').status_code == 404
    assert logged_client.get('/api/v1/preview/view/' + ('A' * 129)).status_code == 404
    assert logged_client.get('/api/v1/preview/view/' + ('A' * 31) + '!').status_code == 404


def test_current_release_does_not_disclose_local_filesystem_path(logged_client):
    result=logged_client.get('/api/v1/publishing/current')
    assert result.status_code == 200
    body=result.json()
    assert 'release_id' in body
    assert 'local_path' not in body


def test_deployment_history_filters_legacy_path_and_raw_error_details(logged_client,app):
    with app.state.db_factory() as db:
        job=PublishDeployment(
            id=str(uuid.uuid4()),
            release_id=None,
            status='failed',
            environment='local_staging',
            requested_by='security-test',
            report_json=json.dumps({
                'release_id':'abc',
                'published_count':1,
                'output_dir':'/srv/private/releases/secret',
                'unexpected_internal_path':'/etc/passwd',
            }),
            error_message='OSError: failed at /srv/private/releases/secret using hidden runtime data',
        )
        db.add(job);db.commit()
    result=logged_client.get('/api/v1/publishing/deployments')
    assert result.status_code == 200
    item=next(x for x in result.json()['items'] if x['status']=='failed')
    assert 'output_dir' not in item['report']
    assert 'unexpected_internal_path' not in item['report']
    assert '/srv/' not in (item['error_message'] or '')
    assert item['error_message']=='Publication failed safely; no staging release was changed'


def test_review_decision_schema_rejects_extra_fields_and_oversized_notes(logged_client):
    fake=str(uuid.uuid4())
    extra=call(logged_client,'POST',f'/api/v1/reviews/{fake}/decision',{
        'decision':'approve','note':'ok','unexpected':'not allowed'
    })
    assert extra.status_code == 422
    oversized=call(logged_client,'POST',f'/api/v1/reviews/{fake}/decision',{
        'decision':'approve','note':'x' * 1001
    })
    assert oversized.status_code == 422


def test_rollback_rejects_unmanaged_release_directory(logged_client,app):
    release_id='a' * 32
    target=app.state.publish_root/'releases'/release_id
    target.mkdir(parents=True,exist_ok=True)
    (target/'manifest.json').write_text(json.dumps({
        'release_id':release_id,
        'environment':'local_staging',
    }),encoding='utf-8')
    response=call(logged_client,'POST','/api/v1/publishing/rollback/'+release_id)
    assert response.status_code == 404


def test_staging_browser_rechecks_directory_index_symlink(logged_client,app):
    release_id='b' * 32
    release=app.state.publish_root/'releases'/release_id
    release.mkdir(parents=True,exist_ok=True)
    secret=app.state.publish_root/'outside-secret.txt'
    secret.write_text('must-not-be-served',encoding='utf-8')
    nested=release/'escape'
    nested.mkdir()
    (nested/'index.html').symlink_to(secret)
    current=app.state.publish_root/'current'
    current.parent.mkdir(parents=True,exist_ok=True)
    current.symlink_to(release.resolve(),target_is_directory=True)
    response=logged_client.get('/api/v1/publishing/site/escape/')
    assert response.status_code == 404
    assert 'must-not-be-served' not in response.text


def test_production_export_rejects_symlinked_staging_tree(logged_client,app,monkeypatch):
    release_id='c' * 32
    release=app.state.publish_root/'releases'/release_id
    release.mkdir(parents=True,exist_ok=True)
    (release/'index.html').write_text('<!doctype html><title>safe</title>',encoding='utf-8')
    outside=app.state.publish_root/'outside-export-secret.txt'
    outside.write_text('must-never-reach-provider',encoding='utf-8')
    (release/'assets').mkdir()
    (release/'assets'/'escape.txt').symlink_to(outside)
    current=app.state.publish_root/'current'
    current.parent.mkdir(parents=True,exist_ok=True)
    current.symlink_to(release.resolve(),target_is_directory=True)
    monkeypatch.setattr(phase6,'readiness',lambda app,db:{'ready':True,'checks':{}})
    response=call(logged_client,'POST','/api/v1/integration/export-production',{})
    assert response.status_code == 409
    assert 'integrity check failed' in response.text.lower()


def test_restore_revalidates_legacy_unsafe_seo_snapshot(logged_client,app):
    seed_pages(app.state.settings)
    with app.state.db_factory() as db:
        page=db.query(Page).filter_by(route='/').one()
        revision=ContentRevision(
            entity_type='seo',
            entity_id=page.id,
            snapshot_json=json.dumps({
                'seo_title':'Safe title',
                'meta_description':'Safe description',
                'canonical_override':'javascript:alert(1)',
                'robots_index':False,
                'robots_follow':True,
                'og_title':'',
                'og_description':'',
                'og_image_media_id':None,
                'schema_type':'WebPage',
                'breadcrumb_title':'',
            }),
            actor_user_id=None,
        )
        db.add(revision);db.commit();revision_id=revision.id
    response=call(logged_client,'POST',f'/api/v1/publishing/versions/{revision_id}/restore',{})
    assert response.status_code == 422


def test_new_publish_prunes_only_previously_managed_stale_route(logged_client,app):
    seed_pages(app.state.settings)
    with app.state.db_factory() as db:
        owner=db.query(User).filter_by(role='super_admin').first()
        home=db.query(Page).filter_by(route='/').one()
        about=db.query(Page).filter_by(route='/about/').one()
        home.status='approved'
        db.flush()
        db.add(EditorialReview(
            id=str(uuid.uuid4()),entity_type='page',entity_id=home.id,state='approved',
            content_hash=fingerprint(db,'page',home.id),requested_by=owner.id,reviewed_by=owner.id,
        ))
        db.commit()
    first=call(logged_client,'POST','/api/v1/publishing/build',{})
    assert first.status_code == 200 and first.json()['deployment']['status']=='completed'
    release=app.state.publish_root/'current'
    assert (release/'index.html').is_file()
    # Baseline pages that never entered the CMS publish lifecycle remain intact.
    assert (release/'about/index.html').is_file()

    with app.state.db_factory() as db:
        home=db.query(Page).filter_by(route='/').one()
        about=db.query(Page).filter_by(route='/about/').one()
        home.status='draft'
        about.status='approved'
        db.flush()
        db.add(EditorialReview(
            id=str(uuid.uuid4()),entity_type='page',entity_id=about.id,state='approved',
            content_hash=fingerprint(db,'page',about.id),requested_by=owner.id,reviewed_by=owner.id,
        ))
        db.commit()
    second=call(logged_client,'POST','/api/v1/publishing/build',{})
    assert second.status_code == 200 and second.json()['deployment']['status']=='completed'
    release=app.state.publish_root/'current'
    assert not (release/'index.html').exists()
    assert (release/'about/index.html').is_file()
    manifest=json.loads((release/'manifest.json').read_text(encoding='utf-8'))
    assert not any(item.get('route')=='/' for item in manifest['published'])
    assert any(item.get('route')=='/about/' for item in manifest['published'])
