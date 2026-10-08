# 上传页通过链接添加发票

上传页支持粘贴一个或多个公网 HTTP(S) PDF 下载链接，每行一个，每批最多 20 个，重复链接自动合并。浏览器逐条提交，某条失败不阻止后续提交。下载、重复、OCR 处理及非发票结果复用右侧上传记录。离开页面停止后续提交，已受理的导入仍继续执行。

后端 `POST /api/v1/invoices/upload-link` 接收 `{ "url": "https://example.com/invoice.pdf" }`，要求登录。文件通过 PDF 魔数及现有发票预判后复用本地上传接口的用户隔离、文件去重、存储和 OCR 分发逻辑。不是网页抓取入口；需要登录的网站或返回 HTML 的链接会失败。重复文件返回 409 和已有发票 ID。

共用下载器逐跳校验公网地址，固定连接至校验后的 IP，同时保留原域名的 HTTPS 证书验证与 Host，避免 DNS 重绑定。签名查询参数不改写。保持文件大小和重定向次数限制，加入 45 秒下载检查期限，网络读取另受连接及读取超时限制。响应和连接池始终关闭。不保存链接到发票字段或上传记录，不在下载错误响应中回显签名地址。

## 验证

- Windows 下 `npm run build`：Vue TypeScript 检查及 Vite 构建通过。现有 CJS 和大 chunk 警告不影响构建。
- 容器内合成输入测试：成功转交上传、文件名清理、流关闭、HTML/非发票拒绝、重复响应、下载错误脱敏通过。
- Mock HTTP/DNS 测试：IP 固定、HTTPS 域名校验参数、签名查询保留、DNS 重绑定拒绝、内网重定向拒绝、超限响应和连接清理通过。
- 测试不访问真实发票链接、不写真实业务数据库、不调用真实 OCR；未进行登录后的浏览器交互实测。

## 环境

前端使用 Windows Node.js/npm 和 `frontend/node_modules`，输出 `frontend/dist`；后端隔离检查使用容器 `/usr/local/bin/python` 和 `/usr/local/lib/python3.11/site-packages`。未添加包依赖。隔离脚本位于 Git 忽略的 `tmp/validate-link-upload.py` 和 `tmp/validate-link-downloader.py`。
