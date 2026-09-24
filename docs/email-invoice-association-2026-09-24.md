# 邮件展开列表发票关联修复

日期：2026-09-24。

## 原因与处理

原实现将扫描结果中的发票 ID 与附件、ZIP 推测名称及正文 PDF 链接的文件名匹配结果合并。不同邮件的附件可以同名，因此展开列表会混入当前用户其他邮件中的发票。

关联现在仅使用 scan_result.files 中的 invoice_id 和 existing_invoice_id，保留用户范围过滤、去重和扫描记录顺序。不再按文件名推断归属，缺失或已删除的 ID 不回退到同名文件。历史邮件若没有明确 ID，其内嵌列表为空；不为补齐展示自动重扫邮件或修改真实数据。扫描计数与现存可关联发票数不是完全相同的概念，本次不修改 invoice_count。

## 验证

- 11 项合成检查通过：同名文件只返回明确关联、重复发票 ID、同一邮件多张发票、重复扫描 existing_invoice_id、跨用户 ID 排除、已删除 ID、仅文件名、空关联、非字典条目、空邮件列表、无 ID 列表覆盖。
- 使用 SQLite 内存库和最小合成发票模型，调用实际 EmailListService 方法；不写入真实数据库。
- MySQL READ ONLY 事务核对截图日期的两封相关邮件，存储计数和新关联数均为 1；只输出计数，不记录邮件正文、账户、附件文件名或发票内容。
- 不涉及前端变动；未做浏览器实测。未增加依赖或数据库字段。

## 验证环境

- WSL 项目：/mnt/e/Projects/InvoiceSystem/invoice_system。
- Docker CLI：/mnt/e/DockerData/DockerDesktopApp/resources/bin/docker.exe。
- 在 invoice_backend 容器通过 compose exec -T backend python - 执行 stdin 脚本。
- Python：/usr/local/bin/python；已有依赖：/usr/local/lib/python3.11/site-packages；应用：/app/app。
- 合成库为 SQLite 内存数据库，真实数据库仅执行 SELECT；验证脚本由 stdin 传入，不保存敏感数据文件。
