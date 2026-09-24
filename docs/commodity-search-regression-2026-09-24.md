# 商品名称搜索范围修复

日期：2026-09-24。

## 原因与修复

原查询将商品明细和整份 OCR JSON 转为文本后执行 LIKE。商品名称输入 352 时，金额 352.00 以及恰好包含 352 的 OCR log_id 都会被命中，因而出现与商品名称无关的发票。

当前查询仅在以下两个来源中提取名称：

- commodity_details 中的 name、word 字段及字符串名称。
- ocr_raw_data.words_result.CommodityName 中的 name、word 字段及旧字符串名称数组。

使用现有 MySQL 8 的 JSON_TABLE 取出名称标量，并通过 EXISTS 子查询匹配。对象/数组类型的非标量字段、缺失名称和空值不会作为文本展开匹配；金额、税额、行号、发票号码、税号、日志编号都不在名称搜索范围内。

搜索值使用 SQLAlchemy 绑定参数和 contains(autoescape=True)，保留名称的包含匹配，同时把百分号、下划线、转义字符当作普通输入处理。多个名称或多个来源同时命中时，仍只返回一张发票。

总数使用同一筛选条件直接 COUNT(id)，不再将整行及 JSON 相关子查询套入 query.count() 的派生表。隔离验证中直接计数与实际记录数一致；原派生计数形式在本机 MySQL 上出现过 JSON 错误或计数偏差。

没有修改前端布局、已选集合、数据库表结构或项目依赖。

## 验证结果

### 合成数据回归：21 项通过

直接调用实际 InvoiceService.get_invoices，在 MySQL 会话级临时表 commodity_search_fixture 中放置合成发票。临时表仅复制真实 invoices 表结构，不复制真实记录，通过临时模型映射测试；结束时删除临时表并回滚连接。

- 复现原整份 JSON 匹配造成的金额、日志编号及行号误命中。
- 352 只命中名称，排除金额、税额、行号、日志编号、发票号码和税号。
- 首尾空格、中文包含搜索、后续商品明细名称正常。
- 兼容整理后的 name/word、OCR 对象名称、旧字符串名称及混合名称数组。
- JSON null、SQL NULL、空数组、缺失字段和非标量名称不导致错误匹配或接口异常。
- 百分号、下划线、斜杠、反斜杠和引号按普通文本安全匹配；SQL 样式输入不扩大结果。
- 空搜索、无结果搜索、报销状态组合筛选、精确金额和最低金额组合正常。
- 用户范围、包含重复选项、分页计数及多来源命中去重正常。

### 真实记录及接口只读验证：4 项通过

使用 SELECT-only 事务核对本机截图对应记录：

- 商品名称 352：0 条，排除了原来的 352.00 和 179.62 两张误命中发票。
- 精确金额 352.00：1 条，正确金额查询保留。
- 通过 FastAPI TestClient 调用真实 GET/POST 搜索路由，响应均为 200，记录和分页总数一致；仅在测试应用中替换身份依赖，不修改线上认证。
- 中文名称鼠标及每页 1 条的分页元数据正常。

不输出真实发票完整数据，不修改内容、报销状态或已选集合。以上是数据库与接口验证，不声称已完成浏览器实测。

## 环境与复核路径

- Python 3.11.13：invoice_backend 容器的 /usr/local/bin/python。
- SQLAlchemy 2.0.23：/usr/local/lib/python3.11/site-packages。
- MySQL 8.0.46；现有应用代码挂载到 /app/app。
- 本机忽略目录 tmp/commodity-search-validation-20260924/run.py 为合成数据回归，live_readonly.py 为只读接口核对。
- 容器执行副本分别为 /tmp/commodity-search-validation-20260924.py 和 /tmp/commodity-search-live-readonly-20260924.py，通过 PYTHONPATH=/app 导入项目。
- 不引入项目测试框架、不新增依赖，保留本机验证脚本；仓库记录验证方法与结果。
