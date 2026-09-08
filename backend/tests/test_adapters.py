import asyncio

import httpx
from commerce_backend.adapters.ebay import EbayAdapter


def test_ebay_search_cache_avoids_duplicate_upstream_request():
    calls = {"token": 0, "search": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            calls["token"] += 1
            return httpx.Response(200, json={"access_token": "safe-test-token", "expires_in": 7200})
        calls["search"] += 1
        return httpx.Response(200, json={"itemSummaries": [{
            "itemId": "v1|demo|0", "title": "Storage Box",
            "price": {"value": "12.50", "currency": "USD"},
            "image": {"imageUrl": "https://example.com/image"},
            "itemWebUrl": "https://example.com/product",
        }]})

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            adapter = EbayAdapter("id", "secret", client=client)
            first, cached_first, _ = await adapter.search("US", "home_storage", None, 5)
            second, cached_second, _ = await adapter.search("US", "home_storage", None, 5)
            assert first[0].id == second[0].id
            assert cached_first is False and cached_second is True

    asyncio.run(scenario())
    assert calls == {"token": 1, "search": 1}


def test_ebay_retries_temporary_service_errors_only_to_limit():
    calls = {"search": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "safe-test-token", "expires_in": 7200})
        calls["search"] += 1
        if calls["search"] < 3:
            return httpx.Response(503)
        return httpx.Response(200, json={"itemSummaries": []})

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            adapter = EbayAdapter("id", "secret", client=client)
            products, _, _ = await adapter.search("US", "outdoor", None, 5)
            assert products == []

    asyncio.run(scenario())
    assert calls["search"] == 3
