from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from commerce_backend.adapters.ebay import EbayAdapter
from commerce_backend.schemas import ProductData


BASE = {
    "id": "p", "source": "demo", "title": "Item", "price": 10, "currency": "USD",
    "image_url": "x", "product_url": "x", "category": "kitchen", "source_label": "test",
    "data_mode": "demo", "collected_at": "2026-09-08T09:00:00+08:00",
}


@pytest.mark.parametrize("price", [0, -1, "NaN", "Infinity"])
def test_product_rejects_invalid_price(price):
    with pytest.raises(ValidationError):
        ProductData.model_validate({**BASE, "price": price})


def test_product_requires_currency_and_timezone():
    with pytest.raises(ValidationError):
        ProductData.model_validate({**BASE, "currency": "US"})
    with pytest.raises(ValidationError):
        ProductData.model_validate({**BASE, "collected_at": "2026-09-08T09:00:00"})


def test_ebay_search_does_not_convert_seller_feedback_or_estimated_sales():
    raw = {
        "itemId": "v1|123|0", "title": "Demo", "price": {"value": "19.99", "currency": "USD"},
        "image": {"imageUrl": "https://example.com/image"}, "itemWebUrl": "https://example.com/item",
        "seller": {"feedbackScore": 9999}, "estimatedAvailabilities": [{"estimatedSoldQuantity": 800}],
    }
    item = EbayAdapter.normalize_item(raw, "home_storage", "US", datetime.now(timezone.utc))
    assert item.rating is None
    assert item.review_count is None
    assert item.sales_count is None
