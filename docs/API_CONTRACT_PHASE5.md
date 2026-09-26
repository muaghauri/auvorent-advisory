# Phase 5 API contract

**Base:** `/api/v1`. All routes other than health/login require an authenticated session. Every `POST`, `PUT`, `PATCH`, and `DELETE` requires the same-origin CSRF cookie/header pair. Roles inherit Phase 1–4 permissions.

| Method | Endpoint | Permission | Description |
| --- | --- | --- | --- |
| GET | `/publishing/entities` | content:read | Selectable page and collection records |
| GET | `/seo/{kind}/{id}` | content:read | Effective SEO metadata + validation |
| PUT | `/seo/{kind}/{id}` | content:edit | Replace metadata and invalidate stale approval |
| GET | `/seo-issues` | content:read | Validation summary for all entities |
| GET | `/seo/validate/{kind}/{id}` | content:read | One-entity SEO validation |
| POST | `/reviews/{kind}/{id}/submit` | content:edit | Submit exact current content for independent review |
| GET | `/reviews` | content:read | List editorial reviews; `state` filter optional |
| POST | `/reviews/{review_id}/decision` | content:approve | Approve or reject (cannot self-approve) |
| POST | `/preview/{kind}/{id}` | content:read | Generate 30-minute private snapshot URL |
| GET | `/preview/view/{token}` | content:read | View expiring private HTML snapshot |
| GET | `/preview/media/{id}` | media:read | Private image for preview |
| GET | `/publishing/versions/{kind}/{id}` | content:read | Content/section/SEO history |
| POST | `/publishing/versions/{revision_id}/restore` | content:edit | Restore older version to draft |
| GET | `/redirects` | content:read | List redirect rules |
| POST | `/redirects` | content:edit | Create internal 301/302 redirect |
| PATCH | `/redirects/{id}` | content:edit | Edit rule |
| DELETE | `/redirects/{id}` | content:edit | Delete rule |
| POST | `/publishing/build` | content:publish | Build now or schedule local staging release |
| POST | `/publishing/run-due` | content:publish | Run up to five scheduled jobs now |
| GET | `/publishing/deployments` | content:read | Recent local deployment history |
| GET | `/publishing/current` | content:read | Current local staging release |
| GET | `/publishing/site/{path}` | content:read | Authenticated preview of current static release |
| POST | `/publishing/rollback/{release_id}` | content:publish | Repoint local staging to immutable prior release |

**Kinds:** `page`, `service`, `industry`, `insight`, `author`, `case_study`, `team_member`.

**Important:** `publishing/build` targets **local staging only** even when a canonical production domain is configured. HTML has noindex and robots.txt disallows all. The final hosted V6 release pipeline is Phase 6.

### Submit request

```json
{"note":"Review consulting claims and the final SEO summary."}
```

### Decision request

```json
{"decision":"approve","note":"Verified against approved business copy."}
```

### Publish request

```json
{}
```

Or schedule a date with timezone:

```json
{"scheduled_for":"2026-10-01T10:00:00+05:00"}
```

Failed local staging jobs return `status: "failed"` with a clear reason and leave the previous release active. Scheduled jobs require explicit worker execution; no automatic hosted scheduler is included.
