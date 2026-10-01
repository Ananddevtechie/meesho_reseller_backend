"""Ensure checkout retries update an existing customer.

Revision ID: 0003_unique_customer_mobile
Revises: 0002_reseller_tables
"""
from typing import Sequence, Union

from alembic import op


revision: str = '0003_unique_customer_mobile'
down_revision: Union[str, None] = '0002_reseller_tables'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
	op.create_unique_constraint('uq_customers_mobile', 'customers', ['mobile'])


def downgrade() -> None:
	op.drop_constraint('uq_customers_mobile', 'customers', type_='unique')