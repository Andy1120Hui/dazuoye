# AI 跨境电商选品与经营模拟后端

这是用于课堂演示的 FastAPI 服务。没有任何外部密钥时，服务会自动加载 20 条国外演示商品和 20 条国内演示候选货源；演示记录在 API 中始终带有 `data_mode=demo` 和来源说明。

## Windows 安装与启动

在仓库根目录运行：

```powershell
python -m venv backend/.venv
.\backend\.venv\Scripts\python.exe -m pip install -e "./backend[dev]"
.\backend\.venv\Scripts\python.exe -m uvicorn commerce_backend.main:app --host 127.0.0.1 --port 8000
```

接口文档：<http://127.0.0.1:8000/docs>；健康检查：<http://127.0.0.1:8000/api/health>。

## 环境变量

复制 `backend/.env.example` 为 `backend/.env` 后按需填写。不要提交 `.env`。

- `DATABASE_URL`：SQLite 地址。
- `CORS_ORIGINS`：逗号分隔的前端来源。
- `EBAY_CLIENT_ID`、`EBAY_CLIENT_SECRET`：eBay 应用凭据。
- `EBAY_CATEGORY_IDS_JSON`：确认过的市场类别映射，例如 `{"US":{"outdoor":"159043"}}`；未配置时只使用关键词。
- `TAOBAO_APP_KEY`、`TAOBAO_APP_SECRET`、`TAOBAO_ADZONE_ID`：淘宝联盟官方接口配置。
- `LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL`：可选的兼容 Chat Completions 服务。URL 应指向包含 `/v1` 的 API 根地址。

密钥只从环境变量读取，不进入日志。eBay Buy API 即使已有应用凭据，也可能尚未获得生产访问权限；这种情况下商品列表会返回带降级原因的演示数据。

## 测试与导入

```powershell
.\backend\.venv\Scripts\python.exe -m pytest backend/tests -q
.\backend\.venv\Scripts\python.exe crawler/collect.py ebay --keyword "storage box" --category home_storage --market US --limit 10
.\backend\.venv\Scripts\python.exe crawler/collect.py taobao --keyword "收纳盒" --category home_storage --limit 10
.\backend\.venv\Scripts\python.exe crawler/import_suppliers.py data/demo_suppliers.json
```

导入器支持 UTF-8/UTF-8 BOM 的 CSV 和 JSON 数组。全部记录通过校验后才写入，重复 ID 会更新原记录。

完整字段、接口和评分说明见 [docs/backend.md](../docs/backend.md)。
