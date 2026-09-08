from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .adapters.ebay import EbayUnavailable
from .models import Product
from .repository import rebuild_matches, upsert_product
from .schemas import ProductData


async def search_products(
    session: Session,
    ebay_adapter,
    market: str,
    category: str | None,
    keyword: str | None,
    limit: int,
) -> tuple[list[ProductData], dict]:
    meta = {
        "data_mode": "demo",
        "source_notice": "人工编制课堂演示数据；不是实时采集结果",
        "cache_hit": False,
        "fallback_reason": "ebay_credentials_not_configured",
        "category_filtering": "local_exact_category",
        "calculation_assumptions": None,
    }
    if ebay_adapter:
        try:
            products, cache_hit, filtering = await ebay_adapter.search(market, category, keyword, limit)
            for product in products:
                upsert_product(session, product)
            if products:
                session.flush()
                rebuild_matches(session)
            session.commit()
            return products, {
                "data_mode": "live",
                "source_notice": "eBay Browse API 实时结果",
                "cache_hit": cache_hit,
                "fallback_reason": None,
                "category_filtering": filtering,
                "calculation_assumptions": None,
            }
        except EbayUnavailable as exc:
            meta["fallback_reason"] = exc.reason

    query = select(Product).where(Product.data_mode == "demo", Product.market == market)
    if category:
        query = query.where(Product.category == category)
    if keyword:
        query = query.where(func.lower(Product.title).contains(keyword.lower()))
    products = session.scalars(query.order_by(Product.id).limit(limit)).all()
    if market != "US":
        meta["source_notice"] = "该市场没有演示记录；未用其他市场数据替代"
    return [ProductData.model_validate(item) for item in products], meta
