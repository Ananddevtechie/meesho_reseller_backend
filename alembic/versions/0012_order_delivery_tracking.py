"""Add delivery tracking state and event history.

Revision ID: 0012_order_delivery_tracking
Revises: 0011_product_reviews
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0012_order_delivery_tracking'
down_revision: Union[str, None] = '0011_product_reviews'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
	op.add_column(
		'orders',
		sa.Column(
			'delivery_status',
			sa.String(length=40),
			server_default='ORDER_CONFIRMED',
			nullable=False,
		),
	)
	op.add_column('orders', sa.Column('estimated_delivery_date', sa.Date(), nullable=True))
	op.create_table(
		'order_tracking_events',
		sa.Column('id', sa.String(length=36), nullable=False),
		sa.Column('order_id', sa.String(length=40), nullable=False),
		sa.Column('status', sa.String(length=40), nullable=False),
		sa.Column('estimated_delivery_date', sa.Date(), nullable=True),
		sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
		sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ondelete='CASCADE'),
		sa.PrimaryKeyConstraint('id'),
	)
	op.create_index('ix_order_tracking_events_order_id', 'order_tracking_events', ['order_id'])
	op.execute(
		sa.text(
			"INSERT INTO order_tracking_events (id, order_id, status, estimated_delivery_date, created_at) "
			"SELECT md5(id), id, 'ORDER_CONFIRMED', NULL, created_at FROM orders "
			"WHERE order_status = 'PLACED' AND payment_status IN ('PAID', 'COD_PENDING')"
		)
	)


def downgrade() -> None:
	op.drop_index('ix_order_tracking_events_order_id', table_name='order_tracking_events')
	op.drop_table('order_tracking_events')
	op.drop_column('orders', 'estimated_delivery_date')
	op.drop_column('orders', 'delivery_status')
