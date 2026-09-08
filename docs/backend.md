# 商品数据、经营模拟与 Agent 接口

## 系统定位与数据边界

本系统用于课堂选品与经营模拟。它不提供真实下单、推广、结算或供应链对接。

国外商品配置 eBay Browse API 生产权限后来自实时查询；未配置或上游不可用时，使用 `data/demo_foreign_products.json` 中 20 条人工演示商品。eBay 搜索摘要缺少的评分、评价数或规格保持 `null`，卖家信用和估计售出量不会当作商品评价或真实销量。

国内候选货源只来自 `data/demo_suppliers.json` 或用户导入的 CSV/JSON，采购价属于课堂模拟成本。它们不能称为真实批发报价、稳定供货或确认同款。系统不依赖淘宝、京东或其他国内平台的应用权限。

所有商品和 Agent 输出都携带：

- `source/source_label`：来源；
- `collected_at`：平台采集时间或演示数据编制时间；
- `data_mode`：`live`、`demo` 或 `imported`；
- `cost_assumptions`：汇率、采购价、物流费、平台费、其他费用和目标利润率；
- `missing_fields/simulated_fields/inferred_fields`：真实缺失、课堂模拟和规则推断的边界。

## 标准化数据

国外商品字段为 `id`、`source`、`title`、`price`、`currency`、`image_url`、`product_url`、`rating`、`review_count`、`sales_count`、`category`、`specification`、`market`、`data_mode`、`source_label`、`collected_at`。

候选货源字段为 `id`、`product_id`、`source`、`title`、`purchase_price`、`currency`、`image_url`、`product_url`、`minimum_order_quantity`、`specification`、`match_score`、`match_reason`、`category`、`data_mode`、`source_label`、`price_basis`、`collected_at`。

金额必须为正有限数，币种采用三位大写代码，时间必须带时区。未知字段使用 `null`，不生成替代值。

## 六个基础工具接口

成功响应统一为 `{"data": ..., "meta": ...}`；错误响应统一为 `{"error":{"code":"...","message":"...","details":...,"request_id":"..."}}`。

- `GET /api/health`：服务、数据库和当前记录状态，不访问外部平台。
- `GET /api/products?market=US&category=home_storage&keyword=storage&limit=5`：查询商品。市场支持 `US/GB/DE`，类别支持 `home_storage/pet_supplies/kitchen/outdoor`，limit 为 1–50。
- `GET /api/products/{id}`：读取商品详情及来源边界。
- `GET /api/products/{id}/suppliers`：按相似度返回模拟候选货源。
- `POST /api/recommendations`：用可配置模拟成本比较一个或多个商品。
- `POST /api/generate-copy`：用已有商品事实生成中、英、德、西班牙语文案。

LLM 工具契约位于 `backend/commerce_backend/agent_tools.py`，每个工具直接映射上述接口；其中 `OPENAI_COMPATIBLE_TOOLS` 可直接作为兼容 Chat Completions 的 function tools。系统提示词位于 `backend/commerce_backend/prompts/agent_system.md`。提示词要求 Agent 先查询再比较，并禁止自行生成商品、销量、评价、成本或认证。

## 自然语言 Agent 接口

`POST /api/agent/recommend` 是唯一新增接口，用于补足六个基础接口没有的自然语言编排能力。零模型密钥时使用受限的中英文意图解析器；配置大模型后，前端 Agent 仍应遵守同一工具契约和系统提示词。

请求示例：

```json
{
  "query": "请推荐美国市场的家居收纳商品，采购价40元，运费30元，平台费率12%，目标利润率20%",
  "max_results": 5,
  "generate_copy_for_top": true,
  "target_language": "zh",
  "copy_style": "professional"
}
```

也可以显式传递模拟参数；结构化值优先于自然语言中的值：

```json
{
  "query": "推荐美国户外商品",
  "max_results": 5,
  "cost_assumptions": {
    "exchange_rates_to_cny": {"USD": 7.2, "CNY": 1},
    "purchase_price_cny": null,
    "purchase_price_overrides_cny": {"product_001": 40},
    "shipping_cny": 25,
    "platform_fee_rate": 0.15,
    "other_cost_cny": 0,
    "target_profit_rate": 0.25
  }
}
```

响应中的 `ranked_products` 按综合评分降序排列。每项同时包含标准化商品、分析结果和 `evidence` 字段分类；`meta.tool_trace` 列出本次编排复用的基础工具，`meta.collected_at_range`、`data_sources`、`data_mode` 与 `cost_assumptions` 用于复核。

## Agent 推荐流程

1. 从自然语言识别市场、类别、引号内关键词和模拟成本；无法识别市场时默认 US，无法识别类别时执行通用关键词查询。
2. 调用商品搜索。eBay 有生产权限时返回 `live`；未配置或失败时返回带降级原因的 `demo`。实时查询成功但为空时保持空结果。
3. 对每个商品读取模拟候选货源，以类别、标题概念和规格相似度建立匹配。匹配分不是同款概率。
4. 应用相同的成本参数计算每个商品的需求、竞争、利润和运输维度，再按综合评分排序。
5. 输出推荐顺序、理由、风险、缺失字段、来源、采集时间和关键计算假设。只有用户要求时才为第一名生成文案。

## 评分和模拟成本

候选匹配为 `35% 类别 + 45% 标题概念相似度 + 20% 规格相似度`，材料或尺寸冲突会扣分。

需求潜力使用商品评价和评价量；缺失时使用中性值 50 并写入 `missing_data`。竞争程度只表示当前数据库内同类样本密度。运输难度来自类别及易碎、电池、大件关键词。

利润默认使用最高分模拟候选货源的采购价。`purchase_price_cny` 可以为本次比较统一覆盖采购价，`purchase_price_overrides_cny` 可以按商品 ID 分别覆盖，后者优先。默认参数是 `1 USD = 7.2 CNY`、物流费 25 CNY、平台费率 15%、其他费用 0、目标利润率 25%。达到目标利润率对应利润分 50；高出或低于目标 25 个百分点分别对应 100 或 0，并限制在 0–100。

综合评分权重为需求 25%、反向竞争 20%、利润 40%、反向运输 15%；利润无法计算时移除利润项并重新归一化。所有结果统一称为“启发式选品评分，不是真实销量预测”。

## eBay 与零密钥模式

eBay Browse 使用应用级 OAuth、生产 API 地址和 `X-EBAY-C-MARKETPLACE-ID`。401 最多刷新令牌一次，403 不重试，连接问题、超时、429 和暂时性 5xx 最多重试两次。查询缓存 5 分钟，命中缓存时保留原采集时间。生产凭据只从环境变量读取，不进入代码、数据库或日志。

没有任何外部密钥时，服务仍能启动、使用 20 条国外演示商品和 20 条模拟候选货源完成完整 Agent 流程。GB、DE 没有演示记录时返回空数组，不使用 US 数据替代。

本地前端默认允许 `localhost` 和 `127.0.0.1` 的 3000、5173 端口访问；其他地址通过 `CORS_ORIGINS` 配置。
