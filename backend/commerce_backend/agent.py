from __future__ import annotations

import re
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .catalog import search_products
from .copywriter import generate_copy
from .models import Product
from .recommendations import score_product
from .schemas import AgentRecommendationRequest, CostAssumptions, ProductData

MARKET_TERMS = [
    ("GB", ("英国", "英國", "united kingdom", " uk ", " gb ")),
    ("DE", ("德国", "德國", "germany", "deutschland", " de ")),
    ("US", ("美国", "美國", "united states", "usa", " us ")),
]
CATEGORY_TERMS = [
    ("home_storage", ("家居收纳", "家居收納", "收纳", "收納", "home storage", "organizer")),
    ("pet_supplies", ("宠物", "寵物", "pet supplies", "pet")),
    ("kitchen", ("厨房", "廚房", "kitchen", "cooking")),
    ("outdoor", ("户外", "戶外", "露营", "露營", "outdoor", "camping")),
]


def _contains_term(query: str, term: str) -> bool:
    padded = f" {query.lower()} "
    return term in padded if term.startswith(" ") else term in query.lower()


def parse_intent(query: str) -> dict:
    market = "US"
    for value, terms in MARKET_TERMS:
        if any(_contains_term(query, term) for term in terms):
            market = value
            break
    category = None
    for value, terms in CATEGORY_TERMS:
        if any(_contains_term(query, term) for term in terms):
            category = value
            break
    quoted = re.search(r"[\"“‘']([^\"”’']{2,80})[\"”’']", query)
    keyword = quoted.group(1).strip() if quoted else None
    return {"market": market, "category": category, "keyword": keyword}


def _number(query: str, label: str) -> Decimal | None:
    match = re.search(label + r"\s*(?:为|是|=|:|：)?\s*(\d+(?:\.\d+)?)\s*(%)?", query, re.IGNORECASE)
    if not match:
        return None
    value = Decimal(match.group(1))
    return value / 100 if match.group(2) else value


def assumptions_from_query(payload: AgentRecommendationRequest) -> tuple[CostAssumptions, list[str]]:
    current = payload.cost_assumptions
    explicit = current.model_fields_set
    updates = {}
    parsed_fields: list[str] = []
    patterns = {
        "purchase_price_cny": r"(?:采购价|采购成本|进货价|purchase price)",
        "shipping_cny": r"(?:物流费|运费|shipping)",
        "platform_fee_rate": r"(?:平台手续费率|平台费率|手续费率|platform fee)",
        "other_cost_cny": r"(?:其他费用|其它费用|other cost)",
        "target_profit_rate": r"(?:目标利润率|目标净利率|target (?:profit|margin))",
    }
    for field, pattern in patterns.items():
        if field in explicit:
            continue
        value = _number(payload.query, pattern)
        if value is not None:
            updates[field] = value
            parsed_fields.append(field)
    if "exchange_rates_to_cny" not in explicit:
        rate = _number(payload.query, r"(?:美元兑人民币汇率|USD兑CNY汇率|汇率)")
        if rate is not None:
            updates["exchange_rates_to_cny"] = {**current.exchange_rates_to_cny, "USD": rate}
            parsed_fields.append("exchange_rates_to_cny")
    return current.model_copy(update=updates), parsed_fields


def _evidence(product: ProductData) -> dict:
    returned_fields = [
        "title", "price", "currency", "image_url", "product_url", "category", "specification",
        "rating", "review_count", "sales_count", "collected_at",
    ]
    missing = [field for field in returned_fields if getattr(product, field) is None]
    factual = [field for field in returned_fields if field not in missing]
    origin_fields = {
        "platform_fields": factual if product.data_mode == "live" else [],
        "demo_fields": factual if product.data_mode == "demo" else [],
        "imported_fields": factual if product.data_mode == "imported" else [],
    }
    return {
        "source": product.source_label,
        "data_mode": product.data_mode,
        "collected_at": product.collected_at,
        "returned_fields": factual,
        **origin_fields,
        "missing_fields": missing,
        "simulated_fields": [
            "candidate_supplier.purchase_price", "purchase_price_cny", "purchase_price_overrides_cny",
            "exchange_rates_to_cny", "shipping_cny",
            "platform_fee_rate", "other_cost_cny", "target_profit_rate",
        ],
        "inferred_fields": [
            "demand_potential", "competition_level", "profit_potential", "transport_difficulty", "overall_score",
        ],
        "historical_sales_available": product.sales_count is not None,
        "scoring_label": "启发式选品评分，不是真实销量预测",
    }


async def run_recommendation_agent(
    payload: AgentRecommendationRequest,
    session: Session,
    ebay_adapter,
    settings,
) -> tuple[dict, dict]:
    intent = parse_intent(payload.query)
    assumptions, parsed_assumptions = assumptions_from_query(payload)
    products, search_meta = await search_products(
        session, ebay_adapter, intent["market"], intent["category"], intent["keyword"], payload.max_results
    )
    if not products:
        return {
            "query": payload.query, "interpreted_request": intent, "ranked_products": [],
            "recommendation": "当前查询没有返回商品，请调整市场、类别或关键词。",
        }, {
            **search_meta, "agent_prompt_version": "classroom-selection-v1", "orchestration_mode": "deterministic",
            "cost_assumptions": assumptions.model_dump(), "tool_trace": ["GET /api/products"],
        }

    ids = [product.id for product in products]
    stored = {item.id: item for item in session.scalars(select(Product).where(Product.id.in_(ids))).all()}
    ranked = []
    for product in products:
        analysis = score_product(session, stored[product.id], assumptions)
        ranked.append({"product": product.model_dump(), "analysis": analysis, "evidence": _evidence(product)})
    ranked.sort(key=lambda item: item["analysis"]["overall_score"], reverse=True)
    for index, item in enumerate(ranked, start=1):
        item["rank"] = index

    tool_trace = ["GET /api/products", "GET /api/products/{id}/suppliers", "POST /api/recommendations"]
    copy_result = None
    if payload.generate_copy_for_top:
        top = stored[ranked[0]["product"]["id"]]
        generated, mode, reason = await generate_copy(top, payload.target_language, payload.copy_style, settings)
        copy_result = {"content": generated, "generation_mode": mode, "fallback_reason": reason}
        tool_trace.append("POST /api/generate-copy")

    top = ranked[0]
    result = {
        "query": payload.query,
        "interpreted_request": intent,
        "recommendation": f"优先考虑第 1 名 {top['product']['title']}；综合评分 {top['analysis']['overall_score']:.2f}。",
        "ranked_products": ranked,
        "generated_copy_for_top": copy_result,
    }
    collected = [product.collected_at for product in products]
    meta = {
        **search_meta,
        "data_sources": sorted({product.source_label for product in products}),
        "collected_at_range": {"earliest": min(collected), "latest": max(collected)},
        "agent_prompt_version": "classroom-selection-v1",
        "orchestration_mode": "deterministic",
        "scoring_label": "启发式选品评分，不是真实销量预测",
        "cost_assumptions": assumptions.model_dump(),
        "assumptions_parsed_from_query": parsed_assumptions,
        "candidate_supplier_notice": "候选货源和采购价为人工编制或用户导入的模拟数据，不是真实批发报价或同款确认。",
        "tool_trace": tool_trace,
    }
    return result, meta
