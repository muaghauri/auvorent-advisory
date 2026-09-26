# Auvorent CMS — Phase 4 Implementation Specification

**Module:** Leads, Forms & Assessments  
**Dependency:** Phase 3 CMS (included in package)  
**Status:** Implemented as independently testable CMS APIs + private administration UI; no public V6 integration or production SMTP credentials bundled.

## Scope delivered

| Submodule | Admin functions | Database entities |
| --- | --- | --- |
| Form Builder | List/create/edit/deactivate/delete unused forms; add/edit/reorder fields; select choices; consent enforced by API | `cms_forms` |
| Notification settings | Update primary recipient, CC, subject prefix, optional acknowledgment | `cms_lead_settings` |
| Lead Inbox | Search/filter/view, update status, assign active user, add private notes, export CSV, retry failed email and delete on approved retention request | `cms_inquiries`, `cms_inquiry_notes` |
| Business Optimization Check | Manage 7 V6 question themes, choices, preliminary guidance rules, CTA, visibility | `cms_assessments` |

The migration `0004_leads_assessments` adds five new entities and retains all earlier tables, keys and routes.

## Design principles

- Public client forms expose **only** field definitions, not email routing, credentials or inquiry data.
- Admin operations require existing authenticated sessions, RBAC and CSRF; email routing restricted to Admin and Super Admin.
- Public submissions require consent, ignore filled honeypots and validate editable schemas **server-side**. Field/choice tampering is rejected.
- Incoming IP address is **not** saved verbatim: a SHA-256 hash of application secret plus peer address is used for one-hour throttling. Configure a trusted ingress/reverse proxy in production; never trust arbitrary `X-Forwarded-For` headers.
- Only requests with the configured exact `CMS_PUBLIC_SITE_ORIGIN` may carry a browser Origin. API rate-limit and ingress/WAF protection remain important against automated server-side traffic.
- No HTML from visitor fields is injected into the admin UI (text-only DOM rendering). Spreadsheet CSV values with formula-leading characters are prefixed to prevent CSV formula execution.
- Mail failures do not lose inquiries. Notification status and attempts remain visible; non-sent notifications can be retried by an administrator. Message content and credentials are not written to audit logs.
- Assessment responses are evaluated without personal information or database persistence. Every result explicitly states that it is a **preliminary screening**. Real diagnosis requires data and stakeholder investigation.

## Form configuration

An editable form has a stable UUID, slug, title, introduction, success message, activation state and a controlled array of fields. Field types: `text`, `email`, `textarea`, `select`, `checkbox`. Each field stores stable key, visible label, required flag, placeholder, help text, length limit and options when relevant. Changing an active field key may require updating the V6 frontend connector during Phase 6.

Seed: `strategy-consultation` with V6 canonical keys `name`, `email`, `company`, `size`, `priority`, `message` (all required). V6's consent and honeypot fields remain separate, with consent required for acceptance. UI displays required asterisks immediately following labels.

## Email delivery

`CMS_SMTP_HOST`, `CMS_SMTP_PORT`, `CMS_SMTP_USERNAME`, `CMS_SMTP_PASSWORD` and `CMS_MAIL_FROM` are private environment settings. The from-address/domain must be verified with your email provider. The admin stores only routing preferences (`muaghauri@gmail.com` by default) and never returns SMTP credentials.

When a submission arrives, it is committed to the database **before** delivery is attempted. `smtp_sender` sends a plain-text message using SMTP STARTTLS on port 587, or SMTP over SSL on 465. A trusted `Reply-To` can point to a server-validated lead email. Optional short acknowledgment is sent best-effort only when the main notification has been accepted; delivery failures cannot be misrepresented as successful main notifications. `not_configured` means no SMTP host/from, `failed` means provider rejection/error, `sent` means SMTP send method returned successfully (not proof of final inbox placement). Configure SPF, DKIM, DMARC and actual end-to-end delivery tests at launch.

## Inquiry storage and retention

All answers, contact consent, timestamp, source page and optional UTM values are saved for authorized administrators. There is no automated lead-deletion schedule yet; implement an approved retention period in production and use the administrative delete endpoint when required. CSV exports contain personal data and are audited. No customer inquiries are seeded.

## Assessment management

The standard seeded assessment has seven V6 questions. Editors may change headings, answers and guidance associations. Results are triggered by exact `questionID.optionID` mappings, validated against the active question set. Invalid/dangling rules are rejected. API responses contain a small list of investigation areas and an explicit disclaimer; there is **no numerical score** or assertion of confirmed root cause.

## UI and permissions

The Phase 4 workspace uses Auvorent navy, ivory and emerald: a live inquiry inbox with summary metrics, a field-based form editor with ordering, a question/answer assessment editor with guidance rules, and an administrator-only email-routing view. Editors manage forms/assessments but cannot view leads or alter email routing; reviewers can view editorial records without editing; ordinary viewers retain read-only access to non-personal draft schemas.

## Deferred

Production V6 `build.py` integration, SEO-aware publishing, versioned frontend render, full browser accessibility QA, email-provider account provisioning, production WAF/CAPTCHA, data retention automation and hosting remain in Phases 5/6 or production readiness. The browser smoke run was blocked in this execution environment; screenshots from prior phases are illustrative only, not Phase 4 E2E evidence.
