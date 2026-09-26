"""Foundation schema — users, opaque sessions, login attempts, append-only audit.

Revision ID: 0001_foundation
Revises:
"""
from alembic import op
import sqlalchemy as sa

revision = '0001_foundation'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('cms_users',
        sa.Column('id',sa.String(length=36),primary_key=True),
        sa.Column('email',sa.String(length=320),nullable=False),
        sa.Column('full_name',sa.String(length=120),nullable=False),
        sa.Column('password_hash',sa.String(length=300),nullable=False),
        sa.Column('role',sa.String(length=32),nullable=False),
        sa.Column('is_active',sa.Boolean(),nullable=False),
        sa.Column('must_change_password',sa.Boolean(),nullable=False),
        sa.Column('failed_login_attempts',sa.Integer(),nullable=False),
        sa.Column('locked_until',sa.DateTime(),nullable=True),
        sa.Column('created_at',sa.DateTime(),nullable=False),
        sa.Column('updated_at',sa.DateTime(),nullable=False),
        sa.Column('last_login_at',sa.DateTime(),nullable=True),
    )
    op.create_index('ix_cms_users_email','cms_users',['email'],unique=True)
    op.create_index('ix_cms_users_role','cms_users',['role'],unique=False)
    op.create_table('cms_sessions',
        sa.Column('id',sa.String(length=36),primary_key=True),
        sa.Column('user_id',sa.String(length=36),sa.ForeignKey('cms_users.id'),nullable=False),
        sa.Column('token_hash',sa.String(length=64),nullable=False),
        sa.Column('created_at',sa.DateTime(),nullable=False),
        sa.Column('expires_at',sa.DateTime(),nullable=False),
        sa.Column('revoked_at',sa.DateTime(),nullable=True),
    )
    op.create_index('ix_cms_sessions_user_id','cms_sessions',['user_id'],unique=False)
    op.create_index('ix_cms_sessions_token_hash','cms_sessions',['token_hash'],unique=True)
    op.create_index('ix_cms_sessions_expires_at','cms_sessions',['expires_at'],unique=False)
    op.create_table('cms_login_attempts',
        sa.Column('id',sa.Integer(),primary_key=True,autoincrement=True),
        sa.Column('email',sa.String(length=320),nullable=False),
        sa.Column('ip_hash',sa.String(length=64),nullable=False),
        sa.Column('succeeded',sa.Boolean(),nullable=False),
        sa.Column('created_at',sa.DateTime(),nullable=False),
    )
    op.create_index('ix_cms_login_attempts_email','cms_login_attempts',['email'],unique=False)
    op.create_index('ix_cms_login_attempts_ip_hash','cms_login_attempts',['ip_hash'],unique=False)
    op.create_index('ix_cms_login_attempts_created_at','cms_login_attempts',['created_at'],unique=False)
    op.create_index('ix_cms_login_attempts_ip_created','cms_login_attempts',['ip_hash','created_at'],unique=False)
    op.create_table('cms_audit_logs',
        sa.Column('id',sa.Integer(),primary_key=True,autoincrement=True),
        sa.Column('actor_user_id',sa.String(length=36),nullable=True),
        sa.Column('action',sa.String(length=80),nullable=False),
        sa.Column('target_type',sa.String(length=64),nullable=False),
        sa.Column('target_id',sa.String(length=80),nullable=True),
        sa.Column('detail',sa.Text(),nullable=False),
        sa.Column('created_at',sa.DateTime(),nullable=False),
    )
    op.create_index('ix_cms_audit_logs_actor_user_id','cms_audit_logs',['actor_user_id'],unique=False)
    op.create_index('ix_cms_audit_logs_action','cms_audit_logs',['action'],unique=False)
    op.create_index('ix_cms_audit_logs_created_at','cms_audit_logs',['created_at'],unique=False)

def downgrade():
    op.drop_table('cms_audit_logs')
    op.drop_table('cms_login_attempts')
    op.drop_table('cms_sessions')
    op.drop_table('cms_users')
