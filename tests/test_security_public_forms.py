import pytest
from pydantic import ValidationError

from backend.app.phase4 import (
    AssessmentAnswers,
    AssessmentCreate,
    AssessmentOption,
    AssessmentQuestion,
    FormCreate,
    FormField,
    PublicFormSubmission,
)


def test_public_form_rejects_unexpected_top_level_fields():
    with pytest.raises(ValidationError):
        PublicFormSubmission.model_validate({
            "data": {"name": "Alice"},
            "consent": True,
            "website": "",
            "source_page": "/contact/",
            "utm": {},
            "admin": True,
        })


def test_public_form_rejects_unsafe_source_paths():
    for bad in (
        "https://evil.example/phish",
        "//evil.example/path",
        "/../../admin",
        "/contact/../admin",
        "/contact\\admin",
        "/contact/?next=https://evil.example",
    ):
        with pytest.raises(ValidationError):
            PublicFormSubmission(data={"name": "Alice"}, consent=True, source_page=bad)

    ok = PublicFormSubmission(data={"name": "Alice"}, consent=True, source_page="/contact/")
    assert ok.source_page == "/contact/"


def test_public_form_rejects_unknown_tracking_parameters():
    with pytest.raises(ValidationError):
        PublicFormSubmission(
            data={"name": "Alice"},
            consent=True,
            source_page="/contact/",
            utm={"redirect": "https://evil.example"},
        )

    ok = PublicFormSubmission(
        data={"name": "Alice"},
        consent=True,
        source_page="/contact/",
        utm={"utm_source": "linkedin", "utm_campaign": "executive-advisory"},
    )
    assert ok.utm["utm_source"] == "linkedin"


def test_public_form_rejects_control_characters_and_nested_values():
    with pytest.raises(ValidationError):
        PublicFormSubmission(data={"message": "hello\x00world"}, consent=True, source_page="/contact/")
    with pytest.raises(ValidationError):
        PublicFormSubmission(data={"message": {"nested": "object"}}, consent=True, source_page="/contact/")
    with pytest.raises(ValidationError):
        PublicFormSubmission(data={"message": ["unexpected", "array"]}, consent=True, source_page="/contact/")


def test_public_form_rejects_oversized_values_before_database_work():
    with pytest.raises(ValidationError):
        PublicFormSubmission(data={"message": "x" * 5001}, consent=True, source_page="/contact/")


def test_public_api_rejects_wrong_content_type_before_route_processing(client):
    response = client.post(
        "/api/v1/public/assessments/nonexistent/evaluate",
        content="answers=priority",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 415


def test_public_api_rejects_oversized_declared_request_before_json_parsing(client):
    response = client.post(
        "/api/v1/public/assessments/nonexistent/evaluate",
        content=b"x" * (129 * 1024),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 413


def test_form_builder_rejects_extra_fields_and_control_chars():
    field = FormField(id="name", label="Your name", type="text", required=True)
    form = FormCreate(slug="strategy-call", title="Strategy call", fields=[field])
    assert form.slug == "strategy-call"

    with pytest.raises(ValidationError):
        FormField.model_validate({
            "id": "name",
            "label": "Your name",
            "type": "text",
            "required": True,
            "unexpected": "value",
        })
    with pytest.raises(ValidationError):
        FormField(id="name", label="Name\x00", type="text")


def test_assessment_rejects_unsafe_cta_and_answer_identifiers():
    question = AssessmentQuestion(
        id="priority",
        prompt="What is your main priority?",
        options=[
            AssessmentOption(id="growth", label="Growth"),
            AssessmentOption(id="efficiency", label="Efficiency"),
        ],
    )
    with pytest.raises(ValidationError):
        AssessmentCreate(
            slug="business-check",
            title="Business check",
            questions=[question],
            cta_url="//evil.example",
        )
    with pytest.raises(ValidationError):
        AssessmentCreate(
            slug="business-check",
            title="Business check",
            questions=[question],
            cta_url="/contact/../admin",
        )
    with pytest.raises(ValidationError):
        AssessmentAnswers(answers={"priority": "growth<script>"})


def test_legitimate_form_submission_shape_still_validates():
    payload = PublicFormSubmission(
        data={
            "name": "Haris",
            "email": "haris@example.com",
            "company": "Mac",
            "message": "Testing the secure form pipeline",
        },
        consent=True,
        website="",
        source_page="/contact/",
        utm={"utm_source": "linkedin"},
    )
    assert payload.consent is True
    assert payload.data["company"] == "Mac"
