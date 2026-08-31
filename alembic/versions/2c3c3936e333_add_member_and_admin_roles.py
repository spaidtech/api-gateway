"""add_member_and_admin_roles

Revision ID: 2c3c3936e333
Revises: b8c7d9e1a2f3
Create Date: 2026-08-28 14:37:54.657160

"""
from typing import Sequence, Union
from uuid import uuid4

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2c3c3936e333'
down_revision: Union[str, None] = 'b8c7d9e1a2f3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    roles = sa.table(
        "roles",
        sa.column("id", sa.UUID()),
        sa.column("name", sa.String()),
        sa.column("description", sa.String()),
    )
    connection = op.get_bind()
    
    # Add admin role if it doesn't exist
    admin_exists = connection.execute(
        sa.select(roles.c.name).where(roles.c.name == "admin")
    ).first()
    if admin_exists is None:
        op.bulk_insert(
            roles,
            [
                {
                    "id": uuid4(),
                    "name": "admin",
                    "description": "Organization admin",
                }
            ],
        )
    
    # Add member role if it doesn't exist
    member_exists = connection.execute(
        sa.select(roles.c.name).where(roles.c.name == "member")
    ).first()
    if member_exists is None:
        op.bulk_insert(
            roles,
            [
                {
                    "id": uuid4(),
                    "name": "member",
                    "description": "Organization member",
                }
            ],
        )


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM roles WHERE name IN ('admin', 'member')"))

