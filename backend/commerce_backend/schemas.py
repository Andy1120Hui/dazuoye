from __future__ import annotations

import math
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


CATEGORIES = {"home_storage", "pet_supplies", "kitchen", "outdoor"}
MARKETS = {"US", "GB", "DE"}


class ProductData(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    source: str
    title: str
    price: Decimal
    currency: str
    image_url: str
    product_url: str
    rating: float | None = None
    review_count: int | None = None
    sales_count: int | None = None
    category: str
    specification: str | None = None
    market: str = "US"
    data_mode: Literal["demo", "live", "imported"] = "demo"
    source_label: str
    collected_at: datetime

    @field_validator("price")
    @classmethod
    def valid_price(cls, value: Decimal) -> Decimal:
        if not value.is_finite() or value <= 0:
            raise ValueError("price must be a finite positive number")
        return value

    @field_validator("currency")
    @classmethod
    def valid_currency(cls, value: str) -> str:
        value = value.upper()
        if len(value) != 3 or not value.isalpha():
            raise ValueError("currency must be a 3-letter code")
        return value

    @field_validator("collected_at")
    @classmethod
    def valid_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("collected_at must include a timezone")
        return value


class SupplierData(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    product_id: str | None = None
    source: str
    title: str
    purchase_price: Decimal
    currency: str
    image_url: str
    product_url: str
    minimum_order_quantity: int | None = Field(default=None, ge=1)
    specification: str | None = None
    match_score: float | None = Field(default=None, ge=0, le=1)
    match_reason: str | None = None
    category: str
    data_mode: Literal["demo", "live", "imported"] = "demo"
    source_label: str
    price_basis: str = "零售采购参考价"
    collected_at: datetime

    @field_validator("purchase_price")
    @classmethod
    def valid_price(cls, value: Decimal) -> Decimal:
        if not value.is_finite() or value <= 0:
            raise ValueError("purchase_price must be a finite positive number")
        return value

    @field_validator("currency")
    @classmethod
    def valid_currency(cls, value: str) -> str:
        value = value.upper()
        if len(value) != 3 or not value.isalpha():
            raise ValueError("currency must be a 3-letter code")
        return value

    @field_validator("collected_at")
    @classmethod
    def valid_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("collected_at must include a timezone")
        return value


class CostAssumptions(BaseModel):
    exchange_rates_to_cny: dict[str, Decimal] = {"USD": Decimal("7.2"), "CNY": Decimal("1")}
    shipping_cny: Decimal = Field(default=Decimal("25"), ge=0)
    platform_fee_rate: Decimal = Field(default=Decimal("0.15"), ge=0, le=1)
    other_cost_cny: Decimal = Field(default=Decimal("0"), ge=0)

    @field_validator("exchange_rates_to_cny")
    @classmethod
    def valid_rates(cls, value: dict[str, Decimal]) -> dict[str, Decimal]:
        normalized = {key.upper(): rate for key, rate in value.items()}
        if any((not rate.is_finite()) or rate <= 0 for rate in normalized.values()):
            raise ValueError("exchange rates must be finite positive numbers")
        normalized.setdefault("CNY", Decimal("1"))
        return normalized


class RecommendationRequest(BaseModel):
    product_ids: list[str] = Field(min_length=1, max_length=50)
    cost_assumptions: CostAssumptions = Field(default_factory=CostAssumptions)


class CopyRequest(BaseModel):
    product_id: str
    target_language: Literal["zh", "en", "de", "es"] = "en"
    style: Literal["concise", "professional", "lively"] = "professional"


class Envelope(BaseModel):
    data: Any
    meta: dict[str, Any] = Field(default_factory=dict)
