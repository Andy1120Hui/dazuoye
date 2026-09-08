from __future__ import annotations

import hashlib
import asyncio
import time
from collections import OrderedDict
from datetime import datetime
from decimal import Decimal
from typing import Any

import httpx

from ..schemas import SupplierData


class TaobaoUnavailable(RuntimeError):
    pass


def top_sign(params: dict[str, str], secret: str) -> str:
    body = "".join(f"{key}{params[key]}" for key in sorted(params) if key != "sign")
    return hashlib.md5(f"{secret}{body}{secret}".encode("utf-8")).hexdigest().upper()


class TaobaoAdapter:
    endpoint = "https://eco.taobao.com/router/rest"

    def __init__(self, app_key: str, app_secret: str, adzone_id: str, client: httpx.AsyncClient | None = None):
        self.app_key, self.app_secret, self.adzone_id, self.client = app_key, app_secret, adzone_id, client
        self._cache: OrderedDict[tuple[str, str, int], tuple[float, list[SupplierData]]] = OrderedDict()

    async def search(self, keyword: str, category: str, limit: int = 20) -> list[SupplierData]:
        cache_key = (keyword, category, limit)
        cached = self._cache.get(cache_key)
        if cached and cached[0] > time.monotonic():
            self._cache.move_to_end(cache_key)
            return cached[1]
        now = datetime.now().astimezone()
        params = {
            "method": "taobao.tbk.dg.material.optional.upgrade", "app_key": self.app_key,
            "format": "json", "v": "2.0", "sign_method": "md5", "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
            "adzone_id": self.adzone_id, "q": keyword, "page_size": str(min(limit, 100)),
        }
        params["sign"] = top_sign(params, self.app_secret)
        own_client = self.client is None
        client = self.client or httpx.AsyncClient(timeout=httpx.Timeout(10, connect=3))
        try:
            response = None
            for attempt in range(3):
                try:
                    response = await client.post(self.endpoint, data=params)
                    if response.status_code >= 500 and attempt < 2:
                        await asyncio.sleep(0.1 * (attempt + 1))
                        continue
                    break
                except (httpx.TimeoutException, httpx.NetworkError) as exc:
                    if attempt == 2:
                        raise TaobaoUnavailable("taobao_timeout_or_network_error") from exc
                    await asyncio.sleep(0.1 * (attempt + 1))
            assert response is not None
            content_type = response.headers.get("content-type", "")
            if response.status_code in {401, 403, 429} or "html" in content_type:
                raise TaobaoUnavailable(f"taobao_access_stopped_{response.status_code}")
            response.raise_for_status()
            payload = response.json()
            if "error_response" in payload:
                raise TaobaoUnavailable("taobao_api_permission_or_request_error")
            result = payload.get("tbk_dg_material_optional_upgrade_response", {}).get("result_list", {})
            rows = result.get("map_data", []) if isinstance(result, dict) else []
            items = [self._normalize(row, category, now) for row in rows if self._has_required(row)]
            self._cache[cache_key] = (time.monotonic() + 600, items)
            while len(self._cache) > 128:
                self._cache.popitem(last=False)
            return items
        except (httpx.HTTPError, ValueError) as exc:
            if isinstance(exc, TaobaoUnavailable):
                raise
            raise TaobaoUnavailable("taobao_connection_or_response_error") from exc
        finally:
            if own_client:
                await client.aclose()

    @staticmethod
    def _has_required(row: dict[str, Any]) -> bool:
        basic = row.get("item_basic_info") or {}
        publish = row.get("publish_info") or {}
        price = row.get("price_promotion_info") or {}
        return bool(basic.get("item_id") and basic.get("title") and publish.get("click_url") and price.get("zk_final_price"))

    @staticmethod
    def _normalize(row: dict[str, Any], category: str, now: datetime) -> SupplierData:
        basic, publish, price = row["item_basic_info"], row["publish_info"], row["price_promotion_info"]
        return SupplierData(
            id=f"taobao_{basic['item_id']}", source="taobao", title=basic["title"],
            purchase_price=Decimal(str(price["zk_final_price"])), currency="CNY",
            image_url=basic.get("pict_url", ""), product_url=publish["click_url"],
            minimum_order_quantity=None, specification=None, category=category, data_mode="live",
            source_label="淘宝联盟官方接口实时查询", price_basis="联盟零售采购参考价，非批发报价",
            collected_at=now,
        )
