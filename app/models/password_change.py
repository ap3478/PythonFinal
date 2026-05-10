# app/models/password_change.py
"""
PasswordChange Audit Model

Records every successful password change so administrators can review the
audit trail. The previous and new password hashes are *not* stored here —
only metadata about when the change happened and who performed it.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship

from app.database import Base


def utcnow():
    """Helper: current UTC time as a timezone-aware datetime."""
    return datetime.now(timezone.utc)


class PasswordChange(Base):
    """
    Audit-log row created every time a user successfully changes their
    password via ``POST /users/me/change-password``.

    Notes:
        * Plain-text and hashed passwords are intentionally NOT recorded.
        * ``changed_by_user_id`` is the user who actually executed the change.
          For self-service changes this equals ``user_id``; for an admin
          performing a forced reset (future feature), the two would differ.
    """

    __tablename__ = "password_changes"

    id = Column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )

    user_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    changed_by_user_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    changed_at = Column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False,
        index=True,
    )

    ip_address = Column(String(45), nullable=True)  # IPv4/IPv6 max length
    user_agent = Column(String(255), nullable=True)

    user = relationship(
        "User",
        foreign_keys=[user_id],
        back_populates="password_changes",
    )

    changed_by = relationship(
        "User",
        foreign_keys=[changed_by_user_id],
    )

    def __repr__(self):
        return (
            f"<PasswordChange(user_id={self.user_id}, "
            f"changed_at={self.changed_at})>"
        )
