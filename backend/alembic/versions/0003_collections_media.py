"""Phase 3: collections, media, relationships and asset usage"""
from alembic import op
import sqlalchemy as sa
revision = '0003_collections_media'
down_revision = '0002_page_studio'
branch_labels = None
depends_on = None

def upgrade():
    # Reconcile a missing Phase 2 index so the migrated schema matches the ORM.
    op.create_index('ix_cms_content_revisions_actor_user_id','cms_content_revisions',['actor_user_id'])
    op.create_table('cms_media_assets',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('original_name', sa.String(240), nullable=False),
        sa.Column('storage_name', sa.String(100), nullable=False, unique=True),
        sa.Column('sha256', sa.String(64), nullable=False),
        sa.Column('mime_type', sa.String(90), nullable=False),
        sa.Column('kind', sa.String(24), nullable=False),
        sa.Column('icon_style', sa.String(16), nullable=True),
        sa.Column('byte_size', sa.Integer(), nullable=False),
        sa.Column('width', sa.Integer(), nullable=True),
        sa.Column('height', sa.Integer(), nullable=True),
        sa.Column('alt_text', sa.String(300), nullable=False, server_default=''),
        sa.Column('caption', sa.String(500), nullable=False, server_default=''),
        sa.Column('source_notes', sa.String(500), nullable=False, server_default=''),
        sa.Column('decorative', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_by', sa.String(36), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_cms_media_assets_kind','cms_media_assets',['kind'])
    op.create_index('ix_cms_media_assets_sha256','cms_media_assets',['sha256'])
    op.create_table('cms_collection_entries',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('kind', sa.String(32), nullable=False),
        sa.Column('title', sa.String(200), nullable=False),
        sa.Column('slug', sa.String(180), nullable=False),
        sa.Column('summary', sa.Text(), nullable=False, server_default=''),
        sa.Column('body_markdown', sa.Text(), nullable=False, server_default=''),
        sa.Column('content_json', sa.Text(), nullable=False, server_default='{}'),
        sa.Column('status', sa.String(24), nullable=False, server_default='draft'),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_featured', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('hero_media_id', sa.String(36), sa.ForeignKey('cms_media_assets.id',ondelete='SET NULL'),nullable=True),
        sa.Column('icon_media_id', sa.String(36), sa.ForeignKey('cms_media_assets.id',ondelete='SET NULL'),nullable=True),
        sa.Column('seo_title', sa.String(180), nullable=False, server_default=''),
        sa.Column('meta_description', sa.String(320), nullable=False, server_default=''),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_cms_collection_entries_kind','cms_collection_entries',['kind'])
    op.create_index('ix_cms_collection_entries_status','cms_collection_entries',['status'])
    op.create_index('uq_cms_collection_kind_slug','cms_collection_entries',['kind','slug'],unique=True)
    op.create_table('cms_collection_relationships',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('source_id', sa.String(36), sa.ForeignKey('cms_collection_entries.id', ondelete='CASCADE'),nullable=False),
        sa.Column('target_id', sa.String(36), sa.ForeignKey('cms_collection_entries.id', ondelete='CASCADE'),nullable=False),
        sa.Column('relation', sa.String(40), nullable=False, server_default='related'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_cms_collection_relationships_source_id','cms_collection_relationships',['source_id'])
    op.create_index('ix_cms_collection_relationships_target_id','cms_collection_relationships',['target_id'])
    op.create_index('uq_cms_collection_relationship','cms_collection_relationships',['source_id','target_id','relation'],unique=True)
    op.create_table('cms_media_usages',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('media_id',sa.String(36),sa.ForeignKey('cms_media_assets.id',ondelete='CASCADE'),nullable=False),
        sa.Column('owner_type',sa.String(32),nullable=False),
        sa.Column('owner_id',sa.String(36),nullable=False),
        sa.Column('slot',sa.String(36),nullable=False),
        sa.Column('created_at',sa.DateTime(),nullable=False),
    )
    op.create_index('ix_cms_media_usages_media_id','cms_media_usages',['media_id'])
    op.create_index('ix_cms_media_usages_owner_id','cms_media_usages',['owner_id'])
    op.create_index('uq_cms_media_usage','cms_media_usages',['media_id','owner_type','owner_id','slot'],unique=True)

def downgrade():
    op.drop_table('cms_media_usages')
    op.drop_table('cms_collection_relationships')
    op.drop_table('cms_collection_entries')
    op.drop_table('cms_media_assets')
    op.drop_index('ix_cms_content_revisions_actor_user_id',table_name='cms_content_revisions')
