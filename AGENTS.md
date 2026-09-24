# InvoiceSystem 开发约定

## 修改范围

- 默认通过 WSL Bash 执行命令，区分 Windows 与 WSL 路径，保留无关工作区改动。
- 仅在用户要求时提交和推送。当前 main 跟踪个人远端 fork/main；推送前重新核对，不默认推送上游 origin。
- 前端使用 Vue、Pinia 和 Element Plus；通过 frontend/package-lock.json 固定依赖，不为单个修复升级依赖。

## 发票勾选语义

- frontend/src/stores/invoice.ts 中的 selectedInvoiceMap 是已选发票的唯一数据源，以发票 ID 标识，不依赖对象引用或当前列表页。
- 筛选、取消筛选、空结果、翻页、修改每页条数和列表刷新都不得清空已选集合。
- 行勾选使用 Element Plus 的 select 事件更新该行；表头 select-all 只更新当前页，保留其他页的选择。
- 不得用通用 selection-change 事件反向覆盖全局选择：数据替换及程序调用 clearSelection、toggleRowSelection 同样会触发它。
- 数据和已选 ID 变化后，在表格渲染完成时从全局集合恢复勾选。回填过程不得改变全局集合。
- 用户主动取消勾选、确认清空选择或成功删除发票时，才移除相应选择。整页刷新后的持久化不属于当前保证范围。
- 批量打印、打包下载及批量修改报销状态必须使用同一全局集合，不能仅使用当前可见行。

## 界面约定

- 页面可整体纵向滚动，表格内部也有独立纵向滚动；展开更多筛选不能压缩或隐藏表格。
- 保留表格主体横向滚动，操作列固定在视窗内右侧；不重新加入单独的表头横向滚动条。
- 筛选条件与列设置相互独立。报销状态为未报销、已报销、需换开、报销中、疑似红冲；不恢复通用状态列，OCR 状态可保留。
- 商品名称仅搜索商品明细中的名称和 OCR words_result.CommodityName 名称列表，兼容 name/word 对象及旧字符串数组；不得模糊搜索整份商品明细或 OCR JSON。金额使用独立金额筛选；名称中的 %、_ 等字符按字面匹配。
- 默认验证桌面环境，除非用户要求，不切换手机模拟。

## 验证与环境路径

- Windows 仓库：E:/Projects/InvoiceSystem/invoice_system；WSL 仓库：/mnt/e/Projects/InvoiceSystem/invoice_system。
- Docker CLI：/mnt/e/DockerData/DockerDesktopApp/resources/bin/docker.exe；从仓库目录运行 Compose。
- 前端入口：http://localhost:8080。生产构建使用 frontend/Dockerfile 的 build-stage：Node 18 Alpine，工作目录 /app，依赖目录 /app/node_modules。
- 构建验证：docker.exe compose build frontend，其中执行 vue-tsc --noEmit 和 vite build。本地更新只需 docker.exe compose up -d --no-deps frontend。
- 勾选回归至少覆盖：最低金额筛选后勾选再清空、空结果后恢复、跨页选择、当前页全选/取消、主动取消单行、刷新、批量打印往返及已选数量/金额一致性。
- 测试不得修改真实发票内容、报销状态或删除真实数据。隔离测试使用合成数据；明确区分组件验证、构建验证与浏览器实测。
- 2026-09-24 勾选回归使用 Node 18.20.8、Vue 3.5.18、Pinia 2.3.1、Element Plus 2.10.7，生产依赖位于验证容器 /app/node_modules；额外隔离依赖 jsdom 22.1.0 位于 /tmp/selection-deps/node_modules，不修改项目依赖清单或锁文件。
- 本机隔离脚本位于被 Git 忽略的 tmp/selection-validation-20260924/run.cjs，容器中只读挂载到 /checks/run.cjs；正式验证记录见 docs/selection-regression-2026-09-24.md。
- 2026-09-24 商品搜索验证环境：invoice_backend 容器的 /usr/local/bin/python（Python 3.11.13），依赖 /usr/local/lib/python3.11/site-packages（SQLAlchemy 2.0.23），数据库为 MySQL 8.0.46。代码挂载到 /app/app，未新增依赖或数据库字段。
- 商品搜索验证脚本位于本机忽略目录 tmp/commodity-search-validation-20260924/，容器副本为 /tmp/commodity-search-validation-20260924.py 和 /tmp/commodity-search-live-readonly-20260924.py；正式记录见 docs/commodity-search-regression-2026-09-24.md。
