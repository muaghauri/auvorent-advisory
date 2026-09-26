# Auvorent Advisory CMS — Phase 6 / Complete integrated package

**Status:** V6-responsive CMS integration, guarded production-export workflow and public contact/assessment API bridge implemented. **Not published to a public domain**; brand, legal, verified sender, production hosting and email deliverability require external approval.

This is a cumulative source package containing development Phases 1–6: secure admin, Page Studio, collections/media/icons, forms/inquiries/assessments, SEO/editorial staging/rollback, and full V6-preserving renderer integration.

See [Phase 6 full implementation and deployment handover](docs/PHASE6_IMPLEMENTATION.md) for local setup, approvals, first staging build, production-readiness gates, Docker staging, testing and release export instructions.

Quick QA:

```bash
python -m pytest -q
alembic upgrade head
alembic check
node --check frontend/assets/admin.js
node --check frontend/assets/phase3.js
node --check frontend/assets/phase4.js
node --check frontend/assets/phase5.js
node --check frontend/assets/phase6.js
node --check seed/cms-public.js
```

The starting content follows the V6 website; it is **not** a representation of verified consulting outcomes, customers, completed projects, finalized privacy policy, purchased domain or a production company registration.
