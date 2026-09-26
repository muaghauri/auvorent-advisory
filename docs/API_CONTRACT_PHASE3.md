# Phase 3 — Collections & Media API Contract

**Base URL:** `/api/v1`  
**Data:** JSON except multipart asset uploads and authenticated media binary responses.  
**Authentication:** server-side CMS session cookie.  
**Writes:** `X-CSRF-Token` required.  
**Roles:** authenticated readers can list/get; Editor/Admin/Super Admin can edit where granted by the server permission matrix.

## Collections

Use `{kind}` = `service`, `industry`, `insight`, `author`, `case_study`, or `team_member`.

| Method | Endpoint | Description |
|---|---|---|
| GET | `/collections/{kind}` | Search, paginate and optionally filter status. |
| POST | `/collections/{kind}` | Create a non-public CMS draft. |
| GET | `/collections/{kind}/{id}` | Retrieve record, connected relationships and image/icon refs. |
| PATCH | `/collections/{kind}/{id}` | Update approved fields; immutable record ID. |
| DELETE | `/collections/{kind}/{id}` | Delete only if not referenced by other collection links. |
| POST | `/collections/{kind}/{id}/relationships` | Add typed relationship to another stable collection ID. |
| DELETE | `/collections/{kind}/{id}/relationships/{relationshipId}` | Remove a relationship. |

Convenience aliases are also provided at `/services`, `/industries`, `/insights`, `/authors`, `/case-studies` and `/team-members`, with corresponding `/{id}` detail/update/delete endpoints.

Basic collection request (all content currently unpublished):

```json
{
  "title": "Business Diagnostics",
  "slug": "business-diagnostics",
  "summary": "Investigate operational bottlenecks and develop a clear improvement roadmap.",
  "body_markdown": "## How we help\nMap the current process and review business evidence.",
  "content": {"deliverables": ["Diagnostic report", "Prioritized improvement plan"]},
  "status": "draft",
  "sort_order": 0,
  "is_featured": true,
  "hero_media_id": null,
  "icon_media_id": null,
  "seo_title": "Business Diagnostics | Auvorent Advisory",
  "meta_description": "Operational assessment and root-cause business advisory."
}
```

Slug uniqueness is enforced **within** a collection kind. Repeated relationships return a conflict. An insight's `author` relationship must point to an `author` entity. Public `published` status is intentionally unavailable until the publishing phase.

## Media

| Method | Endpoint | Description |
|---|---|---|
| GET | `/media` | Search/filter list (`kind`, `search`, `limit`, `offset`). |
| POST | `/media` | Multipart upload of `file`, `kind`, `alt_text`, `caption`, `source_notes`, `decorative`, and `icon_style` as relevant. |
| GET | `/media/{id}` | Metadata, usage count and protected media URLs. |
| GET | `/media/{id}/file` | Authenticated asset bytes. |
| GET | `/media/{id}/thumbnail` | Authenticated WebP thumbnail for raster images. |
| PATCH | `/media/{id}` | Edit alt text, caption, provenance/rights notes, decorative flag. |
| POST | `/media/{id}/replace` | Multipart file replacement preserving ID and linked usages. |
| DELETE | `/media/{id}` | Rejects removal while referenced. |
| GET | `/media/{id}/usages` | All known collection/page-section references. |
| POST | `/media/{id}/usages` | Attach asset to compatible existing page section. |
| DELETE | `/media/{id}/usages/{usageId}` | Unlink manually associated page-section media. |

Accepted upload categories are raster `image`, SVG `icon`, document `document` and other allowed asset kinds as validated by the API. SVG icon design style is `line` or `filled`; external references, scripts and colors outside the Auvorent palette are rejected. A nondécorative image requires meaningful alt text.

## Common API behavior

- Record ID is a UUID independent of the public slug; slugs can change without breaking CMS references.
- 401 = missing/invalid authentication, 403 = insufficient permission, 409 = duplicate slug/reference or in-use asset, 422 = malformed input, 413 = asset too large.
- Lists are paginated and text-searchable. Server-side ORM queries are parameterized.
- Changes create audit records; collection writes also save content revision snapshots.
- Production public asset URLs and a transactional content publishing endpoint are intentionally **not implemented** in Phase 3.

For complete field schemas, use the generated `OPENAPI_PHASE3.json` or launch the local API reference at `/api/docs`.
