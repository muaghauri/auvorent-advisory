# Phase 3 — Collections, Media & Assets

## Delivery objective

Give Auvorent editors a practical, branded administrative workspace for the content types and media required by the V6 website, with stable IDs and server-enforced rules suitable for future API-based publishing.

## Database additions

**`collection_entries`** — normalized `kind`, immutable primary key, unique slug per kind, title, summary, Markdown body, safe structured JSON, status, featured flag, sort order, hero image ID, custom icon ID, provisional SEO fields, timestamps and editor attribution.

**`collection_relationships`** — source ID, target ID, relation kind and timestamps. Links are validated against known entity types; no dangling author references or repeated identical links. Referenced content cannot be deleted while linked.

**`media_assets`** — immutable asset ID, original name, storage file name, MIME, asset kind, icon style, SHA-256, byte size, dimensions, alt text, caption, source notes, decorative flag and attribution. Replacing a file retains the asset ID used throughout the CMS.

**`media_usages`** — media ID, owner type/owner ID and slot. Collection hero/icon usage stays in sync with the corresponding collection field. Image/icon associations can also be attached to existing Page Studio sections. Assets cannot be deleted until their references are detached.

`0003_collections_media` adds these tables and brings the content revisions index into alignment with the Phase 2 ORM schema. It is safe to migrate a tracked Phase 2 database, but back up before migration as standard practice.

## CMS views

**Collections & Insights**: Six collection tabs; searchable record list; inline draft editor for name/slug/summary/Markdown, structured content JSON, status, featured flag, hero image, SVG icon and provisional SEO fields; entity relationships and delete guard. All editing endpoints are authenticated and permissioned. Changes do not publish to the public site.

**Media & Custom Icons**: Search and filter by asset kind; upload JPG/PNG/WebP/PDF and sanitizable SVG icons; thumbnail/card previews; descriptive metadata editing; asset replace action; asset usage report; existing page-section assignment; delete guard for in-use assets. Source notes explicitly support provenance/license review.

## Asset security

- Maximum upload size: 10 MiB for general assets; 200 KiB for SVG icons.
- Raster files are opened and decoded with Pillow; MIME must correspond to actual content.
- Uploaded SVG icons are parsed with `defusedxml`, restricted to a small allowlist of shape/geometry attributes and approved Auvorent colors. Scripting, event handlers, embedded/remote image loading and unknown foreign elements are not permitted.
- Authenticated file and thumbnail endpoints remain private CMS resources pending production public-media deployment.
- File replacement maintains a stable CMS ID; content usage survives. Image thumbnails are generated as WebP.
- Media metadata and collection text reject embedded HTML/executable links in the API. This is not a generic raw-HTML editor.
- Role checks and CSRF checks apply to writes. `viewer`/`reviewer` access is read-only.

## V6 seed mapping

The Phase 3 seed reads the preserved V6 editorial snapshot in `seed/v6_page_content.json`, using existing route slugs. It creates four service records, two industry records, three insight records and four existing WebP assets. Imported records have `draft` status. Source notes on imagery explicitly require commercial usage-rights verification before public launch. Author, leadership, case study and testimonial collections remain empty until factual content is approved.

## Integration contract for next phases

Phase 4 extends this platform with configurable forms, validated consent/inquiries, notification provider settings, and the Business Optimization Check. Phase 5 adds editorial workflow, full SEO panels, preview, publishing and rollback. Phase 6 maps approved CMS collection/page data and media to the current V6 frontend renderer, with stable public routes and proper cache/content invalidation.

Do not assume the current `build.py` already consumes the new collection records; it does not. Never expose draft collection/media endpoints to public visitors.
