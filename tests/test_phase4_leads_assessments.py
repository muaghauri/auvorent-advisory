"""Phase 4 API security, content editing, lead intake, delivery semantics and assessment tests."""
from __future__ import annotations
import json
import pytest
from backend.app.models import Inquiry
from backend.app.seed_phase4 import seed
from tests.conftest import create_team_user


def headers(client):
    return {"X-CSRF-Token": client.csrf_token}


def seeded(app):
    with app.state.db_factory() as db: return seed(db)


def valid_lead():
    return {"data": {"name":"Ada Founder","email":"ada@example.com","company":"Acme Services",
                     "size":"15–49","priority":"Operational inefficiency",
                     "message":"We want to reduce avoidable handoffs in operations."},
            "consent":True,"website":"","source_page":"/contact/","utm":{"utm_source":"organic"}}


def test_phase4_seed_idempotent_and_public_form(app, client):
    assert seeded(app)=={"forms":1,"assessments":1}
    assert seeded(app)=={"forms":1,"assessments":1}
    f=client.get("/api/v1/public/forms/strategy-consultation")
    assert f.status_code==200
    assert len(f.json()["fields"])==6
    assert all(field["required"] for field in f.json()["fields"])
    assert "recipient_email" not in f.text
    assert client.get("/api/v1/public/forms/missing").status_code==404


def test_public_consent_required_field_and_choice_validation(app, client):
    seeded(app);base=valid_lead()
    for mutation in (
        {**base,"consent":False},
        {**base,"data":{**base["data"],"name":""}},
        {**base,"data":{**base["data"],"email":"not-an-email"}},
        {**base,"data":{**base["data"],"size":"99999"}},
        {**base,"data":{**base["data"],"rogue":"bad"}},
    ):
        assert client.post("/api/v1/public/forms/strategy-consultation/submit",json=mutation).status_code==422
    with app.state.db_factory() as db: assert db.query(Inquiry).count()==0


def test_honeypot_does_not_save_and_rate_limit(app, client):
    seeded(app);req=valid_lead();req["website"]="spam.example"
    response=client.post("/api/v1/public/forms/strategy-consultation/submit",json=req)
    assert response.status_code==202
    with app.state.db_factory() as db: assert db.query(Inquiry).count()==0
    for i in range(8):
        data=valid_lead();data["data"]["name"]+=str(i)
        assert client.post("/api/v1/public/forms/strategy-consultation/submit",json=data).status_code==202
    assert client.post("/api/v1/public/forms/strategy-consultation/submit",json=valid_lead()).status_code==429


def test_public_origin_restriction(app, client):
    seeded(app)
    wrong=client.post("/api/v1/public/forms/strategy-consultation/submit",json=valid_lead(),headers={"Origin":"https://untrusted.example"})
    assert wrong.status_code==403
    # A matching configured browser origin can be enabled using CMS_PUBLIC_SITE_ORIGIN.


def test_inquiry_persisted_even_with_missing_smtp(app, client, logged_client):
    seeded(app)
    response=client.post("/api/v1/public/forms/strategy-consultation/submit",json=valid_lead())
    assert response.status_code==202
    ref=response.json()["reference"]
    assert "notification_status" not in response.json()
    entry=logged_client.get("/api/v1/inquiries/"+ref)
    assert entry.status_code==200
    i=entry.json()["inquiry"]
    assert i["notification_status"]=="not_configured" and i["notification_attempts"]==1
    assert i["answers"]["email"]=="ada@example.com"
    assert logged_client.get("/api/v1/leads/summary").json()["total"]==1
    assert logged_client.get("/api/v1/leads/email-health").json()["configured"] is False


def test_email_sender_success_failure_retry_and_recipient_changes(app, logged_client):
    seeded(app)
    sent=[]
    def fake_sender(settings,routing,form,inquiry):
        sent.append((routing.recipient_email,routing.cc_json,inquiry.id))
        return "sent"
    app.state.notification_sender=fake_sender
    new_email=logged_client.patch("/api/v1/forms/settings",json={"recipient_email":"contact@example.com","cc":["owner@example.com"],"subject_prefix":"Business lead","reply_enabled":True},headers=headers(logged_client))
    assert new_email.status_code==200
    req=logged_client.post("/api/v1/public/forms/strategy-consultation/submit",json=valid_lead())
    ref=req.json()["reference"]
    assert logged_client.get("/api/v1/inquiries/"+ref).json()["inquiry"]["notification_status"]=="sent"
    assert sent==[("contact@example.com",'["owner@example.com"]',ref)]
    assert logged_client.post("/api/v1/inquiries/"+ref+"/resend",headers=headers(logged_client)).status_code==409
    del app.state.notification_sender


def test_failing_email_is_not_claimed_sent_and_retry(app, logged_client):
    seeded(app)
    def fails(*args): raise RuntimeError("provider secret do not log")
    app.state.notification_sender=fails
    request=logged_client.post("/api/v1/public/forms/strategy-consultation/submit",json=valid_lead())
    assert request.status_code==202
    ref=request.json()["reference"]
    detail=logged_client.get("/api/v1/inquiries/"+ref).json()["inquiry"]
    assert detail["notification_status"]=="failed"
    assert "provider secret" not in str(detail)
    app.state.notification_sender=lambda *args:"sent"
    retry=logged_client.post("/api/v1/inquiries/"+ref+"/resend",headers=headers(logged_client))
    assert retry.status_code==200 and retry.json()["notification_status"]=="sent"
    assert retry.json()["attempts"]==2
    del app.state.notification_sender


def test_form_crud_revision_and_inquiry_deletion_guard(app, logged_client):
    seeded(app)
    form=logged_client.get("/api/v1/forms").json()["items"][0]
    update=logged_client.patch("/api/v1/forms/"+form["id"],headers=headers(logged_client),json={"title":"Enhanced strategy conversation"})
    assert update.status_code==200
    assert update.json()["form"]["title"]=="Enhanced strategy conversation"
    created=logged_client.post("/api/v1/forms",headers=headers(logged_client),json={"slug":"second-form","title":"Secondary form","fields":[{"id":"email","label":"Email","type":"email","required":True}],"is_active":False})
    assert created.status_code==201
    assert logged_client.delete("/api/v1/forms/"+created.json()["form"]["id"],headers=headers(logged_client)).status_code==200
    r=logged_client.post("/api/v1/public/forms/strategy-consultation/submit",json=valid_lead());assert r.status_code==202
    assert logged_client.delete("/api/v1/forms/"+form["id"],headers=headers(logged_client)).status_code==409
    assert logged_client.delete("/api/v1/inquiries/"+r.json()["reference"],headers=headers(logged_client)).status_code==200


def test_routing_requires_admin_and_csrf(app, logged_client):
    seeded(app)
    assert logged_client.patch("/api/v1/forms/settings",json={"recipient_email":"inbox@example.com"}).status_code==403
    res=logged_client.get("/api/v1/inquiries/assignees")
    assert res.status_code==200 and len(res.json()["items"])>=1
    editor=create_team_user(logged_client,"editor@example.com",role="editor")
    from backend.app.models import User
    with app.state.db_factory() as db:
        account=db.get(User,editor["id"])
        account.must_change_password=False  # Simulates completion of required first-login password change.
        db.commit()
    token=logged_client.get("/api/v1/auth/csrf").json()["csrf_token"]
    logged_client.post("/api/v1/auth/logout",headers={"X-CSRF-Token":token})
    from tests.conftest import ADMIN_PASSWORD
    assert logged_client.post("/api/v1/auth/login",json={"email":editor["email"],"password":"Created-User-Pass!2026"},headers={"X-CSRF-Token":token}).status_code==200
    assert logged_client.get("/api/v1/forms/settings").status_code==403
    assert logged_client.get("/api/v1/inquiries").status_code==403
    assert logged_client.get("/api/v1/forms").status_code==200
    assert logged_client.get("/api/v1/public/forms/strategy-consultation").status_code==200


def test_inquiry_detail_status_notes_export_safe_csv(app, logged_client):
    seeded(app)
    req=valid_lead();req["data"]["name"]="=HYPERLINK(\"http://unsafe.example\")"
    result=logged_client.post("/api/v1/public/forms/strategy-consultation/submit",json=req)
    assert result.status_code==202
    ref=result.json()["reference"]
    assert logged_client.patch("/api/v1/inquiries/"+ref,json={"status":"qualified"},headers=headers(logged_client)).status_code==200
    assert logged_client.post("/api/v1/inquiries/"+ref+"/notes",json={"text":"Schedule a discovery call."},headers=headers(logged_client)).status_code==201
    assert len(logged_client.get("/api/v1/inquiries/"+ref).json()["notes"])==1
    csv_text=logged_client.get("/api/v1/inquiries/export").text
    assert "'=HYPERLINK" in csv_text and "qualified" in csv_text
    assert logged_client.get("/api/v1/inquiries?status=qualified").json()["total"]==1


def test_assessment_seed_api_private_rules_not_exposed_and_results(app, client, logged_client):
    seeded(app)
    a=client.get("/api/v1/public/assessments/business-optimization-check")
    assert a.status_code==200
    assert len(a.json()["questions"])==7
    assert "results" not in a.json()
    answer={"answers":{"q1":"process","q2":"handoffs","q3":"partial","q4":"pilot","q5":"mixed","q6":"shared","q7":"roadmap"}}
    res=client.post("/api/v1/public/assessments/business-optimization-check/evaluate",json=answer)
    assert res.status_code==200
    assert len(res.json()["recommendations"])>1
    assert "root cause" in res.json()["note"].lower()
    assert logged_client.get("/api/v1/inquiries").json()["total"]==0
    answer["answers"]["q1"]="unknown"
    assert client.post("/api/v1/public/assessments/business-optimization-check/evaluate",json=answer).status_code==422


def test_assessment_admin_changes_and_orphan_rule_rejected(app, logged_client):
    seeded(app)
    a=logged_client.get("/api/v1/assessments").json()["items"][0]
    assert logged_client.patch("/api/v1/assessments/"+a["id"],json={"title":"More informed decisions"},headers=headers(logged_client)).status_code==200
    bad=logged_client.patch("/api/v1/assessments/"+a["id"],json={"results":{"nonexistent.option":{"title":"Invalid","description":"This is an invalid orphaned rule."}}},headers=headers(logged_client))
    assert bad.status_code==422
    assert logged_client.get("/api/v1/assessments/"+a["id"]).json()["assessment"]["title"]=="More informed decisions"


def test_assessment_create_and_custom_response(app, logged_client):
    base={"slug":"operations-survey","title":"Operations survey","questions":[{"id":"q1","prompt":"What should improve?","options":[{"id":"speed","label":"Faster delivery"},{"id":"quality","label":"Better quality"}]}],
          "results":{"q1.speed":{"title":"Delivery workflow investigation","description":"Map current delivery steps before changing systems."}},"is_active":True}
    r=logged_client.post("/api/v1/assessments",headers=headers(logged_client),json=base)
    assert r.status_code==201,r.text
    d=logged_client.post("/api/v1/public/assessments/operations-survey/evaluate",json={"answers":{"q1":"speed"}})
    assert d.status_code==200 and d.json()["recommendations"][0]["title"]=="Delivery workflow investigation"


def test_new_endpoint_auth_enforcement(client):
    for path in ["/api/v1/inquiries", "/api/v1/leads/summary", "/api/v1/forms", "/api/v1/assessments", "/api/v1/forms/settings"]:
        assert client.get(path).status_code==401,path
    assert client.post("/api/v1/forms",json={"title":"Unauthorized","slug":"unauthorized","fields":[]}).status_code==403


def test_real_smtp_message_building_without_network(app, monkeypatch):
    """Exercise production transport code with a fake SMTP server; no real email is sent."""
    from dataclasses import replace
    from backend.app.phase4 import smtp_sender, lead_settings
    from backend.app.models import FormDefinition, Inquiry
    from backend.app.config import Settings
    seeded(app)
    messages=[]
    class FakeSMTP:
        def __init__(self, host, port, timeout):
            assert host=='smtp.test.example' and port==587 and timeout==10
        def __enter__(self): return self
        def __exit__(self,*args): return False
        def ehlo(self): pass
        def starttls(self): pass
        def login(self,username,password):
            assert username=='test-user' and password=='fake-password'
        def send_message(self,msg): messages.append(msg)
    monkeypatch.setattr('backend.app.phase4.smtplib.SMTP',FakeSMTP)
    settings=replace(app.state.settings,smtp_host='smtp.test.example',smtp_port=587,
                     smtp_username='test-user',smtp_password='fake-password',mail_from='leads@verified.example')
    with app.state.db_factory() as db:
        route=lead_settings(db)
        route.recipient_email='muaghauri@gmail.com'
        route.reply_enabled=False
        form=db.query(FormDefinition).first()
        inquiry=Inquiry(id='test-inquiry',form_id=form.id,ip_hash='a'*64,name='Ada Founder',email='ada@example.com',
                        company='Acme',priority='Operations',answers_json='{"message":"Investigate workflow friction"}',consent=True)
        assert smtp_sender(settings,route,form,inquiry)=='sent'
    assert len(messages)==1
    msg=messages[0]
    assert msg['To']=='muaghauri@gmail.com' and msg['From']=='leads@verified.example'
    assert msg['Reply-To']=='ada@example.com'
    assert 'Investigate workflow friction' in msg.get_content()


def test_valid_origin_and_safe_assessment_no_private_storage(app, client):
    from dataclasses import replace
    app.state.settings=replace(app.state.settings,public_site_origin='https://auvorent.example')
    seeded(app)
    allowed=client.post('/api/v1/public/forms/strategy-consultation/submit',json=valid_lead(),headers={'Origin':'https://auvorent.example'})
    assert allowed.status_code==202
    with app.state.db_factory() as db:
        assert db.query(Inquiry).count()==1
    result=client.post('/api/v1/public/assessments/business-optimization-check/evaluate',json={'answers':{
        'q1':'visibility','q2':'reporting','q3':'high','q4':'none','q5':'strong','q6':'leader','q7':'decisions'}})
    assert result.status_code==200
    with app.state.db_factory() as db:
        assert db.query(Inquiry).count()==1  # Assessment answers are not stored as personal leads.
