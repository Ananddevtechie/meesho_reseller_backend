"""Rename email delivery fields for Telegram order notifications.

Revision ID: 0009_telegram_notifications
Revises: 0008_product_category
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0009_telegram_notifications'
down_revision: Union[str, None] = '0008_product_category'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
	op.alter_column('orders', 'email_status', new_column_name='notification_status', existing_type=sa.String(length=20), existing_nullable=False)
	op.alter_column('orders', 'email_attempts', new_column_name='notification_attempts', existing_type=sa.Integer(), existing_nullable=False)
	op.alter_column('orders', 'email_error', new_column_name='notification_error', existing_type=sa.Text(), existing_nullable=True)


def downgrade() -> None:
	op.alter_column('orders', 'notification_status', new_column_name='email_status', existing_type=sa.String(length=20), existing_nullable=False)
	op.alter_column('orders', 'notification_attempts', new_column_name='email_attempts', existing_type=sa.Integer(), existing_nullable=False)
	op.alter_column('orders', 'notification_error', new_column_name='email_error', existing_type=sa.Text(), existing_nullable=True)