"""SQLAlchemy ORM models (Postgres + pgvector)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    ARRAY,
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from ..config import get_settings


class Base(DeclarativeBase):
    pass


class Product(Base):
    __tablename__ = "products"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    sku: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    name_vi: Mapped[str] = mapped_column(Text, nullable=False)
    active_ingredient: Mapped[str] = mapped_column(Text, nullable=False)
    strength: Mapped[str] = mapped_column(Text, nullable=False)
    dosage_form: Mapped[str] = mapped_column(Text, nullable=False)
    pack_size: Mapped[str | None] = mapped_column(Text)
    rx_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    manufacturer: Mapped[str | None] = mapped_column(Text)
    price_vnd: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    inventory: Mapped["Inventory"] = relationship(
        "Inventory", back_populates="product", uselist=False, cascade="all, delete-orphan"
    )


class Inventory(Base):
    __tablename__ = "inventory"

    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        primary_key=True,
    )
    qty_on_hand: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reorder_point: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    product: Mapped[Product] = relationship("Product", back_populates="inventory")


class OtcFormula(Base):
    __tablename__ = "otc_formulas"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    code: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    name_vi: Mapped[str] = mapped_column(Text, nullable=False)
    symptom_tags: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    symptom_text_vi: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(get_settings().embedding_dim)
    )
    min_age_years: Mapped[float] = mapped_column(Numeric, nullable=False, default=0)
    max_age_years: Mapped[float | None] = mapped_column(Numeric)
    pregnancy_safe: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notes_vi: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    items: Mapped[list["FormulaItem"]] = relationship(
        "FormulaItem", back_populates="formula", cascade="all, delete-orphan"
    )


class FormulaItem(Base):
    __tablename__ = "formula_items"
    __table_args__ = (
        CheckConstraint("role IN ('primary','adjuvant')", name="ck_formula_items_role"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    formula_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("otc_formulas.id", ondelete="CASCADE"),
        nullable=False,
    )
    active_ingredient: Mapped[str] = mapped_column(Text, nullable=False)
    strength_hint: Mapped[str | None] = mapped_column(Text)
    dose_per_take_vi: Mapped[str] = mapped_column(Text, nullable=False)
    frequency_per_day: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    duration_days: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    age_rule_vi: Mapped[str | None] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(16), nullable=False)

    formula: Mapped[OtcFormula] = relationship("OtcFormula", back_populates="items")


class AgentAuditLog(Base):
    __tablename__ = "agent_audit_log"
    __table_args__ = (
        CheckConstraint("flow IN ('prescription','symptom')", name="ck_audit_flow"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    flow: Mapped[str] = mapped_column(String(16), nullable=False)
    patient_hash: Mapped[str | None] = mapped_column(Text)
    request_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    response_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    llm_model: Mapped[str | None] = mapped_column(Text)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    red_flags: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
