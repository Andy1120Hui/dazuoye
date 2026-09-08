from __future__ import annotations

import csv
import json
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy.orm import Session

from .repository import rebuild_matches, upsert_supplier
from .schemas import SupplierData


class ImportValidationError(ValueError):
    def __init__(self, errors: list[dict]):
        super().__init__("supplier import validation failed")
        self.errors = errors


def load_supplier_rows(path: Path) -> list[dict]:
    suffix = path.suffix.lower()
    if suffix == ".json":
        with path.open(encoding="utf-8-sig") as handle:
            value = json.load(handle)
        if not isinstance(value, list):
            raise ImportValidationError([{"row": 1, "message": "JSON root must be an array"}])
        return value
    if suffix == ".csv":
        with path.open(encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))
    raise ImportValidationError([{"row": 1, "message": "only .csv and .json are supported"}])


def import_suppliers(session: Session, path: Path) -> int:
    try:
        rows = load_supplier_rows(path)
    except (OSError, json.JSONDecodeError) as exc:
        raise ImportValidationError([{"row": 1, "message": str(exc)}]) from exc
    validated: list[SupplierData] = []
    errors: list[dict] = []
    for index, row in enumerate(rows, start=2 if path.suffix.lower() == ".csv" else 1):
        cleaned = dict(row)
        for key in ("minimum_order_quantity",):
            if cleaned.get(key) == "":
                cleaned[key] = None
        cleaned["data_mode"] = "imported"
        cleaned["source_label"] = "用户导入的课堂模拟候选货源"
        cleaned["price_basis"] = "用户导入的课堂模拟采购成本，非真实批发报价"
        try:
            validated.append(SupplierData.model_validate(cleaned))
        except ValidationError as exc:
            errors.append({"row": index, "message": exc.errors(include_url=False)})
    if errors:
        raise ImportValidationError(errors)
    try:
        for item in validated:
            upsert_supplier(session, item)
        session.flush()
        rebuild_matches(session)
        session.commit()
    except Exception:
        session.rollback()
        raise
    return len(validated)
