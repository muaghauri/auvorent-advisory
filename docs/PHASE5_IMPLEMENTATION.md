# Phase 5 implementation — SEO, editorial review and local publishing

## Architecture

Phase 5 extends the Phase 4 FastAPI backend with `phase5.py`, `phase5_worker.py`, an Alembic migration and a fourth standalone admin JS bundle (`phase5.js`). The CMS persists five new concepts: SEO records, redirect rules, editorial reviews, private preview tokens and immutable staging deployment records.

The private admin interface now offers four tabs: SEO Studio, Editorial Approvals, Preview & Releases, and Redirects. It reuses the existing session authentication, CSRF protection, permission checks, audit logging and Auvorent design tokens.

## SEO content and preview

`cms_seo_records` stores per-entity canonical overrides, title/description, robots intent, Open Graph, optional managed OG media, structured-data type and breadcrumb title. Existing Phase 2/3 SEO columns are kept synchronized for backward compatibility. Metadata validation provides blocking errors for missing SEO title/description on indexable content, unsupported canonicals, missing sections or empty collection content; softer warnings cover unusual lengths and missing image alt text.

Private preview tokens are generated with 256+ bits of randomness and stored in the database **only as SHA-256 hashes**. Preview access requires a logged-in CMS account with content-read permission. Tokens expire after 30 minutes, are bound to an immutable snapshot and never enable a visitor to publish. The `X-Robots-Tag` and page robots metadata prevent preview indexing.

Existing source V6 HTML is rendered only when the exact source matches the approved seed. Arbitrary edited HTML does not render; newly written content receives an escaped structural preview. Browser-style rendering of every editable dynamic template is part of Phase 6.

## Editorial workflow

Supported states: `draft → in_review → approved → published` plus rejected, invalidated, unpublished and archived variations. Publication cannot be forced by changing a status field in Page Studio/Collections APIs. An independent reviewer must approve the current content fingerprint. Fingerprints include page content/section order and SEO, or collection content/media references and SEO. Changing metadata or sections invalidates active approval and returns the CMS item to draft. A review cannot be completed by the original author.

Restoring historical page, section, collection or SEO content also returns the item to draft. This does not automatically modify the already released staging site.

## Local staging generation

`compile_release()` assembles approved content into a **new immutable directory** using previously deployed staging files as the baseline. It bundles the original V6 stylesheet and assets, adds canonical/OG/JSON-LD and indexable sitemaps, writes `_redirects`, and creates an immutable release manifest. Original unchanged seed sections render with V6 markup; changed content is escaped in simpler structural sections.

The output includes `robots.txt` with `Disallow: /` and HTML `<meta name="robots" content="noindex,nofollow">` because **Phase 5 is staging only**. Each HTML page includes a `data-planned-robots` attribute showing the intended eventual indexing setting. Phase 6 must generate production-safe robots according to approved metadata.

A temporary directory is validated completely **before** `os.replace()` swaps the `current` symlink. Previous releases remain immutable. Failed builds discard incomplete output and preserve the prior current release; when database/audit failure occurs after pointer switching, the previous pointer is restored. Staging rollout is local filesystem only, not remote deployment. The `publishing/site/...` endpoint provides authenticated local browse access to the active release; responses are private and carry `X-Robots-Tag: noindex, nofollow`.

At Phase 5, the local pointer uses an in-process lock. **Multi-instance distributed locking and remote release orchestration are intentionally Phase 6**. Do not run multiple publishing workers concurrently against the same local staging root.

## Scheduled publishing

Scheduling creates an explicit database job. Execution requires either the authenticated Run Due control or the CLI `python -m backend.app.phase5_worker --once`, invoked periodically by your OS scheduler. At run time, approval fingerprints and SEO requirements are revalidated; content changed after approval cannot publish.

## Redirect rules

Internal URLs only; 301/302 supported. Cyclic redirects, external destinations, route traversal and duplicate source paths are rejected. Redirects are emitted into a staging `_redirects` file. The production platform's redirect deployment is a Phase 6 integration task.

## Production limitations and release prerequisites

- Full V6 editable layout parity: Phase 6.
- Public website integration (all pages, forms, assessment, navigation and live media URLs): Phase 6.
- Production hosting, TLS, PostgreSQL, persistent S3/R2 media, CI/CD, snapshots and distributed job locking: Phase 6.
- Real SMTP recipient delivery to `muaghauri@gmail.com`: must be configured and tested using a verified sender; not implied by the local CMS tests.
- Final business/legal disclosures, privacy terms, consultant credentials, claim substantiation, brand ownership and domain registration must be independently confirmed.
