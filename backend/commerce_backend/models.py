from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator

from .database import Base


class TZDateTime(TypeDecorator):
    """Store timezone-aware datetimes as ISO text so SQLite preserves the offset."""

    impl = String(40)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timezone-aware datetime required")
        return value.isoformat()

    def process_result_value(self, value, dialect):
        return datetime.fromisoformat(value) if value else None


class Product(Base):
    __tablename__ = "products"

    id: Mapped[str] = mapped_column(String(160), primary_key=True)
    source: Mapped[str] = mapped_column(String(32), index=True)
    title: Mapped[str] = mapped_column(String(500))
    price: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(3))
    image_url: Mapped[str] = mapped_column(Text)
    product_url: Mapped[str] = mapped_column(Text)
    rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    review_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sales_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    category: Mapped[str] = mapped_column(String(64), index=True)
    specification: Mapped[str | None] = mapped_column(Text, nullable=True)
    market: Mapped[str] = mapped_column(String(8), index=True, default="US")
    data_mode: Mapped[str] = mapped_column(String(16), default="demo")
    source_label: Mapped[str] = mapped_column(String(200))
    collected_at: Mapped[datetime] = mapped_column(TZDateTime())


class Supplier(Base):
    __tablename__ = "suppliers"

    id: Mapped[str] = mapped_column(String(160), primary_key=True)
    source: Mapped[str] = mapped_column(String(32), index=True)
    title: Mapped[str] = mapped_column(String(500))
    purchase_price: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(3))
    image_url: Mapped[str] = mapped_column(Text)
    product_url: Mapped[str] = mapped_column(Text)
    minimum_order_quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    specification: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(64), index=True)
    data_mode: Mapped[str] = mapped_column(String(16), default="demo")
    source_label: Mapped[str] = mapped_column(String(200))
    price_basis: Mapped[str] = mapped_column(String(120), default="课堂模拟采购成本，非真实批发报价")
    collected_at: Mapped[datetime] = mapped_column(TZDateTime())


class SupplierMatch(Base):
    __tablename__ = "supplier_matches"
    __table_args__ = (UniqueConstraint("product_id", "supplier_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    supplier_id: Mapped[str] = mapped_column(ForeignKey("suppliers.id", ondelete="CASCADE"), index=True)
    match_score: Mapped[float] = mapped_column(Float)
    match_reason: Mapped[str] = mapped_column(Text)
    product: Mapped[Product] = relationship()
    supplier: Mapped[Supplier] = relationship()
