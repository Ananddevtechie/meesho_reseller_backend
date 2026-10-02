"""Replace the sample backup table with admin credentials.

Revision ID: 0007_admins_table
Revises: 0006_backup_table
"""
from typing import Sequence, Union
from uuid import uuid4

from alembic import op
import sqlalchemy as sa

from app.config import settings
from app.services.admin_auth import hash_password


revision: str = '0007_admins_table'
down_revision: Union[str, None] = '0006_backup_table'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
	op.rename_table('backup', 'admins')
	op.drop_column('admins', 'payload')
	op.add_column('admins', sa.Column('username', sa.String(length=120), nullable=True))
	op.add_column('admins', sa.Column('password_hash', sa.String(length=255), nullable=True))
	if settings.admin_username and settings.admin_password:
		op.get_bind().execute(
			sa.text(
				'INSERT INTO admins (id, username, password_hash, created_at) '
				'VALUES (:id, :username, :password_hash, CURRENT_TIMESTAMP)'
			),
			{
				'id': str(uuid4()),
				'username': settings.admin_username,
				'password_hash': hash_password(settings.admin_password),
			},
		)
	op.alter_column('admins', 'username', existing_type=sa.String(length=120), nullable=False)
	op.alter_column('admins', 'password_hash', existing_type=sa.String(length=255), nullable=False)
	op.create_unique_constraint('uq_admins_username', 'admins', ['username'])


def downgrade() -> None:
	op.drop_constraint('uq_admins_username', 'admins', type_='unique')
	op.add_column('admins', sa.Column('payload', sa.JSON(), nullable=True))
	op.execute("UPDATE admins SET payload = json_build_object('username', username, 'password_hash', password_hash)")
	op.alter_column('admins', 'payload', existing_type=sa.JSON(), nullable=False)
	op.drop_column('admins', 'password_hash')
	op.drop_column('admins', 'username')
	op.rename_table('admins', 'backup')