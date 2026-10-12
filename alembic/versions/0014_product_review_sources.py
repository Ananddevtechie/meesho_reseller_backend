"""Track source review IDs to prevent duplicate imports.

Revision ID: 0014_product_review_sources
Revises: 0013_product_images
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0014_product_review_sources'
down_revision: Union[str, None] = '0013_product_images'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
	op.add_column('product_reviews', sa.Column('source_review_id', sa.String(length=120), nullable=True))
	op.create_unique_constraint(
		'uq_product_reviews_source_review',
		'product_reviews',
		['product_id', 'source_review_id'],
	)


def downgrade() -> None:
	op.drop_constraint('uq_product_reviews_source_review', 'product_reviews', type_='unique')
	op.drop_column('product_reviews', 'source_review_id')
