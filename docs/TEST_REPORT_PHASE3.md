# Phase 3 — Automated Verification and Known Limitations

**Date:** 26 September 2026  
**Test environment:** Local development, disposable SQLite database and isolated media directory; Python FastAPI TestClient.

## Automated tests

**32 tests passed.** Coverage includes inherited Phase 1 and Phase 2 tests plus Phase 3 tests for:

- Login/authentication boundary and read-only vs editing permissions for new endpoints.
- Collection creation, update, deletion, paginated listing, alias routes, stable IDs, duplicate-slug rejection and revision snapshots.
- HTML/executable-URL rejection and draft-only status enforcement.
- Type-checked author/other content relationships, duplicate-link prevention and in-use delete guards.
- Raster upload MIME/content verification, dimensions, generated WebP thumbnails, file replacement with stable IDs, metadata validation and oversize rejection.
- Sanitized brand-palette SVG icon acceptance; unsafe scripts, foreign-image/external URL references and non-theme colors rejected.
- Collection hero image usage syncing, image deletion protection, page-section usage linking, slot compatibility, removal and cleanup on section deletion.
- Idempotent V6 content/media import and draft defaults.

## Additional validation

- Alembic migration tested from empty database through `0001_foundation`, `0002_page_studio` and `0003_collections_media`.
- `alembic check` reported no unapplied ORM schema operations after migration.
- Phase 2 + 3 seeds created 19 pages, 59 sections, 4 services, 2 industries, 3 insight drafts and 4 seeded V6 image records; rerunning Phase 3 created zero duplicates.
- `node --check` passed for the existing admin and new Phase 3 frontend scripts.
- Static offline UI captures in `previews/` inspected for responsive visual layout at desktop 1440px and mobile 390px, without horizontal overflow.
- Generated OpenAPI endpoint schema stored in `OPENAPI_PHASE3.json`.

## Not validated or not in this phase

- No full production-hosted browser E2E run was performed. Local Chromium navigation in this execution environment was restricted; static previews and API tests are not substitutes for a live interactive walkthrough.
- No authenticated real SMTP/Resend email deliveries; forms and recipient configuration are Phase 4.
- No publication, indexable production website render, SEO deployment, approval/rollback or public CDN; these are Phases 5–6.
- No real consultant identities, client logos, testimonials or measured outcome claims seeded. Verify usage rights for the imported V6 illustration/photography assets before launch.
- PostgreSQL production deployment, multiuser load tests, WAF/TLS, backups and media object storage require a real staging/production environment in Phase 6.
