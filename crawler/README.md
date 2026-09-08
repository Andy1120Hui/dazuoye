# 数据采集与导入

`commerce_backend.adapters` 仅连接 eBay Browse API 和淘宝联盟官方接口，不读取 Cookie、不处理验证码，也不绕过登录或访问限制。无凭据时后端自动使用 `data/` 中明确标记的演示数据。

安装后可通过官方接口小规模采集，或导入候选货源：

```powershell
.\backend\.venv\Scripts\python.exe crawler\collect.py ebay --keyword "storage box" --category home_storage --market US --limit 10
.\backend\.venv\Scripts\python.exe crawler\collect.py taobao --keyword "收纳盒" --category home_storage --limit 10
.\backend\.venv\Scripts\python.exe crawler\import_suppliers.py path\to\suppliers.csv
```

CSV/JSON 字段与 `data/demo_suppliers.json` 一致。导入会先校验全部记录，任一记录失败时不写入数据库。
