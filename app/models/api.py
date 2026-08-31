import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, Enum as SQLEnum, ForeignKey, String, Text, func, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class APIVisibility(str, Enum):
    PUBLIC = "public"
    PRIVATE = "private"


class APIStatus(str, Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    DISABLED = "disabled"


class API(Base):
    __tablename__ = "apis"

    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "slug",
            name="uq_api_organization_slug"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)

    slug: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
        index=True,
    )

    version: Mapped[str] = mapped_column(
        String(50),
        default="v1",
        nullable=False,
    )

    description: Mapped[str | None] = mapped_column(Text)

    documentation: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    visibility: Mapped[APIVisibility] = mapped_column(
        SQLEnum(APIVisibility),
        default=APIVisibility.PRIVATE,
        nullable=False,
    )

    status: Mapped[APIStatus] = mapped_column(
        SQLEnum(APIStatus),
        default=APIStatus.DRAFT,
        nullable=False,
    )

    base_path: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    organization = relationship(
        "Organization",
        back_populates="apis",
    )

    routes = relationship(
        "APIRoute",
        back_populates="api",
        cascade="all, delete-orphan",
    )

    plans = relationship(
        "APIPlan",
        back_populates="api",
        cascade="all, delete-orphan",
    )

    usage_records = relationship(
        "UsageRecord",
        back_populates="api",
    )

    health_checks = relationship(
        "HealthCheck",
        back_populates="api",
    )
