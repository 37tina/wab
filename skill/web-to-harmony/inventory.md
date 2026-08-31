---
name: web-to-harmony-inventory
description: Web 应用源端理解薄壳（引用 inventory-core 九步，填四项平台差异参数：路由扫描+DOM 树枚举 surface、Playwright/CDP 运行取证、CSS 选择器+路由路径锚、Web 特有存储/网络风险面）。何时用：Web → 鸿蒙手机迁移的 Phase 2 源端理解；何时不适用：已进入 Phase 3 搭壳，或源端非 Web 应用。
---

# Web → 鸿蒙手机 源端理解（薄壳）

## 引用

- `skills/_shared/inventory-core.md` —— 九步流程 / 行为契约六要素 / 对账四态 / 防伪口径**全部继承**。
- `skills/web-to-harmony/controller.md` —— 本路径无降级声明（RUNTIME 项必须实跑）。

## 平台差异参数（填 inventory-core 的表）

| 参数 | 本路径取值 |
|---|---|
| surface 枚举工具 | **路由扫描 + DOM 树遍历**，产出必须脚本生成禁止手抄。① 路由扫描：静态扫框架路由表（React Router / Vue Router 的 routes 定义、Next/Nuxt 文件路由、Angular routes）+ 运行时补全（Playwright 启动后 `page.evaluate` 收集 `a[href]`/router-link 与实际发生的 history 路由变化，覆盖动态路由）；② DOM 树：每路由 `page.evaluate` 遍历 `document.body` 生成结构快照，按语义分类——page（路由级容器）/ sheet·dialog（`role=dialog`、fixed/overlay 弹层、modal 根节点）/ component（普通组件，**防被当独立页面**）/ viewmodel·logic（状态层：Redux/Pinia/Context 扫 store 定义）/ repository·data（fetch/axios 调用点） |
| 运行取证工具 | **Playwright（或裸 CDP）真实驱动**：`page.click`/`page.fill`/`page.keyboard` 执行契约操作序列；断言 `expect(locator)` / `waitForSelector`；截图 `page.screenshot` + trace 留痕；存储断言 `page.evaluate(() => localStorage.getItem/setItem(...))`、Cookie `context.cookies()`；网络面 `page.on('request'/'response')` 录请求对账；IndexedDB 经 CDP Storage 域或注入脚本枚举 |
| source_refs 粒度 | **CSS 选择器 + 路由路径**双锚：选择器优先 `data-testid`/`id`，退化到结构路径（如 `ul.todo-list > li:nth(0) .toggle`）；路由路径（`/login`、`#/todos`）；localStorage 键名、网络端点 URL 也是稳定锚 |
| 特有风险面 | ① **四轨存储并存**：localStorage（持久）/ sessionStorage（会话级，重启即失）/ IndexedDB（结构化大数据）/ Cookie（含会话 Cookie 过期语义）——重启语义各不相同，data-relations 必须逐轨判定；② **Service Worker**：离线缓存/推送/拦截逻辑在主线程外，迁移后 ArkWeb 能力边界 `PENDING_CONFIRM`（见 scaffold.md），先登记为独立风险面；③ **网络请求面**：XHR/fetch 端点、鉴权头、CORS 假设——目标端 ArkWeb 壳内同源策略与原生请求（HTTP API）行为不同；④ **状态管理**：store 的持久化中间件（redux-persist 等）把内存状态隐式落 localStorage，极易迁漏 |
| 静态锚点包 | 有源码时冻结：框架路由表源文件（React Router / Vue Router routes 定义、Next/Nuxt 文件路由目录、Angular routes）、入口 HTML/模板、构建配置（vite/webpack）与产物指纹。**DOM 树即 surface-index 主体**（脚本遍历产出），静态路由表只做对账分母：静态有·运行时无 → 条件路由/懒加载（注明触发条件）；运行时有·静态无 → 动态生成路由（锚定跳转来源） |

## 分级验证落地（继承九步第 5 步）

- RUNTIME 名单照常圈定（增删改 / 持久化 / 账号 / 复杂设置），本路径**全部真跑**（无降级）：每条契约留 Playwright 脚本 + 前后快照 + 断言结果。
- 纯展示 / 纯跳转 / 容器宿主（布局壳、模板组件）SOURCE_CONFIRM——源码/静态快照证据链完整即闭包，不为"被访问过"硬跑。

## 持久化面结论表（data-relations 必填）

每功能↔数据对象行须判定存储轨道并给**存在性判定锚点**：localStorage / sessionStorage（`page.evaluate` 枚举全部键 + 逐键读值，前后各一份）/ IndexedDB（库名+对象仓清单+代表性记录）/ Cookie（`context.cookies()` 清单 + 作用域与过期）/ Cache API / Service Worker 拦截范围。重启语义必须实测：关闭并新建 browser context 后重读，区分"持久"与"会话"。鸿蒙侧语义等价载体初判（ArkWeb DOM Storage 沙箱 vs 原生 Preferences）由 Phase 3/4 裁决，本阶段只记事实。

## 最小验证设想

100 行内 todo 单页应用（原生 JS + localStorage，无框架）：路由扫描产出单 page + N 个 component；≥3 条行为契约（新增/勾选完成/删除）全部 RUNTIME 实跑取证；持久化结论表判明 localStorage 键清单与重启语义；reconciliation 应全部 CONFIRMED（无 GAP）——用最小例子验证"无降级"口径与存储轨判定法真实可执行。

## 环境与工具（双平台，命令两端一致）

- 取证脚本：Node ≥18 + Playwright（`npx playwright test` 或自写 Node 脚本 `node scripts/collect.mjs`）；取证浏览器固定 chromium 并锁版本（`npx playwright install chromium`，`npx playwright --version` 记入 HENV）。
- 存储枚举：localStorage/sessionStorage 用 `page.evaluate` 全键枚举逐键读值；Cookie 用 `context.cookies()`；IndexedDB 用注入脚本 `indexedDB.databases()` 枚举库与对象仓——`PENDING_CONFIRM`：`databases()` 非标准强制项，以取证 Chromium 实测为准（不支持时退化逐库名开仓）。
- 工作区路径：Windows `D:\migrate-runs\<run-id>\`（Git Bash 加 `MSYS_NO_PATHCONV=1`）；macOS `~/migrate-runs/<run-id>/`。

## 参考（真实 URL，调研 2026-09-01）

- WHATWG DOM Standard — https://dom.spec.whatwg.org/ ；MDN DOM 入口 — https://developer.mozilla.org/en-US/docs/Web/API/Document_Object_Model
- Web Storage 规范（localStorage/sessionStorage 作用域与过期语义）— https://html.spec.whatwg.org/multipage/webstorage.html ；MDN localStorage — https://developer.mozilla.org/en-US/docs/Web/API/Window/localStorage
- IndexedDB：W3C 规范 — https://www.w3.org/TR/IndexedDB/ ；MDN — https://developer.mozilla.org/en-US/docs/Web/API/IndexedDB_API
- Chrome DevTools Protocol（Storage/DOM/Runtime 域，裸 CDP 备选通道）— https://chromedevtools.github.io/devtools-protocol/ ；Playwright 文档 — https://playwright.dev/
- TodoMVC（最小验证用 vanilla JS todo 参照）— https://todomvc.com/ ；仓库 — https://github.com/tastejs/todomvc
