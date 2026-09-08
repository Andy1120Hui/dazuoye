"""Tool contracts for an LLM orchestrator. Each tool maps to an existing API."""

AGENT_TOOL_DEFINITIONS = [
    {
        "name": "search_products",
        "endpoint": "GET /api/products",
        "description": "按市场、业务分类和关键词查询 eBay 实时商品或明确标记的演示商品。",
        "input_schema": {
            "type": "object",
            "properties": {
                "market": {"type": "string", "enum": ["US", "GB", "DE"]},
                "category": {"type": "string", "enum": ["home_storage", "pet_supplies", "kitchen", "outdoor"]},
                "keyword": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 50},
            },
            "required": ["market", "limit"],
        },
    },
    {
        "name": "get_product",
        "endpoint": "GET /api/products/{id}",
        "description": "读取标准化商品详情、数据来源、数据模式和采集时间。",
        "input_schema": {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]},
    },
    {
        "name": "get_candidate_suppliers",
        "endpoint": "GET /api/products/{id}/suppliers",
        "description": "读取人工编制或导入的模拟候选货源；不得解释为真实批发报价或同款。",
        "input_schema": {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]},
    },
    {
        "name": "compare_recommendations",
        "endpoint": "POST /api/recommendations",
        "description": "使用可配置模拟成本比较多个商品，返回启发式评分、风险与计算依据。",
        "input_schema": {
            "type": "object",
            "properties": {
                "product_ids": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                "cost_assumptions": {"type": "object"},
            },
            "required": ["product_ids"],
        },
    },
    {
        "name": "generate_product_copy",
        "endpoint": "POST /api/generate-copy",
        "description": "基于已有商品事实生成多语言文案，不得补写销量、评价、认证或性能。",
        "input_schema": {
            "type": "object",
            "properties": {
                "product_id": {"type": "string"},
                "target_language": {"type": "string", "enum": ["zh", "en", "de", "es"]},
                "style": {"type": "string", "enum": ["concise", "professional", "lively"]},
            },
            "required": ["product_id", "target_language", "style"],
        },
    },
    {
        "name": "health_check",
        "endpoint": "GET /api/health",
        "description": "检查服务、数据库和当前数据状态；不触发外部采集。",
        "input_schema": {"type": "object", "properties": {}},
    },
]


OPENAI_COMPATIBLE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": tool["name"],
            "description": tool["description"],
            "parameters": tool["input_schema"],
        },
    }
    for tool in AGENT_TOOL_DEFINITIONS
]
