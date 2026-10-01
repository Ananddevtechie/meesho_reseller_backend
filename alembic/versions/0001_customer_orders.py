"""Create the customer orders table.

Revision ID: 0001_customer_orders
Revises:
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0001_customer_orders'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
	op.create_table(
		'customer_orders',
		sa.Column('id', sa.String(length=40), nullable=False),
		sa.Column('idempotency_key', sa.String(length=128), nullable=False),
		sa.Column('request_fingerprint', sa.String(length=64), nullable=False),
		sa.Column('product_id', sa.String(length=100), nullable=False),
		sa.Column('product_sku', sa.String(length=100), nullable=False),
		sa.Column('product_title', sa.String(length=255), nullable=False),
		sa.Column('quantity', sa.Integer(), nullable=False),
		sa.Column('unit_price', sa.Numeric(precision=12, scale=2), nullable=False),
		sa.Column('mrp', sa.Numeric(precision=12, scale=2), nullable=False),
		sa.Column('subtotal', sa.Numeric(precision=12, scale=2), nullable=False),
		sa.Column('discount', sa.Numeric(precision=12, scale=2), nullable=False),
		sa.Column('shipping', sa.Numeric(precision=12, scale=2), nullable=False),
		sa.Column('tax', sa.Numeric(precision=12, scale=2), nullable=False),
		sa.Column('cod_fee', sa.Numeric(precision=12, scale=2), nullable=False),
		sa.Column('total', sa.Numeric(precision=12, scale=2), nullable=False),
		sa.Column('currency', sa.String(length=3), nullable=False),
		sa.Column('payment_method', sa.String(length=20), nullable=False),
		sa.Column('payment_status', sa.String(length=30), nullable=False),
		sa.Column('order_status', sa.String(length=30), nullable=False),
		sa.Column('payment_reference', sa.String(length=255), nullable=True),
		sa.Column('customer_name', sa.String(length=120), nullable=False),
		sa.Column('customer_email', sa.String(length=255), nullable=True),
		sa.Column('customer_mobile', sa.String(length=20), nullable=False),
		sa.Column('alternate_mobile', sa.String(length=20), nullable=True),
		sa.Column('address_line1', sa.String(length=255), nullable=False),
		sa.Column('address_line2', sa.String(length=255), nullable=False),
		sa.Column('landmark', sa.String(length=255), nullable=True),
		sa.Column('city', sa.String(length=100), nullable=False),
		sa.Column('state', sa.String(length=100), nullable=False),
		sa.Column('pincode', sa.String(length=6), nullable=False),
		sa.Column('expected_delivery_range', sa.String(length=120), nullable=False),
		sa.Column('email_status', sa.String(length=20), nullable=False),
		sa.Column('email_attempts', sa.Integer(), nullable=False),
		sa.Column('email_error', sa.Text(), nullable=True),
		sa.Column('whatsapp_opt_in', sa.Boolean(), nullable=False),
		sa.Column('whatsapp_status', sa.String(length=30), nullable=False),
		sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
		sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
		sa.PrimaryKeyConstraint('id'),
		sa.UniqueConstraint('idempotency_key', name='uq_customer_orders_idempotency_key'),
	)


def downgrade() -> None:
	op.drop_table('customer_orders')