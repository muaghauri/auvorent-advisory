# V6 website integration notes for Phase 2

This Phase 1 package is **separate from the V6 public site**; its Phase 1 APIs do not edit public-site content yet.

## Verified V6 baseline

- Source: `auvorent-advisory-website-v6.zip` / `AUVORENT_V6_WEBSITE_MASTER.md`.
- Public source renderer: `build.py` (pre-rendered HTML).
- Frontend assets: `assets/style.css`, `assets/app.js`, `assets/images`, approved `assets/logo*.svg`.
- Initial config: `content/site-config.json`. It is only partly wired into the existing renderer.
- Public routes: 17 content routes; plus staging legal pages and 404.
- Existing contact endpoint: `POST /api/contact` via optional Cloudflare Pages Function.
- The public site has no admin API/database currently.

## Phase 2 implementation contract

1. Extract content from `build.py` to typed page, section, navigation and global-setting entities. Use immutable stable UUIDs for content IDs and slugs for route locations.
2. Migrate **every** visible field on each V6 page, including headings, accent spans, card descriptions, CTA destinations, icon IDs, image IDs, page SEO, alt text, and nav/footer labels. Keep `build.py` as an adapter/renderer, not a source of truth.
3. Maintain existing HTML semantics and responsive CSS; generate the public content as static HTML. Do not shift indexable content into runtime client-side API calls.
4. Do not publish content directly from draft API writes. Preview and publish queues are introduced in Phase 5.
5. Handle missing/unconfirmed leadership or client evidence with unpublished blocks, never fabricated placeholders in production.
6. Preserve staged legal pages as noindex until reviewed. Maintain the current proposed canonical domain as non-final until registration and brand clearance.
7. Retain existing form endpoint until the dedicated Phase 4 API and verified email delivery are deployed. Never claim form submissions reach Gmail based solely on the admin recipient field.
8. Leave current production website files untouched until Phase 6 integration testing proves route and content parity.

## Planned Phase 2 API endpoints

- `GET/POST /api/v1/pages`
- `GET/PATCH/DELETE /api/v1/pages/{id}`
- `GET/POST /api/v1/pages/{id}/sections`
- `PATCH/DELETE /api/v1/pages/{id}/sections/{sectionId}`
- `POST /api/v1/pages/{id}/sections/reorder`
- `GET/PATCH /api/v1/navigation`
- `GET/PATCH /api/v1/settings` (non-secret site settings)

The API paths above are **not implemented** in this Phase 1 ZIP.


## Phase 3 integration addendum

The Phase 3 admin stores services, industries, insights, related editorial profiles and managed media with permanent CMS UUIDs. Hero images and custom SVG icons are stored through media IDs; the CMS tracks asset usages. The idempotent importer seeds 4 services, 2 industries, 3 insights and 4 source V6 images as drafts. The existing website renderer has **not** yet been refactored to read the new database and may still contain legacy HTML snapshots; Phase 6 must define the mapping, public media URLs, cache behavior and migration/validation checks. Draft records and authenticated media URLs must never be linked into the live public site.
