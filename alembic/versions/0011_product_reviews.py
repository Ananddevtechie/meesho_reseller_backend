"""Add product reviews and uploaded review images.

Revision ID: 0011_product_reviews
Revises: 0010_product_meesho_url
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0011_product_reviews'
down_revision: Union[str, None] = '0010_product_meesho_url'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
	op.create_table(
		'product_reviews',
		sa.Column('id', sa.String(length=36), nullable=False),
		sa.Column('product_id', sa.String(length=100), nullable=False),
		sa.Column('reviewer_name', sa.String(length=120), nullable=False),
		sa.Column('rating', sa.Integer(), nullable=False),
		sa.Column('comment', sa.Text(), nullable=False),
		sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
		sa.CheckConstraint('rating >= 1 AND rating <= 5', name='ck_product_reviews_rating_range'),
		sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='CASCADE'),
		sa.PrimaryKeyConstraint('id'),
	)
	op.create_table(
		'product_review_images',
		sa.Column('id', sa.String(length=36), nullable=False),
		sa.Column('review_id', sa.String(length=36), nullable=False),
		sa.Column('content_type', sa.String(length=40), nullable=False),
		sa.Column('image_data', sa.LargeBinary(), nullable=False),
		sa.ForeignKeyConstraint(['review_id'], ['product_reviews.id'], ondelete='CASCADE'),
		sa.PrimaryKeyConstraint('id'),
	)


def downgrade() -> None:
	op.drop_table('product_review_images')
	op.drop_table('product_reviews')