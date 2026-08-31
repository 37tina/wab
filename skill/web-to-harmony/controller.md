---
name: web-to-harmony-controller
description: Web 应用迁移到鸿蒙手机的治理薄壳（引用通用 controller-core；本路径源端浏览器可真实取证，不设降级，四阶段按全量真实验证口径执行）。何时用：Web 应用 → HarmonyOS 手机迁移 run 的四阶段门禁治理；何时不适用：源端非浏览器可运行的应用（如 Android/iOS 原生），或目标端非手机。
---

# Web → 鸿蒙手机 迁移控制器（薄壳）

## 引用

- `skills/_shared/controller-core.md` —— 四阶段门禁 / 人工审核 / 失败路由 / 防伪铁律**全部继承**，本文件不重复，只声明本路径差异。
- `skills/_shared/00-CONVENTIONS.md` —— 撰写与引用规范。

## 本路径差异：源端可真实取证，无降级

- 与 iOS 路径相反：源端是浏览器应用，任何机器装 Node + Playwright（或 Chrome DevTools Protocol 直连）即可真实驱动取证。**本路径不设 `SOURCE_RUNTIME_UNAVAILABLE` 降级**——Phase 2 高风险功能必须 RUNTIME 实跑闭包；跑不动是环境问题（修环境、换机器），不许降级 SOURCE_CONFIRM 补位，更不许编造 DOM/截图。
- **环境自证**：开工记录 `node -v`、`npx playwright --version`、取证浏览器内核（`page.evaluate('navigator.userAgent')`）进 HENV 冻结；源端形态（部署 URL 或本地 dev server 启动命令 + 构建产物指纹）、路由模式（history/hash）、取证视口（建议 390×844 手机视口对齐目标端）在 Gate 1 冻结。
- **真实性红线具体化**：Playwright 痕迹（脚本/trace/截图/stdout）必须真实可复放；**禁止手写 DOM 快照冒充 `page.evaluate` 采集结果**；允许与预期的措辞/布局/渲染级偏差，不允许虚构未执行的驱动步骤。
- **范围裁决提示**：浏览器特有能力（桌面通知、PWA 安装流、剪贴板、WebShare、浏览器扩展）Gate 1 逐项 included/excluded：ArkWeb 有等价能力的走等价承载，无对应的显式 PLATFORM_DEVIATION 由人工裁决，禁止静默丢弃。
- **取证通道分级（本路径特例，与"无降级"互补）**：Web 源端默认全 A 级（Playwright/CDP 可自动化）；仅两类例外——**A-D**：需第三方账号登录/短信验证码/支付验权的功能（用测试账号 + 人工一次性辅助完成登录态注入，录屏与 cookie 快照留痕，之后回归机器重放）；**A-C2**：验证码/风控人机校验本身（不可自动化 → 该子路径 TOOL_GAP + 人工裁决，不许伪造通过）。分级只切换通道，断言强度与 oracle 口径不变。
- **证据留档**：Playwright trace（trace.zip）、截图、网络录档（HAR / request-response JSON）随工单冻结，存放 `<run-id>/evidence/source/`（Windows `D:\migrate-runs\<run-id>\evidence\source\`；macOS `~/migrate-runs/<run-id>/evidence/source/`）；HAR 可用 Playwright 的网络录制能力或 CDP Network 域导出（PENDING_CONFIRM：HAR 录制对 CORS/跨源请求字段的完整性以取证 Chromium 实测为准）。
- **源端资产两种形态**：部署 URL（冻结 URL + 首屏资源指纹）或本地 dev server（冻结启动命令 + 端口 + 构建产物哈希）；仅 URL 无源码时允许以运行时 DOM 取证单通道为准（静态锚点包缺省，对账注明），不算降级。
- **目标端不豁免**：鸿蒙手机模拟器构建/安装/启动/差分与其他手机路径同标准（见 `skills/_shared/scaffold-core-phone.md`、`skills/_shared/verify-core.md`）。

## 环境与工具（双平台，命令两端一致）

- 源端取证通道（本机可跑，不降级）：Node ≥18 + Playwright，安装 `npm init playwright@latest`（或既有工程 `npm i -D @playwright/test` 后 `npx playwright install chromium`）；裸 CDP 直连为备选通道（websocket + Chrome DevTools Protocol，见参考节协议文档）。
- 环境自证命令（Gate 1 记入 HENV）：`node -v`、`npx playwright --version`、取证页 `page.evaluate('navigator.userAgent')` 输出。
- 工作区路径：Windows `D:\migrate-runs\<run-id>\`（Git Bash 下传设备路径加 `MSYS_NO_PATHCONV=1`）；macOS `~/migrate-runs/<run-id>/`。
- 目标端鸿蒙工具链（hvigorw/hdc）路径两式并列，总表见 `skills/_shared/00-CONVENTIONS.md`。

## 参考（真实 URL，调研 2026-09-01）

- Playwright 官方文档 — https://playwright.dev/ ；Chrome DevTools Protocol 协议文档 — https://chromedevtools.github.io/devtools-protocol/
- WHATWG HTML Standard·Web Storage（localStorage/sessionStorage 语义）— https://html.spec.whatwg.org/multipage/webstorage.html ；MDN DOM 入口 — https://developer.mozilla.org/en-US/docs/Web/API/Document_Object_Model
- MDN Web API 总入口（IndexedDB/Cookie/Service Worker 等语义核对）— https://developer.mozilla.org/en-US/docs/Web/API
- 鸿蒙电脑/多设备适配专题入口（本路径目标端为手机，多设备总入口备查）— https://developer.huawei.com/consumer/cn/multidevice/

## 最小验证设想

任一公开或本地 Web 应用（如 100 行内 todo 单页应用，见 `skills/web-to-harmony/inventory.md` 最小验证设想）+ 本机 Playwright：Phase 2 全部 RUNTIME 项真实取证闭包（GAP=0）；Phase 3/4 鸿蒙端按手机路径全量标准执行——验证"无降级路径"的治理口径本身可跑通。
