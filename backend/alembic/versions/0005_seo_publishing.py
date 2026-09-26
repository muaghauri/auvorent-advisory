"""Phase 5: SEO metadata, editorial reviews, redirects and local staging deployments.

Revision ID: 0005_seo_publishing
Revises: 0004_leads_assessments
"""
from alembic import op
import sqlalchemy as sa

revision='0005_seo_publishing'
down_revision='0004_leads_assessments'
branch_labels=None
depends_on=None


def upgrade():
    op.create_table('cms_seo_records',
        sa.Column('id',sa.String(36),primary_key=True), sa.Column('entity_type',sa.String(32),nullable=False),
        sa.Column('entity_id',sa.String(36),nullable=False), sa.Column('seo_title',sa.String(180),nullable=False),
        sa.Column('meta_description',sa.String(320),nullable=False),sa.Column('canonical_override',sa.String(512),nullable=False),
        sa.Column('robots_index',sa.Boolean(),nullable=False),sa.Column('robots_follow',sa.Boolean(),nullable=False),
        sa.Column('og_title',sa.String(180),nullable=False),sa.Column('og_description',sa.String(320),nullable=False),
        sa.Column('og_image_media_id',sa.String(36),sa.ForeignKey('cms_media_assets.id',ondelete='SET NULL'),nullable=True),
        sa.Column('schema_type',sa.String(32),nullable=False),sa.Column('breadcrumb_title',sa.String(180),nullable=False),
        sa.Column('updated_at',sa.DateTime(),nullable=False))
    op.create_index('ix_cms_seo_records_entity_type','cms_seo_records',['entity_type'])
    op.create_index('ix_cms_seo_records_entity_id','cms_seo_records',['entity_id'])
    op.create_index('uq_cms_seo_entity','cms_seo_records',['entity_type','entity_id'],unique=True)
    op.create_table('cms_redirects',sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('old_path',sa.String(255),nullable=False),sa.Column('new_path',sa.String(255),nullable=False),
        sa.Column('status_code',sa.Integer(),nullable=False),sa.Column('is_active',sa.Boolean(),nullable=False),
        sa.Column('note',sa.String(300),nullable=False),sa.Column('updated_at',sa.DateTime(),nullable=False))
    op.create_index('ix_cms_redirects_old_path','cms_redirects',['old_path'],unique=True)
    op.create_table('cms_editorial_reviews',sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('entity_type',sa.String(32),nullable=False),sa.Column('entity_id',sa.String(36),nullable=False),
        sa.Column('state',sa.String(24),nullable=False),sa.Column('content_hash',sa.String(64),nullable=False),
        sa.Column('requested_by',sa.String(36),nullable=False),sa.Column('reviewed_by',sa.String(36),nullable=True),
        sa.Column('note',sa.String(1000),nullable=False),sa.Column('requested_at',sa.DateTime(),nullable=False),
        sa.Column('decided_at',sa.DateTime(),nullable=True))
    op.create_index('ix_cms_editorial_reviews_entity_type','cms_editorial_reviews',['entity_type'])
    op.create_index('ix_cms_editorial_reviews_entity_id','cms_editorial_reviews',['entity_id'])
    op.create_index('ix_cms_editorial_reviews_state','cms_editorial_reviews',['state'])
    op.create_table('cms_private_previews',sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('token_hash',sa.String(64),nullable=False),sa.Column('entity_type',sa.String(32),nullable=False),
        sa.Column('entity_id',sa.String(36),nullable=False),sa.Column('snapshot_json',sa.Text(),nullable=False),
        sa.Column('created_by',sa.String(36),nullable=False),sa.Column('expires_at',sa.DateTime(),nullable=False))
    op.create_index('ix_cms_private_previews_token_hash','cms_private_previews',['token_hash'],unique=True)
    op.create_table('cms_publish_deployments',sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('release_id',sa.String(72),nullable=True),sa.Column('status',sa.String(24),nullable=False),
        sa.Column('environment',sa.String(32),nullable=False),sa.Column('scheduled_for',sa.DateTime(),nullable=True),
        sa.Column('requested_by',sa.String(36),nullable=False),sa.Column('report_json',sa.Text(),nullable=False),
        sa.Column('error_message',sa.String(1000),nullable=False),sa.Column('created_at',sa.DateTime(),nullable=False),
        sa.Column('completed_at',sa.DateTime(),nullable=True))
    op.create_index('ix_cms_publish_deployments_status','cms_publish_deployments',['status'])
    op.create_index('uq_cms_publish_release','cms_publish_deployments',['release_id'],unique=True)


def downgrade():
    op.drop_table('cms_publish_deployments')
    op.drop_table('cms_private_previews')
    op.drop_table('cms_editorial_reviews')
    op.drop_table('cms_redirects')
    op.drop_table('cms_seo_records')
