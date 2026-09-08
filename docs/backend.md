# 商品数据与后端接口

## 数据边界

仓库内 `data/demo_foreign_products.json` 和 `data/demo_suppliers.json` 均为人工编制的课堂演示数据，不是从 eBay、淘宝或京东实时采集的结果。演示商品的价格、评分、评价数和演示货源价格仅用于展示；销量字段统一为 `null`。演示链接使用 `example.com`，图片使用仓库内的通用分类占位图。

配置并获准使用 eBay Browse API 后，实时商品会标记为 `data_mode=live` 和 `source_label=eBay Browse API 实时查询`。搜索摘要没有商品评价时，`rating`、`review_count` 保持 `null`；卖家信用和估计售出量不会映射为评价量或真实销量。

淘宝适配器只调用淘宝联盟官方接口，不使用 Cookie、不模拟登录、不处理验证码、不轮换代理或绕过访问限制。淘宝联盟价格属于零售采购参考价，不代表批发价、库存或供货承诺。当前六个公开 API 不主动调用淘宝；适配器用于经授权的采集/导入流程，默认候选货源来自演示数据或用户导入文件。

## 标准化字段

国外商品：`id`、`source`、`title`、`price`、`currency`、`image_url`、`product_url`、`rating`、`review_count`、`sales_count`、`category`、`specification`、`market`、`data_mode`、`source_label`、`collected_at`。

候选货源：`id`、`product_id`、`source`、`title`、`purchase_price`、`currency`、`image_url`、`product_url`、`minimum_order_quantity`、`specification`、`match_score`、`match_reason`、`category`、`data_mode`、`source_label`、`price_basis`、`collected_at`。

金额为正有限数，币种采用三位大写代码，采集时间必须带时区。未知的评分、评价数、销量、规格和起订量使用 `null`，不生成替代值。

## API 约定

成功响应统一为：

```json
{"data": {}, "meta": {"data_mode": "demo"}}
```

错误响应统一为：

```json
{"error": {"code": "not_found", "message": "商品 不存在", "details": {"id": "missing"}, "request_id": "..."}}
```

- `GET /api/health`：数据库与演示数据状态，不访问外部平台。
- `GET /api/products?market=US&category=home_storage&keyword=storage&limit=5`：市场支持 `US/GB/DE`，类别支持 `home_storage/pet_supplies/kitchen/outdoor`，limit 为 1–50。无 eBay 凭据时使用 US 演示数据；GB、DE 没有演示记录时返回空数组。
- `GET /api/products/{id}`：商品详情和来源边界。
- `GET /api/products/{id}/suppliers`：按分数降序返回“候选货源”。匹配分只表示文本与规格相似度，不是同款概率。
- `POST /api/recommendations`：请求包含 `product_ids` 与可选 `cost_assumptions`。
- `POST /api/generate-copy`：请求包含 `product_id`、`target_language`（`zh/en/de/es`）和 `style`（`concise/professional/lively`）。

推荐请求示例：

```json
{
  "product_ids": ["product_001"],
  "cost_assumptions": {
    "exchange_rates_to_cny": {"USD": 7.2, "CNY": 1},
    "shipping_cny": 25,
    "platform_fee_rate": 0.15,
    "other_cost_cny": 0
  }
}
```

## 匹配和评分

候选匹配在同一业务类别内进行，得分为 `35% 类别 + 45% 标题概念相似度 + 20% 规格相似度`。文本使用 NFKC、大小写与常用尺寸单位归一化，中英文概念词典支持四个演示类别；材料和尺寸明显冲突会扣分。API 同时返回文字依据。

推荐维度均为 0–100：需求潜力取商品评价和评价量；缺失时各使用中性值 50，并列入 `missing_data`。竞争程度只表示当前数据库内同类样本密度。运输难度由类别及易碎、电池、大件关键词决定。

利润以最高分候选货源计算。默认课堂假设为 `1 USD = 7.2 CNY`、每件运费 25 CNY、平台费率 15%、其他费用 0；请求可覆盖这些参数。净利率 0% 对应利润分 0，50% 对应 100，区间外截断。综合分权重为需求 25%、反向竞争 20%、利润 40%、反向运输难度 15%；利润未知时去掉利润项并重新归一化。

每个推荐响应都注明“启发式选品评分，不是真实销量预测”，并返回公式版本、成本假设、样本量与缺失数据。模型文案失败或未配置时使用对应语言模板，并返回 `generation_mode=template`；模板和模型提示均禁止编造销量、认证或性能。

## 平台与运行限制

eBay Browse 使用应用级 OAuth。应用凭据不等于生产 Buy API 权限；401 会刷新令牌一次，403 不重试，连接问题、超时、429 和暂时性 5xx 最多重试两次。查询缓存 5 分钟，缓存命中保留原 `collected_at`。实时查询成功但为空时返回空数组，不用演示数据替换。

淘宝联盟接口仍需 AppKey、签名与推广位，并可能有场景权限限制。遇到权限错误、验证码/HTML 响应或限流会立即停止，不尝试规避；连接问题或暂时性 5xx 最多重试两次，查询缓存 10 分钟。CSV/JSON 导入器是无平台权限时的稳定补充路径。

本地前端默认允许 `localhost` 和 `127.0.0.1` 的 3000、5173 端口访问；其他地址通过 `CORS_ORIGINS` 配置。
