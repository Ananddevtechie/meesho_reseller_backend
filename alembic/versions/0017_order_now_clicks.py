"""Track storefront Order now clicks per product.

Revision ID: 0017_order_now_clicks
Revises: 0016_review_pagination
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0017_order_now_clicks'
down_revision: Union[str, None] = '0016_review_pagination'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
	op.add_column(
		'products',
		sa.Column('order_now_clicks', sa.Integer(), server_default='0', nullable=False),
	)


def downgrade() -> None:
	op.drop_column('products', 'order_now_clicks')
