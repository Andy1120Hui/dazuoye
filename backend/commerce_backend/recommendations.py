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
    purchase_override = assumptions.purchase_price_overrides_cny.get(
        product.id, assumptions.purchase_price_cny
    )
    sale_rate = assumptions.exchange_rates_to_cny.get(product.currency)
    purchase = purchase_override
    purchase_source = "request_override" if purchase_override is not None else None
    if match:
        supplier_id = match.supplier.id
        if purchase is None:
            purchase_rate = assumptions.exchange_rates_to_cny.get(match.supplier.currency)
            if purchase_rate:
                purchase = Decimal(match.supplier.purchase_price) * purchase_rate
                purchase_source = "highest_scoring_simulated_candidate"
            else:
                missing.append("purchase_currency_exchange_rate")
    if purchase is not None and sale_rate:
        revenue = Decimal(product.price) * sale_rate
        fee = revenue * assumptions.platform_fee_rate
        net_profit = revenue - purchase - assumptions.shipping_cny - assumptions.other_cost_cny - fee
        margin = net_profit / revenue if revenue else Decimal(0)
        target = assumptions.target_profit_rate
        profit_score = _clamp(50 + float(margin - target) * 200)
        profit = {
            "revenue_cny": round(revenue, 2), "purchase_cny": round(purchase, 2),
            "platform_fee_cny": round(fee, 2), "net_profit_cny": round(net_profit, 2),
            "net_margin": round(margin, 4), "target_profit_rate": target,
            "target_margin_gap": round(margin - target, 4),
            "purchase_price_source": purchase_source,
        }
    elif not sale_rate:
        missing.append("sale_currency_exchange_rate")
    if not match:
        missing.append("candidate_supplier")
    if purchase is None:
        missing.append("purchase_price")

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
    risks = []
    if missing:
        risks.append("部分真实字段缺失，相关维度使用中性值或标记为未知")
    if profit and profit["target_margin_gap"] < 0:
        risks.append("按当前模拟参数计算的净利率低于目标利润率")
    if transport >= 60:
        risks.append("运输难度较高，需进一步核实包装、尺寸和运输限制")
    if product.data_mode == "demo":
        risks.append("商品为人工演示数据，不能代替实时市场验证")
    return {
        "product_id": product.id, "demand_potential": demand, "competition_level": competition,
        "profit_potential": profit_score, "transport_difficulty": transport, "overall_score": overall,
        "candidate_supplier_id": supplier_id, "profit_estimate": profit,
        "sample_size": category_count, "transport_factors": triggers, "missing_data": missing,
        "recommendation_reason": f"综合评分 {overall:.2f}；基于评价、同类样本、候选货源成本和运输关键词计算。",
        "risks": risks,
    }
