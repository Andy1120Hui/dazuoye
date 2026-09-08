from __future__ import annotations

import argparse
import asyncio

from commerce_backend.adapters.ebay import EbayAdapter, EbayUnavailable
from commerce_backend.adapters.taobao import TaobaoAdapter, TaobaoUnavailable
from commerce_backend.config import get_settings
from commerce_backend.database import Base, SessionLocal, engine
from commerce_backend.repository import rebuild_matches, upsert_product, upsert_supplier
from commerce_backend.schemas import CATEGORIES, MARKETS


async def collect(args) -> int:
    settings = get_settings()
    Base.metadata.create_all(engine)
    if args.source == "ebay":
        if not (settings.ebay_client_id and settings.ebay_client_secret):
            print("未配置 eBay 应用凭据；没有发起外部请求，也没有写入数据。")
            return 2
        adapter = EbayAdapter(settings.ebay_client_id, settings.ebay_client_secret, settings.ebay_category_ids)
        try:
            items, _, filtering = await adapter.search(args.market, args.category, args.keyword, args.limit)
        except EbayUnavailable as exc:
            print(f"eBay 官方接口不可用：{exc.reason}；没有写入数据。")
            return 3
        with SessionLocal() as session:
            for item in items:
                upsert_product(session, item)
            session.flush()
            rebuild_matches(session)
            session.commit()
        print(f"已保存 {len(items)} 条 eBay 实时商品；过滤方式：{filtering}。")
        return 0

    if not (settings.taobao_app_key and settings.taobao_app_secret and settings.taobao_adzone_id):
        print("未配置淘宝联盟应用凭据和推广位；没有发起外部请求，也没有写入数据。")
        return 2
    adapter = TaobaoAdapter(settings.taobao_app_key, settings.taobao_app_secret, settings.taobao_adzone_id)
    try:
        items = await adapter.search(args.keyword, args.category, args.limit)
    except TaobaoUnavailable as exc:
        print(f"淘宝联盟官方接口不可用：{exc}；没有写入数据。")
        return 3
    with SessionLocal() as session:
        for item in items:
            upsert_supplier(session, item)
        session.flush()
        rebuild_matches(session)
        session.commit()
    print(f"已保存 {len(items)} 条淘宝联盟候选货源；价格仅为零售采购参考价。")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="通过官方 API 小规模采集商品或候选货源")
    parser.add_argument("source", choices=["ebay", "taobao"])
    parser.add_argument("--keyword", required=True)
    parser.add_argument("--category", required=True, choices=sorted(CATEGORIES))
    parser.add_argument("--market", default="US", choices=sorted(MARKETS))
    parser.add_argument("--limit", type=int, default=10, choices=range(1, 51), metavar="1-50")
    args = parser.parse_args()
    return asyncio.run(collect(args))


if __name__ == "__main__":
    raise SystemExit(main())
