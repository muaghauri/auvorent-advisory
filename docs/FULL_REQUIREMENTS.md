# Auvorent Advisory — CMS / Admin Panel Complete Requirements

**Document type:** Product Requirements + Functional Specification + Technical Handover  
**Website baseline:** Auvorent Advisory V6  
**CMS version target:** V1  
**Document date:** 25 September 2026  
**Status:** Ready for backend/API and admin-panel implementation planning

> **Purpose:** Define the complete requirements for a separate CMS/Admin Panel that can fully manage the Auvorent Advisory V6 website while preserving the approved public-site design, SEO architecture, responsive behavior, publishing controls, and future scalability.

---

# 1. Product objective

The CMS/Admin Panel must allow authorized users to manage the complete public website without editing code.

The system must support:

- Full page and section editing.
- Images, icons, logos, and downloadable assets.
- Navigation and footer control.
- Services, industries, insights, assessment content, and forms.
- SEO metadata on every page.
- Contact-email routing.
- Draft, preview, publish, rollback, and version history.
- Media library management.
- Inquiry management.
- User roles and audit logging.
- API connectivity between CMS and website.
- Future extensibility without breaking the current V6 frontend.

The public website should remain **fast, SEO-friendly, responsive, and production-grade**. The CMS should manage content, while the public website should continue to render server-side/static HTML for indexable content.

---

# 2. Core architecture

## 2.1 Recommended architecture

Use a **separate authenticated CMS application** connected to a backend API and database.

Recommended model:

```text
Admin Panel
    ↓
CMS API
    ↓
Database / Media Storage
    ↓
Publish Service
    ↓
V6 Website Renderer
    ↓
Static Production Website
```

The public website must not depend on client-side CMS calls for primary SEO content.

## 2.2 Core components

1. **Admin Frontend**
   - Responsive web application.
   - Desktop-first, usable on tablet.
   - Premium Auvorent visual language.

2. **CMS Backend**
   - Authentication.
   - Authorization.
   - Content CRUD.
   - Media management.
   - SEO management.
   - Inquiry management.
   - Publishing jobs.
   - Audit logs.
   - API access.

3. **Database**
   - Structured relational content model.
   - Recommended: PostgreSQL for production.
   - SQLite acceptable only for local development/prototype.

4. **Media Storage**
   - Cloud object storage recommended.
   - Cloudflare R2, S3, or equivalent.
   - Image optimization pipeline.

5. **Publishing Engine**
   - Converts approved CMS content into the V6 website structure.
   - Rebuilds only affected pages where possible.
   - Supports staging preview and production publishing.

6. **Public Website**
   - Continues to use current V6 branding and responsive frontend.
   - Reads published content from generated/static output.
   - Uses CMS APIs only where justified.

---

# 3. User roles and permissions

The CMS must implement role-based access control.

## 3.1 Super Admin

Full platform access.

Permissions:

- Manage all website content.
- Manage users.
- Manage roles.
- Manage email routing.
- Manage website settings.
- Manage SEO.
- Manage media.
- Publish to production.
- Roll back published versions.
- View audit logs.
- Manage API configuration.
- Manage integrations.
- Manage legal and compliance content.

## 3.2 Admin / Website Manager

Permissions:

- Manage all page content.
- Manage services.
- Manage industries.
- Manage insights.
- Manage media.
- Manage forms.
- Manage navigation.
- Preview changes.
- Publish content.
- View inquiries.
- Edit SEO.

Cannot:

- Modify Super Admin users.
- View provider secret keys.
- Change infrastructure settings.

## 3.3 Editor

Permissions:

- Create and edit content.
- Upload media.
- Create insights.
- Edit page sections.
- Save drafts.
- Preview drafts.

Cannot:

- Publish directly.
- Delete core site configuration.
- Change email provider or secret settings.
- Manage admin users.

## 3.4 Reviewer / Approver

Permissions:

- View pending drafts.
- Add review notes.
- Approve content for publishing.
- Reject content back to editor.

## 3.5 Read-only User

Permissions:

- View content.
- View publishing history.
- View inquiries if explicitly granted.

No editing rights.

---

# 4. Admin dashboard

The CMS homepage should provide an executive overview.

## 4.1 Dashboard widgets

- Total pages.
- Draft pages.
- Published pages.
- Pending approvals.
- Recently updated pages.
- Latest inquiries.
- New unread inquiries.
- Recent media uploads.
- Latest publish status.
- SEO issues summary.
- Broken-link summary.
- Site health.
- Last successful production deployment.
- Upcoming scheduled publications.

## 4.2 Quick actions

- Create page.
- Create insight.
- Upload media.
- Edit homepage.
- View contact inquiries.
- Run preview.
- Publish changes.
- Edit global settings.

---

# 5. Website page management

## 5.1 Page list

Display:

- Page title.
- URL slug.
- Page type.
- Status.
- SEO status.
- Last updated.
- Last published.
- Updated by.
- Publish state.

Available actions:

- Edit.
- Preview.
- Duplicate.
- Unpublish.
- Archive.
- Delete where permitted.
- View history.

## 5.2 Page statuses

Required:

- Draft.
- In Review.
- Approved.
- Scheduled.
- Published.
- Unpublished.
- Archived.

## 5.3 Page properties

Every page must support:

- Internal page name.
- Public title.
- Slug.
- URL path.
- Parent page.
- Page template.
- Status.
- Indexability.
- Navigation visibility.
- Header style.
- Footer visibility.
- Page sections.
- SEO data.
- Social sharing data.
- Structured data.
- Redirect rules.
- Publish schedule.

---

# 6. Section-based page builder

The CMS should manage pages through controlled section modules rather than unrestricted raw HTML.

## 6.1 Section controls

Every section must support:

- Section ID.
- Section type.
- Enable / disable.
- Reorder via drag and drop.
- Duplicate.
- Delete.
- Background style.
- Width option.
- Padding preset.
- Content alignment.
- CTA visibility.
- Media assignment.
- Icon assignment.
- Anchor ID.

## 6.2 Supported section types

At minimum:

- Hero.
- Intro text.
- Split image/text.
- Services grid.
- Challenges grid.
- Statistics.
- Process / methodology.
- Timeline.
- Capability cards.
- Industry cards.
- CTA banner.
- Assessment CTA.
- Case study.
- Testimonial.
- Team / leadership.
- Logo strip.
- Insights grid.
- FAQ.
- Rich text.
- Contact form.
- Embedded media.
- Download block.
- Custom informational cards.
- Trust / compliance block.

The frontend design must remain within approved Auvorent design-system constraints.

---

# 7. Homepage management

The homepage must be fully editable.

Editable areas:

- Hero eyebrow.
- Hero headline.
- Highlighted/emphasized words.
- Hero description.
- Primary CTA.
- Secondary CTA.
- Hero image.
- Hero image alt text.
- Hero visual overlays.
- Business challenge cards.
- Service cards.
- Process section.
- Business intelligence showcase.
- Industry section.
- Assessment CTA.
- Featured insights.
- Final CTA.
- Footer-specific CTA if applicable.

---

# 8. Services management

## 8.1 Service entity fields

- Service ID.
- Name.
- Slug.
- Short description.
- Full description.
- Hero title.
- Hero copy.
- Icon.
- Hero image.
- Challenges solved.
- Deliverables.
- Process.
- Outcomes.
- CTA.
- Related industries.
- Related insights.
- Sort order.
- Featured toggle.
- SEO fields.
- Status.

Initial services:

- Business Diagnostics.
- AI Strategy & Implementation.
- Predictive Intelligence.
- Continuous Optimization.

---

# 9. Industries management

Fields:

- Industry name.
- Slug.
- Short intro.
- Full description.
- Hero image.
- Industry challenges.
- Operational pain points.
- Relevant services.
- Example opportunities.
- CTA.
- Related insights.
- SEO.
- Publish status.

Initial industries:

- Business & Professional Services.
- Staffing & Recruitment.

The structure must allow additional industries later.

---

# 10. Insights / Blog CMS

## 10.1 Article fields

- Title.
- Slug.
- Excerpt.
- Author.
- Author verification status.
- Hero image.
- Category.
- Tags.
- Publication date.
- Last updated date.
- Read time.
- Rich-text body.
- Inline images.
- Pull quotes.
- CTA.
- Related services.
- Related industries.
- Related articles.
- SEO metadata.
- Social image.
- Structured data.
- Draft / review / publish status.

## 10.2 Editor requirements

Support:

- H2 / H3 / H4.
- Paragraphs.
- Bullets.
- Numbered lists.
- Links.
- Tables.
- Quotes.
- Images.
- Captions.
- Inline CTA.
- Callout cards.
- Code or preformatted text if needed.

No arbitrary script injection.

---

# 11. Media library

The media library must manage all public assets.

## 11.1 Supported files

- JPG.
- PNG.
- WebP.
- SVG.
- PDF.
- DOCX if downloadable resources are added later.

## 11.2 Media fields

- File name.
- File type.
- Dimensions.
- File size.
- Alt text.
- Caption.
- Copyright/source notes.
- Upload date.
- Uploaded by.
- Usage locations.
- Replacement history.

## 11.3 Media features

- Upload.
- Replace without breaking references.
- Delete if unused.
- Crop.
- Resize.
- Generate WebP.
- Thumbnail generation.
- Search.
- Filter.
- Folder/tag grouping.
- Asset preview.
- Usage warning before deletion.

## 11.4 Image rules

The CMS should encourage:

- Professional executive/business imagery.
- Auvorent brand colors.
- Custom imagery where possible.
- No generic AI robot visuals.
- No unverified client or partner imagery.
- Required alt text for publishable images.

---

# 12. Icon management

All website icons should follow the Auvorent visual system.

The CMS must support:

- Custom SVG icon library.
- Line-art icons.
- Filled-art icons where approved.
- Theme-color restrictions.
- Icon preview.
- Icon assignment to sections/cards.
- New SVG uploads subject to validation.

SVG uploads must be sanitized.

The admin should not allow arbitrary external icon URLs by default.

---

# 13. Navigation management

## Header navigation

Editable:

- Label.
- URL.
- Internal/external.
- Order.
- Visibility.
- Dropdown grouping.
- Mobile visibility.
- New-tab behavior.

## Primary CTA

Editable:

- Label.
- Target URL.
- Visibility.

## Footer navigation

Manage:

- Services.
- Company links.
- Insights.
- Legal links.
- Social links.
- Contact information.

---

# 14. Global site settings

Editable settings:

## Brand

- Company display name.
- Legal entity name.
- Tagline.
- Primary logo.
- Dark logo.
- Light logo.
- Favicon.
- OG image.

## Contact

- Primary contact email.
- Contact form recipient.
- CC recipients.
- BCC recipients.
- Reply-to logic.
- Business phone.
- Business address.
- Calendly or booking URL.

Default form recipient for current V6 requirement:

`muaghauri@gmail.com`

The admin may change this later.

## Social

- LinkedIn.
- X/Twitter.
- Facebook.
- Instagram.
- YouTube.
- Other approved channels.

## General

- Default CTA.
- Footer copyright.
- Announcement bar.
- Maintenance mode.
- Global noindex toggle.
- Analytics IDs.
- Search Console verification.
- Cookie/consent settings.

---

# 15. Form management

The CMS must support the website contact form and future forms.

## 15.1 Contact form fields

Current V6:

- Full Name.
- Work Email.
- Company.
- Team Size.
- Main Priority.
- Business Challenge.
- Consent checkbox.
- Honeypot.

Admin can manage:

- Field label.
- Placeholder.
- Help text.
- Required/not required.
- Field order.
- Field visibility.
- Dropdown options.
- Success message.
- Failure message.
- Recipient routing.
- Consent text.

Required-field asterisks must render inline at the end of the field label.

## 15.2 Form routing

Allow:

- Primary recipient.
- Optional CC.
- Optional BCC.
- Conditional routing by selected priority.
- Optional autoresponder.

Provider secrets must not be shown in normal settings.

---

# 16. Inquiry management

The CMS should store submitted inquiries in addition to sending email.

Fields:

- Inquiry ID.
- Date/time.
- Name.
- Email.
- Company.
- Team size.
- Main priority.
- Business challenge.
- Assessment source.
- Consent.
- IP metadata if legally approved.
- Source page.
- UTM values.
- Status.
- Assigned owner.
- Notes.

Statuses:

- New.
- Reviewed.
- Qualified.
- Follow-up.
- Converted.
- Closed.
- Spam.

Features:

- Search.
- Filter.
- Export CSV.
- Internal notes.
- Assignment.
- Mark unread/read.
- Delete according to retention policy.

---

# 17. Business Optimization Check management

The assessment must be fully manageable.

## Editable fields

- Assessment name.
- Intro.
- Disclaimer.
- Question text.
- Question order.
- Answer options.
- Required question toggle.
- Conditional logic.
- Recommendation mappings.
- Result headings.
- Result text.
- CTA.
- Related service.
- Image.
- Image alt text.

The CMS must prevent unsupported medical, financial, legal, or diagnostic claims.

Results must remain positioned as **preliminary areas to investigate**, not verified root-cause diagnoses.

---

# 18. SEO management

Every page, service, industry, and article must have a dedicated SEO panel.

## Editable SEO fields

- SEO title.
- Meta description.
- Slug.
- Canonical URL.
- Index / noindex.
- Follow / nofollow.
- OG title.
- OG description.
- OG image.
- Twitter title.
- Twitter description.
- Twitter image.
- Structured-data type.
- Structured-data optional overrides.
- Breadcrumb title.

## SEO validations

Warn when:

- SEO title is too long.
- SEO title is too short.
- Meta description is missing.
- Meta description is too long.
- Duplicate slug exists.
- Duplicate SEO title exists.
- H1 is missing.
- Multiple H1s appear.
- Image alt text is missing.
- Canonical conflicts exist.
- Internal link is broken.
- Page is indexable but unpublished.

## Publish-time outputs

CMS publication must update:

- XML sitemap.
- Robots rules.
- Canonical tags.
- Structured data.
- Open Graph.
- Internal links.
- Page metadata.

---

# 19. Redirect manager

Admin must be able to create redirects.

Fields:

- Old path.
- New path.
- Redirect type.
- Active toggle.
- Notes.

Supported:

- 301.
- 302.

The CMS should automatically suggest a redirect when a published slug changes.

---

# 20. Legal-content management

Manage:

- Privacy Policy.
- Terms of Use.
- Cookie Policy.
- Disclaimer.

Features:

- Draft status.
- Approval status.
- Effective date.
- Version history.
- Legal-review confirmation.

Production publication of legal pages should be restricted to authorized roles.

---

# 21. Preview system

The CMS must support visual preview before publication.

Required:

- Preview current draft.
- Desktop preview.
- Tablet preview.
- Mobile preview.
- Private preview URL.
- Preview expiration.
- Preview unpublished pages.
- Preview scheduled content.

Preview must use the actual V6 frontend components/styles.

---

# 22. Publishing workflow

## 22.1 Standard workflow

```text
Draft
↓
Review
↓
Approved
↓
Publish
↓
Production
```

## 22.2 Publish actions

Support:

- Publish page.
- Publish selected changes.
- Publish all approved changes.
- Schedule publication.
- Unpublish.
- Roll back.

## 22.3 Atomic publication

A failed production build must not partially update the live site.

Required process:

1. Validate data.
2. Build staging output.
3. Run automated checks.
4. Generate preview.
5. Publish only if successful.
6. Keep previous production version available.
7. Record deployment ID.

---

# 23. Version history and rollback

Every content entity must be versioned.

Track:

- Changed field.
- Previous value.
- New value.
- User.
- Timestamp.
- Publish version.
- Approval state.

Admin must support:

- View previous version.
- Compare versions.
- Restore version.
- Roll back published site.

---

# 24. Audit log

Log:

- Login attempts.
- User creation.
- Permission changes.
- Page edits.
- Media uploads.
- Media deletes.
- Settings changes.
- SEO changes.
- Form-routing changes.
- Publish actions.
- Rollbacks.
- Inquiry exports.
- Inquiry deletion.

Audit log should be immutable for normal users.

---

# 25. Authentication

Required:

- Email/password authentication.
- Secure password hashing.
- Session management.
- Logout.
- Password reset.
- Account lockout.
- Rate limiting.
- Optional MFA.
- Admin invite workflow.

Recommended production enhancement:

- TOTP MFA.
- Single sign-on if required later.

---

# 26. Security requirements

Mandatory:

- HTTPS only.
- Secure cookies.
- CSRF protection.
- XSS protection.
- SQL injection protection.
- Parameterized queries.
- Input sanitization.
- File-type validation.
- File-size limits.
- SVG sanitization.
- MIME validation.
- Authentication throttling.
- API rate limiting.
- Security headers.
- Role-based permissions.
- Secret management.
- Encrypted sensitive configuration.
- Audit logs.
- Backup strategy.

Provider API keys must never be returned to the admin browser after saving.

---

# 27. Email configuration

The CMS settings should expose safe routing settings:

Editable:

- Recipient email.
- CC/BCC.
- Reply-to mode.
- Sender display name.
- Form notification subject.

Protected infrastructure configuration:

- Resend API key.
- Verified sender domain.
- Provider secret credentials.

Default website destination:

`muaghauri@gmail.com`

The system should send:

1. Internal inquiry notification.
2. Optional user acknowledgment email.

Email delivery must be tested in production before launch.

---

# 28. API requirements

Base path:

```text
/api/v1
```

All APIs must return JSON unless the endpoint is a media/file response.

## 28.1 Authentication

```text
POST   /api/v1/auth/login
POST   /api/v1/auth/logout
POST   /api/v1/auth/forgot-password
POST   /api/v1/auth/reset-password
GET    /api/v1/auth/me
```

## 28.2 Users

```text
GET    /api/v1/users
POST   /api/v1/users
GET    /api/v1/users/{id}
PATCH  /api/v1/users/{id}
DELETE /api/v1/users/{id}
```

## 28.3 Pages

```text
GET    /api/v1/pages
POST   /api/v1/pages
GET    /api/v1/pages/{id}
PATCH  /api/v1/pages/{id}
DELETE /api/v1/pages/{id}
POST   /api/v1/pages/{id}/duplicate
GET    /api/v1/pages/{id}/versions
POST   /api/v1/pages/{id}/restore/{versionId}
```

## 28.4 Sections

```text
GET    /api/v1/pages/{id}/sections
POST   /api/v1/pages/{id}/sections
PATCH  /api/v1/pages/{id}/sections/{sectionId}
DELETE /api/v1/pages/{id}/sections/{sectionId}
POST   /api/v1/pages/{id}/sections/reorder
```

## 28.5 Services

```text
GET    /api/v1/services
POST   /api/v1/services
GET    /api/v1/services/{id}
PATCH  /api/v1/services/{id}
DELETE /api/v1/services/{id}
```

## 28.6 Industries

```text
GET    /api/v1/industries
POST   /api/v1/industries
GET    /api/v1/industries/{id}
PATCH  /api/v1/industries/{id}
DELETE /api/v1/industries/{id}
```

## 28.7 Insights

```text
GET    /api/v1/insights
POST   /api/v1/insights
GET    /api/v1/insights/{id}
PATCH  /api/v1/insights/{id}
DELETE /api/v1/insights/{id}
```

## 28.8 Media

```text
GET    /api/v1/media
POST   /api/v1/media
GET    /api/v1/media/{id}
PATCH  /api/v1/media/{id}
DELETE /api/v1/media/{id}
```

## 28.9 Navigation

```text
GET    /api/v1/navigation
PATCH  /api/v1/navigation
```

## 28.10 Site settings

```text
GET    /api/v1/settings
PATCH  /api/v1/settings
```

## 28.11 Forms

```text
GET    /api/v1/forms
GET    /api/v1/forms/{id}
PATCH  /api/v1/forms/{id}
```

## 28.12 Inquiries

```text
GET    /api/v1/inquiries
GET    /api/v1/inquiries/{id}
PATCH  /api/v1/inquiries/{id}
DELETE /api/v1/inquiries/{id}
GET    /api/v1/inquiries/export
```

## 28.13 Assessment

```text
GET    /api/v1/assessments
GET    /api/v1/assessments/{id}
PATCH  /api/v1/assessments/{id}
```

## 28.14 SEO

```text
GET    /api/v1/seo/issues
POST   /api/v1/seo/validate
```

## 28.15 Publishing

```text
POST   /api/v1/preview
POST   /api/v1/publish
GET    /api/v1/publish/{jobId}
POST   /api/v1/publish/{jobId}/rollback
```

## 28.16 Audit

```text
GET    /api/v1/audit
```

---

# 29. API standards

Every API should use:

- RESTful routes.
- Stable resource IDs.
- JSON responses.
- Consistent error structure.
- Pagination.
- Filtering.
- Sorting.
- Validation errors by field.
- Permission checks.
- Audit-event creation.

Example error:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "The request contains invalid fields.",
    "fields": {
      "slug": "This slug is already in use."
    }
  }
}
```

---

# 30. Database entities

Recommended core tables:

- users
- roles
- permissions
- user_roles
- pages
- page_versions
- page_sections
- section_versions
- services
- industries
- insights
- insight_tags
- media
- media_usage
- navigation_items
- site_settings
- forms
- form_fields
- inquiries
- inquiry_notes
- assessments
- assessment_questions
- assessment_options
- assessment_result_rules
- redirects
- publish_jobs
- deployments
- audit_logs

Optional future:

- testimonials
- case_studies
- team_members
- client_logos
- resources
- newsletter_subscribers

---

# 31. Search and filtering inside CMS

Provide search across:

- Pages.
- Services.
- Industries.
- Insights.
- Media.
- Inquiries.

Filters:

- Status.
- Type.
- Updated by.
- Published/unpublished.
- Date range.
- SEO health.
- Assigned owner.

---

# 32. CMS design system

The admin panel should visually align with Auvorent but remain operational and efficient.

Recommended:

- Executive Navy sidebar.
- Ivory main surfaces.
- Emerald action states.
- Slate secondary text.
- Manrope headings.
- DM Sans body.
- Rounded 8–12px controls.
- Custom line icons.
- Clear data tables.
- Minimal visual noise.

The CMS should feel like a professional business platform, not a consumer dashboard.

---

# 33. Responsive admin requirements

Primary target:

- 1440px desktop.
- 1280px laptop.
- 1024px tablet landscape.

Secondary:

- 768px tablet.

Mobile editing is not required for V1 but key read-only functionality should remain usable.

---

# 34. Performance requirements

Admin:

- Dashboard usable within 2 seconds on normal broadband.
- Table pagination.
- Lazy-loaded media thumbnails.
- Optimistic saving where safe.
- Background publishing jobs.

Public site:

- No CMS JavaScript dependency for primary content.
- Optimized images.
- Minimal JS.
- Static/server-rendered HTML.
- Existing V6 performance principles preserved.

---

# 35. Accessibility requirements

CMS:

- Keyboard accessible.
- Visible focus.
- Proper form labels.
- Appropriate contrast.
- Accessible modals.
- ARIA where required.

Public site:

- Preserve current accessibility standards.
- Alt-text validation.
- Heading hierarchy validation.
- Reduced-motion support.
- Semantic output.

---

# 36. Content safeguards

The CMS should prevent or warn against:

- Fabricated testimonials.
- Fabricated client logos.
- Unverified performance statistics.
- Unsupported claims.
- Publishing empty legal placeholders.
- Publishing pages without required SEO.
- Publishing images without alt text.
- Publishing draft author credentials as facts.

Warnings do not replace human/legal review.

---

# 37. Analytics and tracking settings

Manage:

- Google Analytics ID.
- Google Tag Manager ID.
- Search Console verification.
- LinkedIn Insight Tag.
- Meta Pixel.
- Other approved tags.

The CMS must not allow arbitrary raw script injection for ordinary editors.

Third-party tracking should be gated by approved cookie/consent logic where applicable.

---

# 38. Environment management

Required environments:

- Local development.
- Staging.
- Production.

Each environment should have separate:

- Database.
- Secrets.
- email settings.
- deployment target.
- site URL.

Production data should not automatically overwrite staging.

---

# 39. Backup and recovery

Required:

- Automated database backups.
- Media backups.
- Deployment history.
- Rollback to previous deployment.
- Restoration testing.
- Retention policy.

---

# 40. Logging and monitoring

Log:

- Application errors.
- Failed API requests.
- Authentication failures.
- Email-delivery failures.
- Publish failures.
- Media failures.

Recommended:

- Error monitoring platform.
- Uptime monitoring.
- Email alert for repeated publish failure.

---

# 41. Testing requirements

## Backend tests

- Authentication.
- Authorization.
- CRUD.
- Validation.
- Publishing.
- Rollback.
- Media upload.
- Form routing.
- Inquiry storage.
- SEO validation.

## Admin UI tests

- Login.
- Edit page.
- Reorder section.
- Upload image.
- Save draft.
- Preview.
- Publish.
- Rollback.
- Change contact recipient.
- Manage SEO.

## Integration tests

- CMS change → preview.
- CMS change → publish.
- Public page reflects approved content.
- Sitemap updated.
- Contact inquiry stored.
- Contact email delivered.
- Rollback restores previous output.

## Responsive tests

Website:

- 320.
- 375.
- 768.
- 1024.
- 1280.
- 1440.
- 1920.

Admin:

- 768.
- 1024.
- 1280.
- 1440.

---

# 42. Acceptance criteria

The CMS V1 is complete when an authorized admin can:

1. Log in securely.
2. Edit every visible text section of the V6 website.
3. Replace every managed image.
4. Replace every managed icon.
5. Edit navigation.
6. Edit footer content.
7. Edit all services.
8. Edit all industries.
9. Add/edit/delete insights.
10. Edit Business Optimization Check content.
11. Edit contact form labels/options.
12. Change the contact recipient email.
13. Edit SEO metadata on every page.
14. Preview draft changes.
15. Publish without editing source code.
16. Roll back to a previous version.
17. View inquiries.
18. Manage media.
19. View publishing history.
20. View an audit history of changes.
21. Publish without breaking the V6 design.
22. Maintain SEO-friendly output.
23. Maintain desktop/mobile responsiveness.

---

# 43. Phase plan

## Phase 1 — Content-model extraction

- Extract all hardcoded V6 content from `build.py`.
- Define database schema.
- Create migration/seed data.
- Assign stable IDs.
- Preserve exact public routes.

## Phase 2 — CMS backend and APIs

- Authentication.
- Users/roles.
- Page APIs.
- Section APIs.
- Media APIs.
- Settings.
- Forms.
- Inquiries.
- Publishing.
- Audit.

## Phase 3 — Admin UI

- Login.
- Dashboard.
- Pages.
- Section editor.
- Services.
- Industries.
- Insights.
- Media.
- Forms.
- SEO.
- Settings.
- Inquiries.
- Users.
- Audit.

## Phase 4 — Website integration

- Update website renderer to use CMS-managed content.
- Add staging preview.
- Connect publish process.
- Preserve V6 design and URLs.

## Phase 5 — QA and production hardening

- Security.
- Responsive checks.
- SEO validation.
- Accessibility.
- Email delivery.
- Backups.
- Rollback.
- Production deployment.

---

# 44. Out of scope for initial CMS V1

Unless separately approved:

- Ecommerce.
- Payments.
- CRM replacement.
- Full marketing automation.
- Live chat.
- Client portal.
- Multi-language publishing.
- Multi-site management.
- Complex workflow automation.
- Advanced DAM.
- AI-generated auto-publishing.
- Public user accounts.

The architecture should allow these later without forcing a complete rebuild.

---

# 45. Future-ready extensions

Potential later modules:

- Case studies.
- Testimonials.
- Team profiles.
- Client logos.
- Newsletter.
- Lead scoring.
- CRM integration.
- HubSpot.
- Salesforce.
- Calendly.
- Advanced analytics.
- A/B testing.
- Multi-language.
- Multi-region SEO.
- Resource downloads.
- Webinar/event management.
- AI-assisted drafting with human approval.
- AI SEO recommendations.
- Automated image resizing.
- Scheduled campaigns.

---

# 46. Implementation principles

1. **CMS manages content; frontend controls presentation.**
2. **Editors should not need code.**
3. **The approved V6 design must not be breakable through ordinary CMS edits.**
4. **SEO-critical content must remain server-rendered/static.**
5. **Draft content must never appear publicly before publication.**
6. **Sensitive credentials must remain server-side.**
7. **All important changes should be auditable.**
8. **Every publish should be reversible.**
9. **No fabricated business claims should be introduced through seed data.**
10. **The CMS should scale from one administrator to a larger advisory company.**

---

# 47. Recommended initial technology stack

This is a recommended implementation path, not a mandatory constraint.

## Backend

- Python FastAPI
- PostgreSQL
- SQLAlchemy
- Alembic migrations
- Pydantic validation

## Admin frontend

- React
- TypeScript
- Vite or Next.js admin application
- Reusable design-system components

## Public website

- Existing V6 build system initially
- Evolve current `build.py` to read published CMS content
- Retain static output

## Storage

- Cloudflare R2 or AWS S3

## Email

- Resend

## Hosting

- Cloudflare Pages for public website
- Cloudflare-compatible or container hosting for CMS API
- Managed PostgreSQL

---

# 48. Final implementation deliverables

The completed CMS package should include:

- Admin Panel source.
- CMS backend source.
- Database schema.
- Migrations.
- Seed content matching V6.
- API documentation.
- `.env.example`.
- Local setup guide.
- Deployment guide.
- Role/permission matrix.
- Security notes.
- Backup/restore guide.
- Publishing workflow guide.
- Automated tests.
- Integration tests.
- Website connector.
- API endpoint specification.
- Production checklist.
- Separate Admin/CMS ZIP package.

---

# 49. Definition of success

The CMS is successful when Auvorent can operate the website as a managed business platform rather than a static development project.

A non-technical administrator should be able to update content, imagery, services, industries, insights, forms, SEO, and global website settings safely—while the live website continues to look like the approved premium Executive Intelligence brand and remains technically optimized for search, performance, accessibility, and future growth.
