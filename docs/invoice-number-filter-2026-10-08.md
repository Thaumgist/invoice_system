# 发票号码筛选

发票列表“更多”中新增发票号码文本框，支持完整或部分号码包含匹配。前后空白会去除，前导零保留，空白输入不增加条件，`%`、`_` 按字面处理。只查询当前用户的 `invoice_num`，可与其他条件叠加，默认仍排除重复记录；清空搜索重置号码，既有跨页勾选机制保持不变。

GET 列表和 POST 搜索均接收 `invoice_num`，不修改数据库结构。

验证：Windows `npm run build`（类型检查、Vite）通过；容器内合成 SQLite 查询检查覆盖完整/部分号码、前导零、空白、字面百分号、无结果、用户隔离和重复记录排除。未写真实数据，未进行登录后的浏览器实测。

环境：Windows 前端依赖为 `frontend/node_modules`，产物 `frontend/dist`；后端使用 `invoice_backend` 的 `/usr/local/bin/python` 和 `/usr/local/lib/python3.11/site-packages`。没有新增依赖。隔离脚本为本机 Git 忽略目录下 `tmp/validate-invoice-number.py`。
