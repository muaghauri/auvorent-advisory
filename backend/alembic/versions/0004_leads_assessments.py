"""Phase 4: editable forms, lead routing, inquiries, assessments.

Revision ID: 0004_leads_assessments
Revises: 0003_collections_media
"""
from alembic import op
import sqlalchemy as sa
revision='0004_leads_assessments'
down_revision='0003_collections_media'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('cms_forms',
        sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('slug',sa.String(100),nullable=False),
        sa.Column('title',sa.String(180),nullable=False),
        sa.Column('intro',sa.Text(),nullable=False,server_default=''),
        sa.Column('success_message',sa.String(500),nullable=False,server_default='Thank you. We will review your inquiry.'),
        sa.Column('fields_json',sa.Text(),nullable=False,server_default='[]'),
        sa.Column('is_active',sa.Boolean(),nullable=False,server_default=sa.false()),
        sa.Column('created_at',sa.DateTime(),nullable=False),
        sa.Column('updated_at',sa.DateTime(),nullable=False))
    op.create_index('ix_cms_forms_slug','cms_forms',['slug'],unique=True)
    op.create_table('cms_lead_settings',
        sa.Column('id',sa.String(20),primary_key=True),
        sa.Column('recipient_email',sa.String(254),nullable=False,server_default='muaghauri@gmail.com'),
        sa.Column('cc_json',sa.Text(),nullable=False,server_default='[]'),
        sa.Column('reply_enabled',sa.Boolean(),nullable=False,server_default=sa.false()),
        sa.Column('subject_prefix',sa.String(100),nullable=False,server_default='Auvorent inquiry'),
        sa.Column('updated_at',sa.DateTime(),nullable=False))
    op.create_table('cms_inquiries',
        sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('form_id',sa.String(36),sa.ForeignKey('cms_forms.id',ondelete='RESTRICT'),nullable=False),
        sa.Column('name',sa.String(180),nullable=False,server_default=''),
        sa.Column('email',sa.String(254),nullable=False,server_default=''),
        sa.Column('company',sa.String(180),nullable=False,server_default=''),
        sa.Column('priority',sa.String(160),nullable=False,server_default=''),
        sa.Column('answers_json',sa.Text(),nullable=False,server_default='{}'),
        sa.Column('source_page',sa.String(300),nullable=False,server_default=''),
        sa.Column('utm_json',sa.Text(),nullable=False,server_default='{}'),
        sa.Column('consent',sa.Boolean(),nullable=False,server_default=sa.false()),
        sa.Column('ip_hash',sa.String(64),nullable=False),
        sa.Column('status',sa.String(24),nullable=False,server_default='new'),
        sa.Column('assigned_user_id',sa.String(36),sa.ForeignKey('cms_users.id',ondelete='SET NULL'),nullable=True),
        sa.Column('notification_status',sa.String(24),nullable=False,server_default='pending'),
        sa.Column('notification_attempts',sa.Integer(),nullable=False,server_default='0'),
        sa.Column('notified_at',sa.DateTime(),nullable=True),
        sa.Column('created_at',sa.DateTime(),nullable=False),
        sa.Column('updated_at',sa.DateTime(),nullable=False))
    for col in ('form_id','ip_hash','status','created_at'):
        op.create_index('ix_cms_inquiries_'+col,'cms_inquiries',[col])
    op.create_table('cms_inquiry_notes',
        sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('inquiry_id',sa.String(36),sa.ForeignKey('cms_inquiries.id',ondelete='CASCADE'),nullable=False),
        sa.Column('author_id',sa.String(36),sa.ForeignKey('cms_users.id',ondelete='SET NULL'),nullable=True),
        sa.Column('text',sa.Text(),nullable=False),
        sa.Column('created_at',sa.DateTime(),nullable=False))
    op.create_index('ix_cms_inquiry_notes_inquiry_id','cms_inquiry_notes',['inquiry_id'])
    op.create_table('cms_assessments',
        sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('slug',sa.String(100),nullable=False),
        sa.Column('title',sa.String(200),nullable=False),
        sa.Column('intro',sa.Text(),nullable=False,server_default=''),
        sa.Column('disclaimer',sa.String(600),nullable=False,server_default='This is a preliminary screening, not a verified business diagnosis.'),
        sa.Column('questions_json',sa.Text(),nullable=False,server_default='[]'),
        sa.Column('results_json',sa.Text(),nullable=False,server_default='{}'),
        sa.Column('cta_label',sa.String(100),nullable=False,server_default='Request a strategy conversation'),
        sa.Column('cta_url',sa.String(300),nullable=False,server_default='/contact/'),
        sa.Column('is_active',sa.Boolean(),nullable=False,server_default=sa.false()),
        sa.Column('created_at',sa.DateTime(),nullable=False),
        sa.Column('updated_at',sa.DateTime(),nullable=False))
    op.create_index('ix_cms_assessments_slug','cms_assessments',['slug'],unique=True)

def downgrade():
    op.drop_table('cms_inquiry_notes')
    op.drop_table('cms_inquiries')
    op.drop_table('cms_assessments')
    op.drop_table('cms_forms')
    op.drop_table('cms_lead_settings')
