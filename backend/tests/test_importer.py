import json
from pathlib import Path

import pytest
from commerce_backend.database import Base, make_engine
from commerce_backend.importer import ImportValidationError, import_suppliers
from commerce_backend.models import Supplier
from sqlalchemy import func, select
from sqlalchemy.orm import Session


def valid_row(identifier="supplier_imported"):
    return {
        "id": identifier, "source": "manual", "title": "候选货源", "purchase_price": 12.5,
        "currency": "cny", "image_url": "https://example.com/a", "product_url": "https://example.com/b",
        "minimum_order_quantity": 1, "specification": "硅胶", "category": "kitchen",
        "collected_at": "2026-09-08T09:00:00+08:00",
    }


def test_json_import_is_idempotent(tmp_path: Path):
    path = tmp_path / "rows.json"
    path.write_text(json.dumps([valid_row()], ensure_ascii=False), encoding="utf-8")
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        assert import_suppliers(session, path) == 1
        assert import_suppliers(session, path) == 1
        assert session.scalar(select(func.count()).select_from(Supplier)) == 1
        supplier = session.get(Supplier, "supplier_imported")
        assert supplier.data_mode == "imported"
        assert "模拟" in supplier.source_label
        assert "非真实批发报价" in supplier.price_basis


def test_csv_bom_and_transactional_validation(tmp_path: Path):
    path = tmp_path / "rows.csv"
    fields = list(valid_row().keys())
    good = valid_row("good")
    bad = {**valid_row("bad"), "purchase_price": "NaN"}
    lines = [",".join(fields), ",".join(str(good[key]) for key in fields), ",".join(str(bad[key]) for key in fields)]
    path.write_text("\ufeff" + "\n".join(lines), encoding="utf-8")
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        with pytest.raises(ImportValidationError) as exc:
            import_suppliers(session, path)
        assert exc.value.errors[0]["row"] == 3
        assert session.scalar(select(func.count()).select_from(Supplier)) == 0
