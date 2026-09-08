from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .config import REPO_ROOT
from .matching import match_product_supplier
from .models import Product, Supplier, SupplierMatch
from .schemas import ProductData, SupplierData


def _read_json(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig") as handle:
        value = json.load(handle)
    if not isinstance(value, list):
        raise ValueError(f"{path} must contain a JSON array")
    return value


def upsert_product(session: Session, item: ProductData) -> Product:
    values = item.model_dump(exclude_none=False)
    obj = session.get(Product, item.id)
    if obj is None:
        obj = Product(**values)
        session.add(obj)
    else:
        for key, value in values.items():
            setattr(obj, key, value)
    return obj


def upsert_supplier(session: Session, item: SupplierData) -> Supplier:
    values = item.model_dump(exclude={"product_id", "match_score", "match_reason"}, exclude_none=False)
    obj = session.get(Supplier, item.id)
    if obj is None:
        obj = Supplier(**values)
        session.add(obj)
    else:
        for key, value in values.items():
            setattr(obj, key, value)
    return obj


def rebuild_matches(session: Session) -> None:
    session.execute(delete(SupplierMatch))
    products = session.scalars(select(Product)).all()
    suppliers = session.scalars(select(Supplier)).all()
    for product in products:
        for supplier in suppliers:
            if product.category != supplier.category:
                continue
            result = match_product_supplier(product, supplier)
            session.add(SupplierMatch(
                product_id=product.id,
                supplier_id=supplier.id,
                match_score=result.score,
                match_reason=result.reason,
            ))


def seed_demo_data(session: Session) -> None:
    product_path = REPO_ROOT / "data" / "demo_foreign_products.json"
    supplier_path = REPO_ROOT / "data" / "demo_suppliers.json"
    for raw in _read_json(product_path):
        upsert_product(session, ProductData.model_validate(raw))
    for raw in _read_json(supplier_path):
        upsert_supplier(session, SupplierData.model_validate(raw))
    session.flush()
    rebuild_matches(session)
    session.commit()
