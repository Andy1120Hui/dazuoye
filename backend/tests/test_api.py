from fastapi.testclient import TestClient

from commerce_backend.main import app


def test_zero_key_demo_api_flow():
    with TestClient(app) as client:
        health = client.get("/api/health")
        assert health.status_code == 200
        assert health.json()["data"]["products"] == 20
        assert health.json()["data"]["suppliers"] == 20

        products = client.get("/api/products", params={"market": "US", "category": "home_storage", "limit": 5})
        assert products.status_code == 200
        body = products.json()
        assert len(body["data"]) == 5
        assert body["meta"]["data_mode"] == "demo"
        assert all(item["sales_count"] is None for item in body["data"])

        product_id = body["data"][0]["id"]
        detail = client.get(f"/api/products/{product_id}")
        assert detail.status_code == 200
        assert detail.json()["meta"]["data_mode"] == "demo"

        suppliers = client.get(f"/api/products/{product_id}/suppliers")
        assert suppliers.status_code == 200
        assert suppliers.json()["meta"]["label"] == "候选货源"
        scores = [item["match_score"] for item in suppliers.json()["data"]]
        assert scores == sorted(scores, reverse=True)

        recommendation = client.post("/api/recommendations", json={"product_ids": [product_id]})
        assert recommendation.status_code == 200
        result = recommendation.json()
        assert "不是真实销量预测" in result["meta"]["notice"]
        assert result["data"][0]["profit_estimate"] is not None

        copy = client.post("/api/generate-copy", json={"product_id": product_id, "target_language": "zh", "style": "professional"})
        assert copy.status_code == 200
        assert len(copy.json()["data"]["selling_points"]) == 5
        assert copy.json()["meta"]["generation_mode"] == "template"


def test_errors_cors_and_non_us_demo_boundary():
    with TestClient(app) as client:
        assert client.get("/api/products/missing").status_code == 404
        invalid = client.get("/api/products", params={"limit": 0})
        assert invalid.status_code == 422
        assert invalid.json()["error"]["code"] == "validation_error"
        empty = client.get("/api/products", params={"market": "GB"})
        assert empty.status_code == 200 and empty.json()["data"] == []
        cors = client.options("/api/products", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"})
        assert cors.headers["access-control-allow-origin"] == "http://localhost:5173"
