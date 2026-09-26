# Phase 6 — V6 Integration, Security QA & Deployment Handover

**Implemented:** September 26, 2026. **Release type:** fully integrated local/private staging + guarded production static export. **Not live on a domain.**

## What changed

1. All 19 original V6 page templates and associated images, SVG logos and theme styles are bundled with the CMS. A staging publish now preserves the original responsive V6 HTML, CSS, navigation and footer rather than using the earlier generic preview shell.
2. Existing V6 section content is represented by stable CMS section IDs. The new visual editor exposes each text-node slot, image, inline SVG icon and internal CTA/link, so routine changes do not require manually editing HTML or losing the approved template. New sections use bounded brand styles.
3. Original V6 shared navigation, primary CTA, logo paths, copyright and tagline resolve from CMS-managed settings during staging builds.
4. Existing V6 service, industry and insight collection pages retain their original styled shells; collection updates alter the relevant copy and editorial content without downgrading to a generic page template. Images and sanitized custom SVG icons from the managed media library are copied into self-contained release assets. Section editor changes invalidate prior content approval; a separate reviewer must approve the exact new version.
5. The public V6 contact form and Business Optimization Check now use the Phase 4 public APIs. Contact field order/labels/options come from CMS form definitions. Assessment answers are evaluated on the API server; recommendations do not claim to be verified diagnoses.
6. Phase 5 versioned, atomic staging publishing and rollback remain intact. SEO metadata, sitemap and redirect data are carried into each release. Staging outputs remain `noindex,nofollow` and `Disallow: /`.
7. The static site deployment `_headers` also receives an exact-origin `connect-src` rule for the separately hosted CMS API; this is necessary for form and assessment requests on hosting platforms such as Cloudflare Pages.
8. The admin now shows the new **Visual editor** inside Page Studio plus a **production readiness** panel in SEO & publishing.
9. A manually triggered production static export is possible *only after all deployment gates pass*. No actual DNS, domain purchase, SMTP secret, or public hosting credentials are provided.

## API additions

| Method | Endpoint | Access | Purpose |
|---|---|---|---|
| GET | `/api/v1/integration/sections/{id}/fields` | Editor+ | List text, media, icon and internal-link slots. |
| PATCH | `/api/v1/integration/sections/{id}/visual` | Editor+ + CSRF | Save field-level changes as draft and invalidate prior approvals. |
| GET | `/api/v1/integration/readiness` | CMS authenticated content reader | Safe boolean deployment readiness checklist; secrets never returned. |
| POST | `/api/v1/integration/export-production` | Super Admin + CSRF | Create standalone, non-deployed static export when ALL gates pass. |

Public website calls existing Phase 4 endpoints:

- `GET /api/v1/public/forms/strategy-consultation`
- `POST /api/v1/public/forms/strategy-consultation/submit`
- `GET /api/v1/public/assessments/business-optimization-check`
- `POST /api/v1/public/assessments/business-optimization-check/evaluate`

## Setup / run locally

```bash
cd auvorent-cms-phase6
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Set CMS_SECRET_KEY to a unique 32+ character value, even on staging.
alembic upgrade head
python -m backend.app.seed_super_admin --email your-email@company.com --name 'Your Name'
python -m backend.app.seed_phase2
python -m backend.app.seed_phase3
python -m backend.app.seed_phase4
uvicorn backend.app.main:app --host 127.0.0.1 --port 8900
```

Open `http://127.0.0.1:8900`. Configure `CMS_PUBLIC_SITE_ORIGIN=http://localhost:8787` and `CMS_PUBLIC_API_BASE=http://127.0.0.1:8900` for public local preview. Browser calls will use CORS only for the single configured site origin.

## First complete staging release

1. Review the imported pages, four services, two industries, three articles and contact/assessment definitions.
2. Set the site's canonical HTTPS base in Site settings; `https://auvorent.com` is a **provisional design baseline**, not proof that you own the domain.
3. Update at least the homepage, About, Services, Contact and Assessment pages. Use **Visual editor** to change copy, images, icons and CTA destinations without altering the V6 layout.
4. Add a second user with Reviewer rights. Submit changed pages for review; the creator cannot approve their own changes.
5. In SEO & publishing, validate SEO and build a private staging release. No changes are sent to the domain automatically.
6. Click **View current staging**. Full V6 styles, original images and content from approved page snapshots render in that release. Unapproved pages retain the original V6 staging baseline and noindex status.
7. Run `python scripts/verify_release.py instance/publishing/current` if using the default local SQLite path.
8. Test the public form with the development SMTP sandbox or test provider. Check inquiry persistence and notification status in the admin; don't equate saved records with delivered messages.
9. On any incorrect publish, use the Phase 5 rollback control to restore the previous immutable release.

## Separate website preview

For an ordinary local public-site preview, serve the active release on its own port:

```bash
python3 -m http.server 8787 --bind 127.0.0.1 --directory instance/publishing/current
```

Open `http://localhost:8787`. Configure the matching CORS site origin before form tests.

## Production-readiness gate

The gated export requires **all** of the following:

- Current immutable staging release exists.
- Super Admin explicitly sets `CMS_ENABLE_PRODUCTION_EXPORT=true`.
- Legal counsel approves the **final** privacy policy and terms, and both are published without drafting placeholders. Explicitly set `CMS_LEGAL_REVIEW_CONFIRMED=true` after approval.
- Brand legal/trademark rights and intended territory are verified; only then set `CMS_BRAND_CLEARANCE_CONFIRMED=true`. Auvorent's name and logo are **not** represented as cleared by this codebase.
- SMTP host and verified sender are configured; actual delivery to `muaghauri@gmail.com` must also be smoke-tested on the hosting environment.
- The public CMS API origin is HTTPS and the exact public website origin is configured in `CMS_PUBLIC_SITE_ORIGIN`.
- Admin sessions are Secure with a strong secret; production database uses managed PostgreSQL.
- Canonical website base is HTTPS and matches your owned production domain.

The **production export** endpoint writes a static directory to the private publish root's `exports/` folder with production `robots.txt` and the intended robots settings on approved pages. It does NOT upload, change DNS, purchase a domain, or activate indexing itself.

## Hosting recommendation

- Public static pages: Cloudflare Pages (or equivalent). Deploy only the exported production site folder to the verified account. Include `_headers` and `_redirects` in the host's upload.
- CMS/API: protected, TLS-terminated container service on a separate subdomain; restrict admin to authorized people and configure CSP/CORS.
- Data: PostgreSQL 16+; persistent media and publishing volumes, with tested encrypted backups. Move media to S3/R2 and integrate external cache invalidation before running multi-node publishing.
- Mail: verified sender, real SMTP/transactional service, deliverability monitoring. The default recipient is `muaghauri@gmail.com` but editable inside the CMS.
- TLS, WAF, uptime monitoring, credential vault and DNS remain an operator responsibility; no connection is installed by this package.

### Docker staging example

`Dockerfile` and `compose.staging.yml` provide a staging-compatible CMS container and PostgreSQL. Add your own TLS proxy and secrets; run migrations once using `docker compose -f compose.staging.yml run --rm cms alembic upgrade head` before starting the API. This compose definition binds the API to loopback and does not expose an HTTPS endpoint.

## Security / limitations

- Original V6 HTML may contain inline icon SVGs; visual editor replaces chosen icons with Phase 3 sanitized managed SVG files. New/modified raw HTML is allowlist-sanitized and custom JavaScript is forbidden.
- CMS field changes invalidate approval; navigation and global settings remain admin-only and are reapplied on the next release, so review them as part of every publish checklist.
- All private preview/staging routes require CMS authentication; generated static export contains **no admin secrets**.
- The editor preserves V6's approved HTML/CSS. Rich layout creation beyond the supported section catalog requires development work.
- Domain/trademark clearance, final legal text, genuine biographies/case studies, real SMTP delivery and remote-host browser acceptance are **external dependencies**. These are not artificially marked complete.
- Phase 6 does **not** include a production SMTP credential, a paid domain purchase, a hosting account connection or a public deployment. The code is ready for these steps once credentials and approvals are supplied through the user's own infrastructure.

## Acceptance testing evidence and outstanding UI checks

- Automated tests: **71 passing** after implementing the collection-template preservation and Phase 6 field-level editor.
- Clean SQLite Alembic migration: all migrations through Phase 5; no schema change required by Phase 6; `alembic check` shows no new operations.
- Private staging render: all 19 V6 pages compile with original design assets, per-page SEO, a single HTML5 doctype and configured content-security policy.
- Public API HTTP smoke: contact and assessment endpoints respond; CORS permits only the configured site origin; authenticated deployment-readiness endpoint denies unauthorized requests.
- Automated static check: no missing referenced local images and 19 documents validated.
- **Automated Chromium visual interaction test remains pending** because the hosted execution environment returns `ERR_BLOCKED_BY_ADMINISTRATOR` even for `data:` and `file:` URLs. Do not interpret static tests as proof of browser layout or live SMTP delivery. Perform desktop/mobile and screen-reader acceptance on your own staging domain.

## Collection/content ownership

Original V6 service, industry and insight URLs have both a Page Studio record (layout/sections) and a related collection record (editorial content). If both revisions are approved in a single publish, the collection copy on that URL takes precedence, using the original V6 template. Coordinate approvals to avoid overwriting layout-related copy changes unexpectedly. New collection slugs outside the 19 original V6 routes use the basic brand-compatible template until a dedicated V6 page layout is assigned.
