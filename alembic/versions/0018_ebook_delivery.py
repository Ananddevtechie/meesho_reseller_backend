"""Add secure delivery records for Book-category digital products.

Revision ID: 0018_ebook_delivery
Revises: 0017_order_now_clicks
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0018_ebook_delivery'
down_revision: Union[str, None] = '0017_order_now_clicks'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
	op.add_column('products', sa.Column('ebook_storage_path', sa.Text(), nullable=True))

	op.create_table(
		'ebook_order_access',
		sa.Column('order_id', sa.String(length=40), nullable=False),
		sa.Column('token_hash', sa.String(length=64), nullable=False),
		sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
		sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
		sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ondelete='CASCADE'),
		sa.PrimaryKeyConstraint('order_id'),
		sa.UniqueConstraint('token_hash', name='uq_ebook_order_access_token_hash'),
	)

	op.create_table(
		'ebook_entitlements',
		sa.Column('id', sa.String(length=36), nullable=False),
		sa.Column('order_id', sa.String(length=40), nullable=False),
		sa.Column('product_id', sa.String(length=100), nullable=False),
		sa.Column('storage_path', sa.Text(), nullable=False),
		sa.Column('download_count', sa.Integer(), nullable=False),
		sa.Column('download_limit', sa.Integer(), nullable=False),
		sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
		sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
		sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
		sa.CheckConstraint('download_count >= 0', name='ck_ebook_entitlements_download_count'),
		sa.CheckConstraint('download_limit > 0', name='ck_ebook_entitlements_download_limit'),
		sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ondelete='CASCADE'),
		sa.PrimaryKeyConstraint('id'),
		sa.UniqueConstraint('order_id', name='uq_ebook_entitlements_order_id'),
	)
	op.create_index('ix_ebook_entitlements_expiry', 'ebook_entitlements', ['expires_at'])

	op.create_table(
		'ebook_download_tokens',
		sa.Column('id', sa.String(length=36), nullable=False),
		sa.Column('entitlement_id', sa.String(length=36), nullable=False),
		sa.Column('token_hash', sa.String(length=64), nullable=False),
		sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
		sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
		sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
		sa.ForeignKeyConstraint(['entitlement_id'], ['ebook_entitlements.id'], ondelete='CASCADE'),
		sa.PrimaryKeyConstraint('id'),
		sa.UniqueConstraint('token_hash', name='uq_ebook_download_tokens_token_hash'),
	)
	op.create_index(
		'ix_ebook_download_tokens_entitlement_id',
		'ebook_download_tokens',
		['entitlement_id'],
	)

	op.create_table(
		'ebook_email_jobs',
		sa.Column('id', sa.String(length=36), nullable=False),
		sa.Column('entitlement_id', sa.String(length=36), nullable=False),
		sa.Column('status', sa.String(length=20), nullable=False),
		sa.Column('attempts', sa.Integer(), nullable=False),
		sa.Column('next_attempt_at', sa.DateTime(timezone=True), nullable=False),
		sa.Column('locked_at', sa.DateTime(timezone=True), nullable=True),
		sa.Column('last_error', sa.Text(), nullable=True),
		sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
		sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
		sa.ForeignKeyConstraint(['entitlement_id'], ['ebook_entitlements.id'], ondelete='CASCADE'),
		sa.PrimaryKeyConstraint('id'),
		sa.UniqueConstraint('entitlement_id', name='uq_ebook_email_jobs_entitlement_id'),
	)
	op.create_index(
		'ix_ebook_email_jobs_ready',
		'ebook_email_jobs',
		['status', 'next_attempt_at'],
	)

	for table_name in (
		'ebook_order_access',
		'ebook_entitlements',
		'ebook_download_tokens',
		'ebook_email_jobs',
	):
		op.execute(f'ALTER TABLE public.{table_name} ENABLE ROW LEVEL SECURITY')

	op.execute(
		"""
		INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
		VALUES ('ebooks', 'ebooks', FALSE, 52428800, ARRAY['application/pdf']::text[])
		ON CONFLICT (id) DO UPDATE
		SET public = FALSE,
		    file_size_limit = 52428800,
		    allowed_mime_types = ARRAY['application/pdf']::text[]
		"""
	)


def downgrade() -> None:
	op.drop_index('ix_ebook_email_jobs_ready', table_name='ebook_email_jobs')
	op.drop_table('ebook_email_jobs')
	op.drop_index('ix_ebook_download_tokens_entitlement_id', table_name='ebook_download_tokens')
	op.drop_table('ebook_download_tokens')
	op.drop_index('ix_ebook_entitlements_expiry', table_name='ebook_entitlements')
	op.drop_table('ebook_entitlements')
	op.drop_table('ebook_order_access')
	op.drop_column('products', 'ebook_storage_path')
