from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .adapters.ebay import EbayAdapter, EbayUnavailable
from .config import REPO_ROOT, Settings, get_settings
from .copywriter import generate_copy
from .database import Base, engine, get_db
from .models import Product, Supplier, SupplierMatch
from .recommendations import score_product
from .repository import rebuild_matches, seed_demo_data, upsert_product
from .schemas import CATEGORIES, MARKETS, CopyRequest, Envelope, ProductData, RecommendationRequest, SupplierData


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("commerce_backend")


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    with Session(bind=engine) as session:
        seed_demo_data(session)
    app.state.ebay_adapter = (
        EbayAdapter(settings.ebay_client_id, settings.ebay_client_secret, settings.ebay_category_ids)
        if settings.ebay_client_id and settings.ebay_client_secret else None
    )
    yield


app = FastAPI(title="AI 跨境电商选品与经营模拟 API", version="0.1.0", lifespan=lifespan)
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/demo-assets", StaticFiles(directory=REPO_ROOT / "data" / "images"), name="demo-assets")


@app.middleware("http")
async def request_logging(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.request_id = request_id
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("request_id=%s path=%s error=unhandled_exception", request_id, request.url.path)
        raise
    response.headers["X-Request-ID"] = request_id
    logger.info("request_id=%s method=%s path=%s status=%s duration_ms=%.2f", request_id, request.method,
                request.url.path, response.status_code, (time.perf_counter() - started) * 1000)
    return response


def error_response(request: Request, status: int, code: str, message: str, details=None) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message,
        "details": details, "request_id": getattr(request.state, "request_id", None)}})


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    details = [{key: value for key, value in item.items() if key not in {"input", "ctx"}} for item in exc.errors()]
    return error_response(request, 422, "validation_error", "请求参数校验失败", details)


@app.exception_handler(Exception)
async def unhandled_handler(request: Request, exc: Exception):
    return error_response(request, 500, "internal_error", "服务器内部错误")


def not_found(request: Request, resource: str, identifier: str):
    return error_response(request, 404, "not_found", f"{resource} 不存在", {"id": identifier})


DbSession = Annotated[Session, Depends(get_db)]


@app.get("/api/health", response_model=Envelope)
def health(db: DbSession):
    product_count = db.scalar(select(func.count()).select_from(Product)) or 0
    supplier_count = db.scalar(select(func.count()).select_from(Supplier)) or 0
    return Envelope(data={"status": "ok", "database": "ok", "products": product_count, "suppliers": supplier_count},
                    meta={"data_mode": "demo_available", "external_requests": False})


@app.get("/api/products", response_model=Envelope)
async def list_products(
    request: Request,
    db: DbSession,
    market: str = Query("US"),
    category: str | None = Query(None),
    keyword: str | None = Query(None, min_length=1, max_length=120),
    limit: int = Query(5, ge=1, le=50),
):
    market = market.upper()
    if market not in MARKETS:
        return error_response(request, 422, "unsupported_market", "market 仅支持 US、GB、DE")
    if category and category not in CATEGORIES:
        return error_response(request, 422, "unsupported_category", "不支持的商品类别", sorted(CATEGORIES))

    meta = {"data_mode": "demo", "source_notice": "人工编制课堂演示数据；不是实时采集结果", "cache_hit": False,
            "fallback_reason": "ebay_credentials_not_configured", "category_filtering": "local_exact_category"}
    adapter = request.app.state.ebay_adapter
    if adapter:
        try:
            products, cache_hit, filtering = await adapter.search(market, category, keyword, limit)
            for product in products:
                upsert_product(db, product)
            if products:
                db.flush()
                rebuild_matches(db)
            db.commit()
            return Envelope(data=products, meta={"data_mode": "live", "source_notice": "eBay Browse API 实时结果",
                "cache_hit": cache_hit, "fallback_reason": None, "category_filtering": filtering})
        except EbayUnavailable as exc:
            meta["fallback_reason"] = exc.reason

    query = select(Product).where(Product.data_mode == "demo", Product.market == market)
    if category:
        query = query.where(Product.category == category)
    if keyword:
        query = query.where(func.lower(Product.title).contains(keyword.lower()))
    products = db.scalars(query.order_by(Product.id).limit(limit)).all()
    if market != "US":
        meta["source_notice"] = "该市场没有演示记录；未用其他市场数据替代"
    return Envelope(data=[ProductData.model_validate(item) for item in products], meta=meta)


@app.get("/api/products/{product_id}", response_model=Envelope)
def get_product(product_id: str, request: Request, db: DbSession):
    product = db.get(Product, product_id)
    if not product:
        return not_found(request, "商品", product_id)
    return Envelope(data=ProductData.model_validate(product), meta={"data_mode": product.data_mode, "source_notice": product.source_label})


@app.get("/api/products/{product_id}/suppliers", response_model=Envelope)
def get_suppliers(product_id: str, request: Request, db: DbSession):
    product = db.get(Product, product_id)
    if not product:
        return not_found(request, "商品", product_id)
    matches = db.scalars(select(SupplierMatch).where(SupplierMatch.product_id == product_id).order_by(SupplierMatch.match_score.desc())).all()
    data = []
    for match in matches:
        supplier = match.supplier
        payload = SupplierData.model_validate(supplier).model_copy(update={"product_id": product_id,
            "match_score": match.match_score, "match_reason": match.match_reason})
        data.append(payload)
    modes = sorted({item.data_mode for item in data})
    return Envelope(data=data, meta={"label": "候选货源", "data_mode": modes or ["none"],
        "source_notice": "匹配分表示文本与规格相似程度，不代表同款概率；价格需自行核实"})


@app.post("/api/recommendations", response_model=Envelope)
def recommendations(payload: RecommendationRequest, request: Request, db: DbSession):
    products = {item.id: item for item in db.scalars(select(Product).where(Product.id.in_(payload.product_ids))).all()}
    missing_ids = [identifier for identifier in payload.product_ids if identifier not in products]
    if missing_ids:
        return error_response(request, 404, "products_not_found", "部分商品不存在", {"ids": missing_ids})
    results = [score_product(db, products[identifier], payload.cost_assumptions) for identifier in payload.product_ids]
    return Envelope(data=results, meta={"notice": "启发式选品评分，不是真实销量预测", "formula_version": "heuristic-v1",
        "cost_assumptions": payload.cost_assumptions.model_dump(mode="json"),
        "assumptions_are_demo_defaults": "cost_assumptions" not in payload.model_fields_set,
        "data_modes": sorted({product.data_mode for product in products.values()})})


@app.post("/api/generate-copy", response_model=Envelope)
async def copy(payload: CopyRequest, request: Request, db: DbSession):
    product = db.get(Product, payload.product_id)
    if not product:
        return not_found(request, "商品", payload.product_id)
    result, mode, reason = await generate_copy(product, payload.target_language, payload.style, settings)
    return Envelope(data=result, meta={"generation_mode": mode, "fallback_reason": reason,
        "source_notice": "文案仅基于现有商品标题和规格生成，不包含未经证实的销量或认证"})
