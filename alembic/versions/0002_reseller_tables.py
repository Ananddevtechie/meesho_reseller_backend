"""Add reseller tables and normalize order ownership.

Revision ID: 0002_reseller_tables
Revises: 0001_customer_orders
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0002_reseller_tables'
down_revision: Union[str, None] = '0001_customer_orders'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
	op.create_table(
		'users',
		sa.Column('id', sa.String(length=36), nullable=False),
		sa.Column('full_name', sa.String(length=120), nullable=False),
		sa.Column('email', sa.String(length=255), nullable=False),
		sa.Column('password_hash', sa.String(length=255), nullable=False),
		sa.Column('role', sa.String(length=30), nullable=False),
		sa.Column('is_active', sa.Boolean(), nullable=False),
		sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
		sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
		sa.PrimaryKeyConstraint('id'),
		sa.UniqueConstraint('email', name='uq_users_email'),
	)
	op.create_table(
		'products',
		sa.Column('id', sa.String(length=100), nullable=False),
		sa.Column('sku', sa.String(length=100), nullable=False),
		sa.Column('title', sa.String(length=255), nullable=False),
		sa.Column('description', sa.Text(), nullable=True),
		sa.Column('image_url', sa.Text(), nullable=True),
		sa.Column('cost_price', sa.Numeric(precision=12, scale=2), nullable=False),
		sa.Column('selling_price', sa.Numeric(precision=12, scale=2), nullable=False),
		sa.Column('mrp', sa.Numeric(precision=12, scale=2), nullable=False),
		sa.Column('stock_quantity', sa.Integer(), nullable=False),
		sa.Column('is_active', sa.Boolean(), nullable=False),
		sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
		sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
		sa.PrimaryKeyConstraint('id'),
		sa.UniqueConstraint('sku', name='uq_products_sku'),
	)
	op.create_table(
		'customers',
		sa.Column('id', sa.String(length=36), nullable=False),
		sa.Column('full_name', sa.String(length=120), nullable=False),
		sa.Column('email', sa.String(length=255), nullable=True),
		sa.Column('mobile', sa.String(length=20), nullable=False),
		sa.Column('alternate_mobile', sa.String(length=20), nullable=True),
		sa.Column('address_line1', sa.String(length=255), nullable=False),
		sa.Column('address_line2', sa.String(length=255), nullable=False),
		sa.Column('landmark', sa.String(length=255), nullable=True),
		sa.Column('city', sa.String(length=100), nullable=False),
		sa.Column('state', sa.String(length=100), nullable=False),
		sa.Column('pincode', sa.String(length=6), nullable=False),
		sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
		sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
		sa.PrimaryKeyConstraint('id'),
	)
	op.rename_table('customer_orders', 'orders')
	op.execute('ALTER TABLE orders RENAME CONSTRAINT uq_customer_orders_idempotency_key TO uq_orders_idempotency_key')
	op.add_column('orders', sa.Column('user_id', sa.String(length=36), nullable=True))
	op.add_column('orders', sa.Column('customer_id', sa.String(length=36), nullable=True))
	op.create_foreign_key('fk_orders_user_id_users', 'orders', 'users', ['user_id'], ['id'])
	op.create_foreign_key('fk_orders_customer_id_customers', 'orders', 'customers', ['customer_id'], ['id'])
	op.create_table(
		'order_items',
		sa.Column('id', sa.String(length=36), nullable=False),
		sa.Column('order_id', sa.String(length=40), nullable=False),
		sa.Column('product_id', sa.String(length=100), nullable=True),
		sa.Column('product_sku', sa.String(length=100), nullable=False),
		sa.Column('product_title', sa.String(length=255), nullable=False),
		sa.Column('quantity', sa.Integer(), nullable=False),
		sa.Column('unit_price', sa.Numeric(precision=12, scale=2), nullable=False),
		sa.Column('discount', sa.Numeric(precision=12, scale=2), nullable=False),
		sa.Column('line_total', sa.Numeric(precision=12, scale=2), nullable=False),
		sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
		sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ondelete='CASCADE'),
		sa.ForeignKeyConstraint(['product_id'], ['products.id']),
		sa.PrimaryKeyConstraint('id'),
	)
	op.create_table(
		'payments',
		sa.Column('id', sa.String(length=36), nullable=False),
		sa.Column('order_id', sa.String(length=40), nullable=False),
		sa.Column('provider', sa.String(length=40), nullable=False),
		sa.Column('provider_order_id', sa.String(length=120), nullable=True),
		sa.Column('provider_payment_id', sa.String(length=120), nullable=True),
		sa.Column('method', sa.String(length=30), nullable=False),
		sa.Column('status', sa.String(length=30), nullable=False),
		sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=False),
		sa.Column('currency', sa.String(length=3), nullable=False),
		sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
		sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
		sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ondelete='CASCADE'),
		sa.PrimaryKeyConstraint('id'),
	)
	op.create_table(
		'shipments',
		sa.Column('id', sa.String(length=36), nullable=False),
		sa.Column('order_id', sa.String(length=40), nullable=False),
		sa.Column('carrier', sa.String(length=100), nullable=True),
		sa.Column('tracking_number', sa.String(length=120), nullable=True),
		sa.Column('status', sa.String(length=30), nullable=False),
		sa.Column('shipped_at', sa.DateTime(timezone=True), nullable=True),
		sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True),
		sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
		sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
		sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ondelete='CASCADE'),
		sa.PrimaryKeyConstraint('id'),
	)
	op.create_table(
		'expenses',
		sa.Column('id', sa.String(length=36), nullable=False),
		sa.Column('user_id', sa.String(length=36), nullable=True),
		sa.Column('category', sa.String(length=80), nullable=False),
		sa.Column('description', sa.Text(), nullable=True),
		sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=False),
		sa.Column('currency', sa.String(length=3), nullable=False),
		sa.Column('expense_date', sa.Date(), nullable=False),
		sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
		sa.ForeignKeyConstraint(['user_id'], ['users.id']),
		sa.PrimaryKeyConstraint('id'),
	)
	op.create_table(
		'profit_loss',
		sa.Column('id', sa.String(length=36), nullable=False),
		sa.Column('period_start', sa.Date(), nullable=False),
		sa.Column('period_end', sa.Date(), nullable=False),
		sa.Column('revenue', sa.Numeric(precision=12, scale=2), nullable=False),
		sa.Column('cost_of_goods', sa.Numeric(precision=12, scale=2), nullable=False),
		sa.Column('expenses', sa.Numeric(precision=12, scale=2), nullable=False),
		sa.Column('net_profit', sa.Numeric(precision=12, scale=2), nullable=False),
		sa.Column('currency', sa.String(length=3), nullable=False),
		sa.Column('generated_at', sa.DateTime(timezone=True), nullable=False),
		sa.PrimaryKeyConstraint('id'),
	)
	op.create_table(
		'notifications',
		sa.Column('id', sa.String(length=36), nullable=False),
		sa.Column('order_id', sa.String(length=40), nullable=True),
		sa.Column('customer_id', sa.String(length=36), nullable=True),
		sa.Column('channel', sa.String(length=30), nullable=False),
		sa.Column('recipient', sa.String(length=255), nullable=False),
		sa.Column('subject', sa.String(length=255), nullable=True),
		sa.Column('status', sa.String(length=30), nullable=False),
		sa.Column('provider_message_id', sa.String(length=255), nullable=True),
		sa.Column('error', sa.Text(), nullable=True),
		sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
		sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
		sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ondelete='SET NULL'),
		sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ondelete='SET NULL'),
		sa.PrimaryKeyConstraint('id'),
	)


def downgrade() -> None:
	op.drop_table('notifications')
	op.drop_table('profit_loss')
	op.drop_table('expenses')
	op.drop_table('shipments')
	op.drop_table('payments')
	op.drop_table('order_items')
	op.drop_constraint('fk_orders_customer_id_customers', 'orders', type_='foreignkey')
	op.drop_constraint('fk_orders_user_id_users', 'orders', type_='foreignkey')
	op.drop_column('orders', 'customer_id')
	op.drop_column('orders', 'user_id')
	op.rename_table('orders', 'customer_orders')
	op.execute('ALTER TABLE customer_orders RENAME CONSTRAINT uq_orders_idempotency_key TO uq_customer_orders_idempotency_key')
	op.drop_table('customers')
	op.drop_table('products')
	op.drop_table('users')