# Auvorent CMS Phase 4 API Contract

Prefix: `/api/v1`. OpenAPI details: `OPENAPI_PHASE4.json` or `/api/docs` in development.

## Authenticated endpoints

All mutation routes except public form/assessment submissions require the existing session cookie and `X-CSRF-Token` header from `GET /api/v1/auth/csrf`.

| Verb | Path | Purpose | Permission |
| --- | --- | --- | --- |
| GET | `/forms` | List definitions | Content Read |
| POST | `/forms` | Create form | Content Edit |
| GET | `/forms/{id}` | Full form schema | Content Read |
| PATCH | `/forms/{id}` | Update editable fields | Content Edit |
| DELETE | `/forms/{id}` | Delete disabled, unused form | Content Edit |
| GET | `/forms/settings` | Read recipient routing | Settings Manage |
| PATCH | `/forms/settings` | Change recipient, CC, subject and acknowledgment | Settings Manage |
| GET | `/inquiries` | Search and paginate saved inquiries | Inquiries Read |
| GET | `/inquiries/export` | CSV export (up to 5,000 rows) | Inquiries Read |
| GET | `/inquiries/assignees` | Active team members for assignment | Inquiries Read |
| GET | `/inquiries/{id}` | Full inquiry and private notes | Inquiries Read |
| PATCH | `/inquiries/{id}` | Status and assigned user | Inquiries Read |
| POST | `/inquiries/{id}/notes` | Add private note | Inquiries Read |
| POST | `/inquiries/{id}/resend` | Retry non-sent notification | Settings Manage |
| DELETE | `/inquiries/{id}` | Approved privacy/retention deletion | Settings Manage |
| GET | `/assessments` | List assessment definitions | Content Read |
| POST | `/assessments` | Create assessment | Content Edit |
| GET | `/assessments/{id}` | Full managed assessment | Content Read |
| PATCH | `/assessments/{id}` | Update questions, options, rules and CTA | Content Edit |
| GET | `/leads/summary` | Protected dashboard metrics | Inquiries Read |
| GET | `/leads/email-health` | Boolean sender setup (no secrets) | Settings Manage |

## Public endpoints

| Verb | Path | Response |
| --- | --- | --- |
| GET | `/public/forms/{slug}` | Active form schema (without destinations) |
| POST | `/public/forms/{slug}/submit` | `202` acceptance reference/message; never discloses email delivery state |
| GET | `/public/assessments/{slug}` | Active questionnaire without private guidance mappings |
| POST | `/public/assessments/{slug}/evaluate` | Preliminary recommendations and disclaimer; no stored answers |

### Submission example

```json
{
  "data": {
    "name": "Example Client",
    "email": "client@example.com",
    "company": "Sample Operations LLC",
    "size": "15–49",
    "priority": "Operational inefficiency",
    "message": "We need clearer reporting across our delivery team."
  },
  "consent": true,
  "website": "",
  "source_page": "/contact/",
  "utm": { "utm_source": "organic" }
}
```

The `website` property is an invisible honeypot. The real website connector must display it accessibly hidden from normal users. Use a same-origin reverse proxy to the private CMS API or set `CMS_PUBLIC_SITE_ORIGIN` to the exact published site origin for cross-origin browser requests.

### Assessment example

```json
{
  "answers": {
    "q1": "process",
    "q2": "handoffs",
    "q3": "partial",
    "q4": "pilot",
    "q5": "mixed",
    "q6": "shared",
    "q7": "roadmap"
  }
}
```

### Routing update

```json
{
  "recipient_email": "muaghauri@gmail.com",
  "cc": [],
  "reply_enabled": false,
  "subject_prefix": "Auvorent inquiry"
}
```

**Status semantics:** `202` means the inquiry was saved and notification was attempted. Only an authenticated administrator can view `notification_status` and retry a non-sent notification. `sent` confirms SMTP method completion, not final human receipt; test actual delivery before production launch.
