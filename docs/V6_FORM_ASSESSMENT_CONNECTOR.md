# Planned V6 → CMS Phase 6 Connector Contract

**This file is a handover contract. The public V6 website is not yet patched or connected.**

## Contact form

Current V6 JavaScript posts its native form fields to the V6 website's `/api/contact`. Map that handler to the Phase 4 CMS API during Phase 6. Prefer a **same-origin reverse proxy/serverless adapter** so the static website does not need broad cross-origin permissions. The alternative is direct cross-origin fetch to a hardened public CMS origin using `CMS_PUBLIC_SITE_ORIGIN`.

| V6 form name | CMS form `data` key | Requirement |
| --- | --- | --- |
| `name` | `name` | Required |
| `email` | `email` | Required, validated |
| `company` | `company` | Required |
| `size` | `size` | Required choice |
| `priority` | `priority` | Required choice |
| `message` | `message` | Required, max 3000 |
| `consent` | root `consent` | Required true |
| `website` | root `website` | Honeypot, must be empty |

Adapter request: `POST /api/v1/public/forms/strategy-consultation/submit`. Include the actual source page and permitted UTM parameters. The response is an **accepted inquiry reference**, not proof of email delivery. Admin sees and retries failed email notifications. Update form HTML in V6 from the public form definition if field labels/options are changed in CMS, otherwise keep fixed canonical keys and manage labels/options via build-time dynamic rendering in Phase 6.

## Business Optimization Check

V6 currently contains seven hardcoded questions (`q1`...`q7`) in its `assets/app.js`. During Phase 6, load CMS `GET /api/v1/public/assessments/business-optimization-check`, render the approved field/choice labels, POST selections to `/evaluate`, display the preliminary screening response and offer the linked `/contact/?from=assessment` CTA.

Assessment responses must remain browser-side until a user chooses to attach them to a contact inquiry. Never silently save assessment choices as identifiable leads or convert them to fabricated numerical readiness scores.

## Readiness checks for Phase 6

- Confirm public domain, DNS, TLS and content hosting.
- Configure CMS public origin or same-origin proxy, load-balanced production API and approved rate limiting.
- Confirm SMTP sender validation, SPF/DKIM/DMARC and successful actual delivery to `muaghauri@gmail.com` (or its updated admin setting).
- Render CMS-driven labels and answer options with required markers immediately after field labels.
- Confirm assessments and inquiry conversion work on desktop and mobile, with CSRF/session isolation for private admin routes.
- Preserve V6 SEO performance and static/server-rendered editorial content; primary page content must not depend on client-side API fetches.
