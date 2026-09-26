# Phase 1 API contract

Base: `/api/v1`. Interactive OpenAPI (development): `/api/docs`.

| Method | Endpoint | Access | Purpose |
|---|---|---|---|
| GET | `/health` | Public | Basic service and database readiness |
| GET | `/auth/csrf` | Public | Create/get same-origin CSRF token |
| POST | `/auth/login` | CSRF | Password login; sets HTTP-only session cookie |
| GET | `/auth/me` | Signed in | Current user/role |
| POST | `/auth/logout` | Signed in + CSRF | Revoke current session |
| POST | `/auth/change-password` | Signed in + CSRF | Verify existing password, update and revoke other sessions |
| GET | `/dashboard` | `dashboard:read` | Actual database counts and module status |
| GET | `/users` | `users:manage` | Super Admin account list with search and pagination |
| POST | `/users` | `users:manage` + CSRF | Create user with temporary password; force change |
| PATCH | `/users/{id}` | `users:manage` + CSRF | Update name, role, active state |
| POST | `/users/{id}/reset-password` | `users:manage` + CSRF | Replace another user's password, revoke sessions |
| GET | `/audit` | `audit:read` | Paginated security audit log |

### Session rules

- CSRF: `GET /auth/csrf` then `X-CSRF-Token` on every POST/PATCH/DELETE.
- Authentication: `auv_admin_session` cookie; HTTP-only, SameSite=Strict and secure when configured.
- Cookies and API requests must be same-origin (or use an explicitly configured origin with CSRF origin verification).
- Users are never authorized based on a browser-provided role; every permission check reads the authenticated account from the database.

### Status codes

- `401`: authentication missing/expired or failed login.
- `403`: missing CSRF, wrong Origin, insufficient role or initial password-change requirement.
- `409`: duplicate email.
- `422`: field validation.
- `429`: IP login threshold reached.

### Planned API namespaces, not yet implemented

`/pages`, `/pages/{id}/sections`, `/services`, `/industries`, `/insights`, `/media`, `/navigation`, `/settings`, `/forms`, `/inquiries`, `/assessments`, `/seo`, `/preview`, `/publish` and `/redirects` will be introduced in their respective phases. No fake placeholder JSON endpoints are exposed.
