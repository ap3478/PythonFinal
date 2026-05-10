"""add is_admin to users; create password_changes audit table

Revision ID: 0002_admin_and_password_audit
Revises: 0001_baseline
Create Date: 2025-05-09 19:30:00.000000

Schema changes for the profile/password/admin/stats feature:

* ``users.is_admin`` boolean column (defaults to ``False``)
* new ``password_changes`` audit table with two FKs to ``users``
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0002_admin_and_password_audit"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # is_admin column. server_default=false so existing rows are non-admin.
    op.add_column(
        "users",
        sa.Column(
            "is_admin",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )

    op.create_table(
        "password_changes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "changed_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "changed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.String(length=255), nullable=True),
    )
    op.create_index(
        "ix_password_changes_user_id",
        "password_changes",
        ["user_id"],
    )
    op.create_index(
        "ix_password_changes_changed_at",
        "password_changes",
        ["changed_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_password_changes_changed_at", table_name="password_changes")
    op.drop_index("ix_password_changes_user_id", table_name="password_changes")
    op.drop_table("password_changes")
    op.drop_column("users", "is_admin")
