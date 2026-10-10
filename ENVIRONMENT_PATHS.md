# InvoiceSystem 本机环境路径

更新时间：2026-10-09

## 报销状态与反选验证

- 状态配色统一沿用本节 Windows 构建、Playwright 和本地前端镜像环境，无新增依赖。
- Windows Node.js：`C:\Program Files\nodejs\node.exe`；在 `E:\Projects\InvoiceSystem\invoice_system\frontend` 执行 `npm run build`，沿用 `frontend/node_modules`，未新增项目依赖。
- 浏览器隔离脚本：`tmp/reimbursement-browser/status-selection.cjs`；Playwright 依赖位于该目录的 `node_modules`，Chromium 位于 `%LOCALAPPDATA%/ms-playwright/chromium-1208/chrome-win64/chrome.exe`。
- 后端隔离脚本：`tmp/validate-rejected-status.py`，容器副本 `/tmp/validate-rejected-status.py`；通过 `invoice_backend` 的 `/usr/local/bin/python`、`PYTHONPATH=/app` 执行，依赖位于 `/usr/local/lib/python3.11/site-packages`，数据库为 SQLite 内存库。
- 本地前端镜像使用 `tmp/reimbursement-runtime/Dockerfile` 打包 Windows 构建产物；镜像名 `invoice_system-frontend-local:latest`。验证脚本和运行时构建目录均受 `tmp/` 忽略规则保护。

## 报销单入库与金额反推

- 报销单正式文件目录：`/app/storage/reimbursement_reports/<user_id>/`，宿主机对应 `E:\InvoiceStorage\storage\reimbursement_reports\<user_id>\`。
- 临时识别文件目录：`/app/storage/temp/reimbursements/<user_id>/`；入库成功后转移，任务失败或超时后清理。
- 新增数据表：`reimbursement_reports`、`reimbursement_report_invoices`；应用启动时由 `Base.metadata.create_all` 补齐本地数据库表。
- 金额反推在后端以整数分做 0/1 DP，状态超过 250,000 时拒绝继续扩张，避免异常金额组合耗尽内存。

## 报销单匹配运行环境

- 后端与 Celery 使用本地构建镜像 `ghcr.io/ke4king/invoice_system-backend:latest`，构建上下文为 `backend/`；镜像内安装 `tesseract-ocr` 和 `tesseract-ocr-eng`。
- 票号识别只使用英文数字 Tesseract 模型，运行目录为 `/usr/share/tesseract-ocr/5/tessdata`；临时报销单目录为 `/app/storage/temp/reimbursements/<user_id>/`。
- 识别后台任务为 `app.workers.reimbursement_tasks.recognize_reimbursement_numbers`，Celery worker 与 API 使用同一代码挂载和镜像。
- 本地浏览器交互检查使用 Windows Playwright Chromium，隔离脚本位于 `tmp/reimbursement-browser/check.cjs`，截图位于同一 Git 忽略目录。

## 报销单提取原型环境

- WSL Kali：`/usr/bin/python3`，Pillow 12.1.1 与 pikepdf 10.5.0 位于 `/usr/lib/python3/dist-packages`。
- Poppler：`/usr/bin/pdfinfo`、`/usr/bin/pdffonts`、`/usr/bin/pdftotext`、`/usr/bin/pdftoppm`；PDF 结构辅助工具 `/usr/bin/mutool`。
- OCR：`/usr/bin/tesseract` 5.5.0；中文和英文模型目录 `/usr/share/tesseract-ocr/5/tessdata`。
- 提取程序：`scripts/extract_reimbursement.py`；样本结果、切图和本机校对脚本只存放于 Git 忽略目录 `tmp/reimbursement-analysis/`。
- 未新增安装包、未调用外部 API、未修改真实发票记录。

## 链接上传验证环境

- 前端构建使用 Windows Node.js/npm，依赖位于 `E:\Projects\InvoiceSystem\invoice_system\frontend\node_modules`，产物位于同目录下 `dist`。
- 后端测试使用 `invoice_backend` 内 `/usr/local/bin/python` 与 `/usr/local/lib/python3.11/site-packages`。
- 合成测试脚本：`tmp/validate-link-upload.py`、`tmp/validate-link-downloader.py`；不连接真实 OCR，不修改真实发票数据。

## 项目路径

- Windows 仓库路径：`E:\Projects\InvoiceSystem\invoice_system`
- WSL 仓库路径：`/mnt/e/Projects/InvoiceSystem/invoice_system`
- 当前本地 Compose 文件：`E:\Projects\InvoiceSystem\invoice_system\docker-compose.yml`
- 当前本地 Compose 覆盖文件：`E:\Projects\InvoiceSystem\invoice_system\docker-compose.override.yml`

## 运行入口

- 本机访问地址：`http://127.0.0.1:8080`
- 后端 API：`http://127.0.0.1:8000`
- 推荐启动目录：`E:\Projects\InvoiceSystem\invoice_system`
- 推荐启动命令：`docker compose up -d`
- 推荐停止命令：`docker compose stop`

## 数据路径

- 发票文件存储挂载：`E:\InvoiceStorage\storage`
- 后端容器内存储路径：`/app/storage`
- Docker Desktop 数据目录：`E:\DockerData`

## 当前本地容器

- `invoice_frontend`：本地构建镜像 `invoice_system-frontend-local:latest`
- `invoice_backend`：后端服务，代码挂载自 `.\backend\app`
- `invoice_celery_worker`：异步任务 worker，代码挂载自 `.\backend\app`
- `invoice_celery_beat`：定时任务调度，代码挂载自 `.\backend\app`
- `invoice_mysql`：MySQL 8.0
- `invoice_redis`：Redis 7

## 本次功能相关说明

- 前端已通过 `docker-compose.override.yml` 切换为本地构建镜像，否则 Vue 源码改动不会进入官方预构建前端镜像。
- 后端代码通过 bind mount 生效，修改 Python 代码后需要重启 `backend`、`celery_worker`、`celery_beat`。
- 新增数据库列 `invoices.reimbursement_status` 会在后端启动时自动补齐。
- 后端和 Celery 容器在 `docker-compose.override.yml` 中配置了外部 DNS：`223.5.5.5`、`119.29.29.29`，用于缓解 Docker Desktop 内部 DNS 对邮箱和百度 OCR 域名的间歇解析失败。
