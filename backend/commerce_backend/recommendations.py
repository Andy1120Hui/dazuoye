from __future__ import annotations

import math
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import Product, SupplierMatch
from .schemas import CostAssumptions


def _clamp(value: float) -> float:
    return round(max(0.0, min(100.0, value)), 2)


def score_product(session: Session, product: Product, assumptions: CostAssumptions) -> dict:
    missing: list[str] = []
    rating_score = (product.rating / 5 * 100) if product.rating is not None else 50
    if product.rating is None:
        missing.append("rating")
    review_score = min(100, math.log10(product.review_count + 1) / 4 * 100) if product.review_count is not None else 50
    if product.review_count is None:
        missing.append("review_count")
    demand = _clamp((rating_score + review_score) / 2)

    category_count = session.scalar(select(func.count()).select_from(Product).where(Product.category == product.category)) or 0
    competition = _clamp(min(100, category_count / 20 * 100))
    match = session.scalar(select(SupplierMatch).where(SupplierMatch.product_id == product.id).order_by(SupplierMatch.match_score.desc()))
    profit_score = None
    profit = None
    supplier_id = None
    if match:
        supplier = match.supplier
        sale_rate = assumptions.exchange_rates_to_cny.get(product.currency)
        purchase_rate = assumptions.exchange_rates_to_cny.get(supplier.currency)
        if sale_rate and purchase_rate:
            revenue = Decimal(product.price) * sale_rate
            purchase = Decimal(supplier.purchase_price) * purchase_rate
            fee = revenue * assumptions.platform_fee_rate
            net_profit = revenue - purchase - assumptions.shipping_cny - assumptions.other_cost_cny - fee
            margin = net_profit / revenue if revenue else Decimal("0")
            profit_score = _clamp(float(margin) / 0.5 * 100)
            profit = {
                "revenue_cny": round(revenue, 2), "purchase_cny": round(purchase, 2),
                "platform_fee_cny": round(fee, 2), "net_profit_cny": round(net_profit, 2),
                "net_margin": round(margin, 4),
            }
            supplier_id = supplier.id
        else:
            missing.append("exchange_rate")
    else:
        missing.append("candidate_supplier")

    risk = {"home_storage": 35, "pet_supplies": 30, "kitchen": 45, "outdoor": 55}.get(product.category, 50)
    triggers = ["类别基础运输系数"]
    text = f"{product.title} {product.specification or ''}".lower()
    for term, points, label in [("glass", 20, "易碎"), ("玻璃", 20, "易碎"), ("battery", 20, "含电池"), ("large", 15, "大件")]:
        if term in text:
            risk += points
            triggers.append(label)
    transport = _clamp(risk)
    components = [(demand, 0.25), (100 - competition, 0.20), (100 - transport, 0.15)]
    if profit_score is not None:
        components.append((profit_score, 0.40))
    weight = sum(item[1] for item in components)
    overall = _clamp(sum(score * part for score, part in components) / weight)
    return {
        "product_id": product.id, "demand_potential": demand, "competition_level": competition,
        "profit_potential": profit_score, "transport_difficulty": transport, "overall_score": overall,
        "candidate_supplier_id": supplier_id, "profit_estimate": profit,
        "sample_size": category_count, "transport_factors": triggers, "missing_data": missing,
        "recommendation_reason": f"综合评分 {overall:.2f}；基于评价、同类样本、候选货源成本和运输关键词计算。",
    }
