from __future__ import annotations

import asyncio
import base64
import time
from collections import OrderedDict
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import httpx

from ..schemas import ProductData

MARKET_IDS = {"US": "EBAY_US", "GB": "EBAY_GB", "DE": "EBAY_DE"}
CATEGORY_KEYWORDS = {
    "home_storage": "home storage organizer",
    "pet_supplies": "pet supplies",
    "kitchen": "kitchen tools",
    "outdoor": "outdoor camping",
}


class EbayUnavailable(RuntimeError):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class EbayAdapter:
    token_url = "https://api.ebay.com/identity/v1/oauth2/token"
    search_url = "https://api.ebay.com/buy/browse/v1/item_summary/search"

    def __init__(self, client_id: str, client_secret: str, category_ids: dict[str, dict[str, str]] | None = None,
                 client: httpx.AsyncClient | None = None):
        self.client_id = client_id
        self.client_secret = client_secret
        self.category_ids = category_ids or {}
        self.client = client
        self._token: str | None = None
        self._token_expires = 0.0
        self._token_lock = asyncio.Lock()
        self._cache: OrderedDict[tuple, tuple[float, list[ProductData], str]] = OrderedDict()

    async def _get_token(self, force: bool = False) -> str:
        if not force and self._token and self._token_expires > time.monotonic() + 60:
            return self._token
        async with self._token_lock:
            if not force and self._token and self._token_expires > time.monotonic() + 60:
                return self._token
            credentials = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
            own_client = self.client is None
            client = self.client or httpx.AsyncClient(timeout=httpx.Timeout(10, connect=3))
            try:
                response = await client.post(
                    self.token_url,
                    headers={"Authorization": f"Basic {credentials}", "Content-Type": "application/x-www-form-urlencoded"},
                    data={"grant_type": "client_credentials", "scope": "https://api.ebay.com/oauth/api_scope"},
                )
                if response.status_code >= 400:
                    raise EbayUnavailable(f"oauth_http_{response.status_code}")
                payload = response.json()
                self._token = payload["access_token"]
                self._token_expires = time.monotonic() + int(payload.get("expires_in", 7200))
                return self._token
            except (httpx.HTTPError, KeyError, ValueError) as exc:
                if isinstance(exc, EbayUnavailable):
                    raise
                raise EbayUnavailable("oauth_connection_or_response_error") from exc
            finally:
                if own_client:
                    await client.aclose()

    async def search(self, market: str, category: str | None, keyword: str | None, limit: int) -> tuple[list[ProductData], bool, str]:
        query = keyword or CATEGORY_KEYWORDS.get(category or "", "popular products")
        category_id = self.category_ids.get(market, {}).get(category or "")
        key = (market, category, query, limit, category_id)
        cached = self._cache.get(key)
        if cached and cached[0] > time.monotonic():
            self._cache.move_to_end(key)
            return cached[1], True, cached[2]

        token = await self._get_token()
        params: dict[str, Any] = {"q": query, "limit": limit}
        filtering = "keyword"
        if category_id:
            params["category_ids"] = category_id
            filtering = "keyword_and_confirmed_category_id"
        headers = {"Authorization": f"Bearer {token}", "X-EBAY-C-MARKETPLACE-ID": MARKET_IDS[market]}
        own_client = self.client is None
        client = self.client or httpx.AsyncClient(timeout=httpx.Timeout(10, connect=3))
        try:
            response = None
            refreshed = False
            for attempt in range(3):
                try:
                    response = await client.get(self.search_url, params=params, headers=headers)
                    if response.status_code == 401 and not refreshed:
                        headers["Authorization"] = f"Bearer {await self._get_token(force=True)}"
                        refreshed = True
                        continue
                    if response.status_code in {429, 502, 503, 504} and attempt < 2:
                        wait = min(float(response.headers.get("Retry-After", "0.15")), 1.0)
                        await asyncio.sleep(max(wait, 0))
                        continue
                    break
                except (httpx.TimeoutException, httpx.NetworkError) as exc:
                    if attempt == 2:
                        raise EbayUnavailable("upstream_timeout_or_network_error") from exc
                    await asyncio.sleep(0.1 * (attempt + 1))
            assert response is not None
            if response.status_code >= 400:
                raise EbayUnavailable(f"browse_http_{response.status_code}")
            now = datetime.now(timezone.utc)
            items = [self.normalize_item(raw, category or "uncategorized", market, now) for raw in response.json().get("itemSummaries", [])]
            self._cache[key] = (time.monotonic() + 300, items, filtering)
            while len(self._cache) > 128:
                self._cache.popitem(last=False)
            return items, False, filtering
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            if isinstance(exc, EbayUnavailable):
                raise
            raise EbayUnavailable("browse_invalid_response") from exc
        finally:
            if own_client:
                await client.aclose()

    @staticmethod
    def normalize_item(raw: dict[str, Any], category: str, market: str, collected_at: datetime) -> ProductData:
        price = raw.get("price") or {}
        aspects = raw.get("localizedAspects") or []
        specification = "; ".join(
            f"{item.get('name')}: {item.get('value')}" for item in aspects if item.get("name") and item.get("value")
        ) or None
        return ProductData(
            id=str(raw["itemId"]), source="ebay", title=raw["title"], price=Decimal(str(price["value"])),
            currency=price["currency"], image_url=(raw.get("image") or {}).get("imageUrl", ""),
            product_url=raw.get("itemWebUrl", ""), rating=None, review_count=None, sales_count=None,
            category=category, specification=specification, market=market, data_mode="live",
            source_label="eBay Browse API 实时查询", collected_at=collected_at,
        )
