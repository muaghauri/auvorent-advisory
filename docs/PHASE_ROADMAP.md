# Auvorent Advisory — CMS development roadmap

**Basis:** `AUVORENT_CMS_ADMIN_PANEL_COMPLETE_REQUIREMENTS.md` and the V6 website master document.  
**Delivery model:** Six individually testable modules. Each phase produces an updated CMS package and passes a defined acceptance gate.  
**Non-negotiable:** Preserve the V6 public website's design, fast pre-rendered content, SEO metadata, and responsive behavior. The admin panel is a separate authenticated application.

| Phase | Module | Included functionality | Completion gate |
|---|---|---|---|
| **1** | **Foundation, Security & Dashboard** | FastAPI project, local/production DB configuration, Alembic initial migration, Argon2id password hashing, secure sessions, CSRF protection, login/logout/reset-own-password, role-based access, user administration, audit trail, admin design shell, health and dashboard APIs | Protected admin panel runs locally; roles enforced; security/API tests pass. No demo credentials or fabricated dashboard data. |
| **2** | **Page Studio & Global Structure** | V6 content extraction/migration, all page records (including legal), modular page/section editing, field controls, drag/reorder, navigation/footer, global branding/settings, content validation, staging drafts | All existing V6 pages can be edited through the CMS and previewed without manually editing `build.py`; current routes preserved. |
| **3** | **Collections, Media & Assets** | CRUD for services, industries, insights/articles, author profiles, relevant case-study/team content, searchable media library, sanitized custom SVG icons, image metadata/alt text, asset usage/replacement, content relationships | Each collection and managed asset changes in the admin and resolves through stable CMS IDs; V6 design tokens enforced. |
| **4** | **Lead Generation & Assessments** | Editable form schemas, validation/consent, contact routing settings, production-capable email integration, inquiry storage/assignment/export, configurable Business Optimization Check and result rules, anti-spam | End-to-end contact form creates an inquiry and delivers a verified notification to the configured recipient; assessment outputs remain preliminary. |
| **5** | **SEO, Approval & Publishing Studio** | Per-entity SEO and Open Graph, canonical/index controls, XML sitemap, redirects, SEO validation, workflow draft→review→approved→publish, previews, scheduled posts, content versions, atomic deployment and rollback | Approved changes publish to a staging V6 render with correct SEO; failed builds do not alter production; rollback is demonstrated. |
| **6** | **V6 Integration, Security QA & Deployment** | Connect complete V6 renderer to published CMS data, media hosting, static rebuild hooks, production DB/storage, observability, backup/restore, access reviews, responsive/accessibility/SEO tests, email deliverability, CI/CD, operational handover | Editors can manage every V6 section/asset/SEO field, publish and roll back safely, inquiries deliver correctly, and the site passes deployment/quality gates. |

## Cross-phase operating rules

- Ship an **individually runnable ZIP** at each phase. Keep the frontend, backend, migrations, tests, and `.env.example` together.
- Never invent testimonials, client logos, team credentials, pricing commitments, or performance statistics.
- Keep credentials outside Git or downloadable source. Set the eventual contact-recipient default to `muaghauri@gmail.com` only after the form/email module is built.
- Changes stay **unpublished until an authorized editor/approver publishes**. A failed publish must be atomic and reversible.
- Use **stable IDs and API versioning** now so later modules do not require frontend rewrites.
- Production database: PostgreSQL; SQLite is only for development/testing.
- Do not claim CMS-driven page content is already connected while Phase 1 is underway.

## Current execution

**Phases 1–5 are developed and included in this package.** Phase 5 provides SEO/review controls and an authenticated **local staging publisher only**. Phase 6 is required for complete CMS-driven public V6 templates, production hosting, email-delivery verification and final quality sign-off.
