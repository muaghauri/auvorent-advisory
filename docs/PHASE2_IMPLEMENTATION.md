# Auvorent CMS — Phase 2 Implementation

## Module
Page Studio & Global Structure

## Implemented

- V6 rendered-content snapshot imported into a versioned seed file.
- 19 CMS page records: 17 public-content routes plus Privacy and Terms staging routes.
- 59 imported V6 top-level content blocks preserved as managed section records.
- Page CRUD with title, route, slug, template, status, navigation visibility, indexability, SEO title and meta description.
- Section CRUD with stable IDs, section keys/types, enable/disable, position and structured JSON content.
- Section reorder API.
- Header/footer/utility navigation source.
- Global brand, CTA, SEO and footer settings.
- Content revision snapshots on page/section/settings/navigation changes.
- Page Studio, Navigation and Settings admin screens.
- Phase 2 Alembic migration and V6 seed command.
- Existing Phase 1 authentication, RBAC, CSRF and audit controls retained.

## Boundary

The CMS data model is now ready, but the live/static V6 renderer is not yet consuming CMS data. Publishing, preview URLs, approvals, deployment jobs and rollback belong to Phases 5–6. The imported HTML snapshot exists to preserve current V6 content during migration; subsequent collection/media modules will progressively replace legacy HTML fields with controlled structured components.

## Seed commands

```bash
alembic upgrade head
python -m backend.app.seed_super_admin --email you@example.com --name "Your Name"
python -m backend.app.seed_phase2
uvicorn backend.app.main:app --reload --port 8000
```

## Phase 2 endpoints

- `GET/POST /api/v1/pages`
- `GET/PATCH/DELETE /api/v1/pages/{id}`
- `GET/POST /api/v1/pages/{id}/sections`
- `PATCH/DELETE /api/v1/pages/{id}/sections/{sectionId}`
- `POST /api/v1/pages/{id}/sections/reorder`
- `GET/PATCH /api/v1/navigation`
- `GET/PATCH /api/v1/settings`
- `GET /api/v1/content/revisions`
