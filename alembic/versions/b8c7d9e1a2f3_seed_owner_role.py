"""seed owner role required by registration

Revision ID: b8c7d9e1a2f3
Revises: f43b15060f4b
"""
from typing import Sequence, Union
from uuid import uuid4

from alembic import op
import sqlalchemy as sa


revision: str = "b8c7d9e1a2f3"
down_revision: Union[str, None] = "f43b15060f4b"
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
    owner_exists = connection.execute(
        sa.select(roles.c.name).where(roles.c.name == "owner")
    ).first()
    if owner_exists is None:
        op.bulk_insert(
            roles,
            [
                {
                    "id": uuid4(),
                    "name": "owner",
                    "description": "Organization owner",
                }
            ],
        )


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM roles WHERE name = 'owner'"))
