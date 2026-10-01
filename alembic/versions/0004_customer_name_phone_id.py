"""Use the customer name and phone as the customer identity.

Revision ID: 0004_customer_name_phone_id
Revises: 0003_unique_customer_mobile
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0004_customer_name_phone_id'
down_revision: Union[str, None] = '0003_unique_customer_mobile'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
	op.drop_constraint('fk_orders_customer_id_customers', 'orders', type_='foreignkey')
	op.drop_constraint('uq_customers_mobile', 'customers', type_='unique')
	op.alter_column('customers', 'id', existing_type=sa.String(length=36), type_=sa.String(length=141))
	op.alter_column('orders', 'customer_id', existing_type=sa.String(length=36), type_=sa.String(length=141))
	op.execute(
		"""
		WITH customer_ids AS (
			SELECT id AS old_id, full_name || ':' || mobile AS new_id
			FROM customers
		)
		UPDATE orders
		SET customer_id = customer_ids.new_id
		FROM customer_ids
		WHERE orders.customer_id = customer_ids.old_id
		"""
	)
	op.execute("UPDATE customers SET id = full_name || ':' || mobile")
	op.create_foreign_key('fk_orders_customer_id_customers', 'orders', 'customers', ['customer_id'], ['id'])
	op.create_unique_constraint('uq_customers_name_mobile', 'customers', ['full_name', 'mobile'])


def downgrade() -> None:
	raise RuntimeError('Customer IDs now contain personal data and cannot be safely converted back to UUIDs.')