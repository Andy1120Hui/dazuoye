# 数据采集与导入

`commerce_backend.adapters` 只通过 eBay Browse API 查询真实在售商品。无 eBay 生产权限或凭据时，后端自动使用 `data/` 中明确标记的演示商品。国内候选货源仅使用人工编制或用户导入的模拟采购数据。

安装后可通过官方接口小规模采集，或导入候选货源：

```powershell
.\backend\.venv\Scripts\python.exe crawler\collect.py ebay --keyword "storage box" --category home_storage --market US --limit 10
.\backend\.venv\Scripts\python.exe crawler\import_suppliers.py path\to\suppliers.csv
```

CSV/JSON 字段与 `data/demo_suppliers.json` 一致。导入会先校验全部记录，任一记录失败时不写入数据库。导入后的采购价仍是课堂模拟参数，不会标记为真实批发报价。
