from decimal import Decimal

from commerce_backend.agent import assumptions_from_query, parse_intent
from commerce_backend.agent_tools import AGENT_TOOL_DEFINITIONS, OPENAI_COMPATIBLE_TOOLS
from commerce_backend.main import app
from commerce_backend.schemas import AgentRecommendationRequest
from fastapi.testclient import TestClient


def test_natural_language_intent_and_cost_parsing():
    payload = AgentRecommendationRequest(
        query="请推荐美国市场的家居收纳商品，采购价 40 元，运费 30 元，平台费率 12%，目标利润率 20%"
    )
    assert parse_intent(payload.query) == {"market": "US", "category": "home_storage", "keyword": None}
    assumptions, fields = assumptions_from_query(payload)
    assert assumptions.shipping_cny == Decimal(30)
    assert assumptions.purchase_price_cny == Decimal(40)
    assert assumptions.platform_fee_rate == Decimal("0.12")
    assert assumptions.target_profit_rate == Decimal("0.20")
    assert set(fields) == {"purchase_price_cny", "shipping_cny", "platform_fee_rate", "target_profit_rate"}


def test_structured_cost_values_override_natural_language():
    payload = AgentRecommendationRequest.model_validate({
        "query": "推荐美国户外商品，运费 30 元",
        "cost_assumptions": {"shipping_cny": 10},
    })
    assumptions, fields = assumptions_from_query(payload)
    assert assumptions.shipping_cny == Decimal(10)
    assert "shipping_cny" not in fields


def test_agent_endpoint_ranks_and_labels_demo_results():
    with TestClient(app) as client:
        response = client.post("/api/agent/recommend", json={
            "query": "请推荐美国市场的家居收纳商品，运费 30 元，平台费率 12%，目标利润率 20%",
            "max_results": 5,
            "generate_copy_for_top": True,
        })
        assert response.status_code == 200
        body = response.json()
        ranked = body["data"]["ranked_products"]
        assert len(ranked) == 5
        assert [item["rank"] for item in ranked] == [1, 2, 3, 4, 5]
        scores = [item["analysis"]["overall_score"] for item in ranked]
        assert scores == sorted(scores, reverse=True)
        assert body["meta"]["data_mode"] == "demo"
        assert "不是真实销量预测" in body["meta"]["scoring_label"]
        assert body["meta"]["cost_assumptions"]["shipping_cny"] == "30"
        assert body["meta"]["collected_at_range"]["earliest"]
        assert body["data"]["generated_copy_for_top"]["generation_mode"] == "template"
        for item in ranked:
            evidence = item["evidence"]
            assert evidence["source"]
            assert evidence["collected_at"]
            assert evidence["demo_fields"]
            assert evidence["platform_fields"] == []
            assert "simulated_fields" in evidence
            assert "inferred_fields" in evidence


def test_agent_returns_empty_result_without_cross_market_demo_substitution():
    with TestClient(app) as client:
        response = client.post("/api/agent/recommend", json={
            "query": "推荐英国市场的户外商品",
            "max_results": 3,
        })
        assert response.status_code == 200
        assert response.json()["data"]["ranked_products"] == []
        assert "没有演示记录" in response.json()["meta"]["source_notice"]


def test_agent_tools_reuse_the_six_base_endpoints():
    assert {tool["endpoint"] for tool in AGENT_TOOL_DEFINITIONS} == {
        "GET /api/health", "GET /api/products", "GET /api/products/{id}",
        "GET /api/products/{id}/suppliers", "POST /api/recommendations", "POST /api/generate-copy",
    }
    assert len(OPENAI_COMPATIBLE_TOOLS) == 6
    assert all(tool["type"] == "function" for tool in OPENAI_COMPATIBLE_TOOLS)


def test_target_profit_rate_changes_profit_score():
    with TestClient(app) as client:
        low_target = client.post("/api/recommendations", json={
            "product_ids": ["product_001"], "cost_assumptions": {"target_profit_rate": 0.10}
        }).json()["data"][0]
        high_target = client.post("/api/recommendations", json={
            "product_ids": ["product_001"], "cost_assumptions": {"target_profit_rate": 0.60}
        }).json()["data"][0]
        assert low_target["profit_potential"] > high_target["profit_potential"]
        assert Decimal(low_target["profit_estimate"]["target_profit_rate"]) == Decimal("0.10")


def test_product_specific_purchase_price_override_is_used():
    with TestClient(app) as client:
        result = client.post("/api/recommendations", json={
            "product_ids": ["product_001"],
            "cost_assumptions": {"purchase_price_overrides_cny": {"product_001": 88}},
        }).json()["data"][0]
        assert Decimal(result["profit_estimate"]["purchase_cny"]) == Decimal(88)
        assert result["profit_estimate"]["purchase_price_source"] == "request_override"
