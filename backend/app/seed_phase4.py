"""Rerunnable import of the actual V6 contact labels/options and seven assessment questions.

This is editorial seed data, not evidence of customer leads or delivered notifications.
"""
from __future__ import annotations
import json
import uuid
from .config import Settings
from .db import make_engine, make_session_factory
from .models import FormDefinition, AssessmentDefinition, LeadSettings

FORM_FIELDS = [
    {"id":"name","label":"Full name","type":"text","required":True,"placeholder":"Your name","max_length":100},
    {"id":"email","label":"Work email","type":"email","required":True,"placeholder":"you@company.com","max_length":180},
    {"id":"company","label":"Company","type":"text","required":True,"placeholder":"Company name","max_length":120},
    {"id":"size","label":"Team size","type":"select","required":True,"options":["1–14","15–49","50–149","150–499","500+"],"max_length":30},
    {"id":"priority","label":"What is your main priority?","type":"select","required":True,
     "options":["Operational inefficiency","Margins and delivery performance","Data and forecasting","AI opportunity assessment","Growth and strategic planning","Other"],"max_length":100},
    {"id":"message","label":"Tell us about the challenge","type":"textarea","required":True,
     "placeholder":"What is happening, and what would meaningful improvement look like?","max_length":3000},
]
QUESTIONS = [
    {"id":"q1","prompt":"What business challenge deserves the most attention right now?","options":[
        {"id":"performance","label":"We are growing but profitability and delivery consistency are under pressure."},
        {"id":"process","label":"Our operations rely too heavily on manual work and workarounds."},
        {"id":"visibility","label":"We cannot see performance trends early enough to act confidently."},
        {"id":"customers","label":"Our customer intake, response or retention process needs improvement."}]},
    {"id":"q2","prompt":"Where does the friction show up most often?","options":[
        {"id":"handoffs","label":"Handoffs, approvals and internal coordination."},
        {"id":"reporting","label":"Reporting, spreadsheets and pulling data together."},
        {"id":"customer","label":"Customer communication, onboarding and follow-up."},
        {"id":"planning","label":"Capacity, forecasting or unpredictable demand."}]},
    {"id":"q3","prompt":"How well can your team measure the current problem?","options":[
        {"id":"high","label":"We have reliable KPIs and a clear baseline."},
        {"id":"partial","label":"We have reports, but key metrics are scattered or delayed."},
        {"id":"low","label":"We rely mainly on spreadsheets and management judgment."},
        {"id":"unknown","label":"We have not defined consistent measures yet."}]},
    {"id":"q4","prompt":"How is AI being used in your organization today?","options":[
        {"id":"none","label":"We have not introduced AI in any meaningful way."},
        {"id":"individual","label":"Some people use standalone AI tools."},
        {"id":"pilot","label":"We have small pilots or limited automations."},
        {"id":"embedded","label":"AI supports multiple established business workflows."}]},
    {"id":"q5","prompt":"How ready is your operational data for deeper analysis?","options":[
        {"id":"strong","label":"Most critical data is accessible and consistently defined."},
        {"id":"mixed","label":"Useful data exists, but systems and definitions vary."},
        {"id":"weak","label":"Important information is incomplete, manual or hard to access."},
        {"id":"unsure","label":"We need to assess data quality first."}]},
    {"id":"q6","prompt":"Who could own improvements after an initial diagnostic?","options":[
        {"id":"leader","label":"A named executive or process owner has time and authority."},
        {"id":"shared","label":"Several leaders would need to coordinate."},
        {"id":"limited","label":"Our team has little spare implementation capacity."},
        {"id":"unclear","label":"We have not identified an accountable owner yet."}]},
    {"id":"q7","prompt":"What outcome would make an engagement valuable?","options":[
        {"id":"margin","label":"Improved margins and less avoidable work."},
        {"id":"experience","label":"Faster and more consistent customer delivery."},
        {"id":"decisions","label":"Better visibility, forecasting and management decisions."},
        {"id":"roadmap","label":"A credible roadmap for practical AI and operational change."}]},
]
RESULTS = {
    "q1.performance":{"title":"Margin and delivery diagnostic","description":"Compare revenue, effort, rework and handoffs before deciding which processes warrant changes."},
    "q1.process":{"title":"Workflow and bottleneck diagnostic","description":"Map a frequent workflow end to end and identify waiting, duplication and rework before selecting technology."},
    "q1.visibility":{"title":"Management reporting review","description":"Identify decisions requiring better information, examine data reliability and prioritize actionable measures."},
    "q1.customers":{"title":"Customer journey investigation","description":"Examine intake, handoffs and follow-up to identify potential points of service friction."},
    "q3.partial":{"title":"Reporting consistency","description":"Review fragmented KPIs and data definitions to establish a trustworthy baseline."},
    "q3.low":{"title":"Measurement baseline","description":"Define a few essential measures before planning forecasting or complex automation."},
    "q3.unknown":{"title":"Measurement baseline","description":"Agree on consistent performance measures before investing in additional technology."},
    "q5.mixed":{"title":"Data-quality assessment","description":"Assess integration gaps and inconsistent definitions across systems."},
    "q5.weak":{"title":"Data-quality assessment","description":"Review missing or manually managed information before selecting AI applications."},
    "q5.unsure":{"title":"Data-quality assessment","description":"Validate data completeness, provenance and ownership before any forecasting initiative."},
    "q6.limited":{"title":"Implementation ownership","description":"Agree on accountable delivery ownership and realistic capacity before launching change."},
    "q6.unclear":{"title":"Implementation ownership","description":"Identify a process owner and decision-making responsibilities before implementation."},
    "q7.decisions":{"title":"Decision-driven intelligence","description":"Start with the management decisions that better reporting and scenarios would improve."},
    "q7.roadmap":{"title":"Feasible optimization roadmap","description":"Prioritize use cases with clear benefits, costs, owners and risk assumptions."},
}


def seed(db):
    routing = db.get(LeadSettings, "primary")
    if not routing:
        db.add(LeadSettings(id="primary", recipient_email="muaghauri@gmail.com"))
    form = db.query(FormDefinition).filter_by(slug="strategy-consultation").first()
    if not form:
        form = FormDefinition(id=str(uuid.uuid4()), slug="strategy-consultation", title="Request a strategy conversation",
            intro="We use this information only to respond to your business inquiry. Avoid sensitive client or employee data.",
            fields_json=json.dumps(FORM_FIELDS, ensure_ascii=False),
            success_message="Your inquiry has been received. Thank you for reaching out.", is_active=True)
        db.add(form)
    assessment = db.query(AssessmentDefinition).filter_by(slug="business-optimization-check").first()
    if not assessment:
        assessment = AssessmentDefinition(id=str(uuid.uuid4()),slug="business-optimization-check",
            title="Business Optimization Check",
            intro="A brief, confidential self-reflection to highlight areas that may warrant deeper review.",
            disclaimer="Preliminary self-assessment only. A root-cause conclusion requires actual process data, stakeholder interviews and evidence. Forecasting recommendations depend on data quality and uncertainty.",
            questions_json=json.dumps(QUESTIONS,ensure_ascii=False),
            results_json=json.dumps(RESULTS,ensure_ascii=False),is_active=True,
            cta_label="Discuss your summary",cta_url="/contact/?from=assessment")
        db.add(assessment)
    db.commit()
    return {"forms":db.query(FormDefinition).count(),"assessments":db.query(AssessmentDefinition).count()}


def main():
    db_factory=make_session_factory(make_engine(Settings.from_env().database_url))
    with db_factory() as db:
        print("Phase 4 seeded:",seed(db))

if __name__=="__main__":main()
