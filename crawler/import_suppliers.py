from __future__ import annotations

import argparse
import json
from pathlib import Path

from commerce_backend.database import Base, SessionLocal, engine
from commerce_backend.importer import ImportValidationError, import_suppliers


def main() -> int:
    parser = argparse.ArgumentParser(description="Import candidate suppliers from UTF-8 CSV/JSON")
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    Base.metadata.create_all(engine)
    try:
        with SessionLocal() as session:
            count = import_suppliers(session, args.path)
        print(json.dumps({"status": "ok", "imported": count}, ensure_ascii=False))
        return 0
    except ImportValidationError as exc:
        print(json.dumps({"status": "error", "errors": exc.errors}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
