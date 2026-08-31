---
name: web-to-harmony-implementation
description: Web → 鸿蒙手机 Phase 4 实现与双端差分薄壳（引用 verify-core 四维差分内核：源端 Playwright 重放契约序列采四维证据，目标端 DevEco 手机模拟器 hdc+uitest 驱动，DOM 断言与 ArkUI 组件树断言按语义锚对齐）。何时用：Gate 3 闭包后的功能实现与双端差分；何时不适用：Phase 1-3。
---

# Web → 鸿蒙手机 实现与双端差分（薄壳）

## 引用

- `skills/_shared/verify-core.md` —— 双端行为差分四维 + 修复回环通用内核（oracle / 比结果不比路径 / 前置对齐 / ≤2 轮），**全部继承**。
- `skills/_shared/controller-core.md` —— 等价契约与失败路由。
- `skills/web-to-harmony/scaffold.md` —— ArkWeb vs ArkUI 承载裁决（差分时按 carrier 分流）。

## 本路径差异：双端驱动与语义对齐

### 源端（oracle）：Playwright 重放

- 按行为契约把操作序列落成**可重放脚本**（语义步骤 = 选择器 + 动作 + 断言，录制-重放思想借鉴 https://arxiv.org/pdf/2510.05480 ），重放确定性由等待条件（`waitForSelector`）保证。
- 四维采集：observable = locator 断言 + 截图；semantic data = `page.evaluate` 读 localStorage/内存 store；persistence = 关闭并新建 context（等价冷重启）后重读；side-effect = `page.on('request'/'response')` 网络对账 + 存储键 diff。
- 源端 Web 资产指纹（URL/构建产物）冻结为 oracle 输入，缓存命中不重跑（verify-core 第 4 步）。

### 目标端：DevEco 手机模拟器 + hdc + uitest（arkxtest）

- 驱动：`uitest` 组件树快照（dumpLayout）+ `Driver` 点击/输入；冷重启 `hdc shell aa force-stop` + `aa start` + 前台校验；截图 `hdc shell snapshot_display`。
- 数据断言出口：原生重写面走冻结的独立数据探针（读 data-contracts 落点，应用自报不算）；ArkWeb 壳面经 `runJavaScript` 桥读 DOM Storage/页面状态——探针脚本哈希随工单冻结。

### DOM 断言 ↔ ArkUI 组件树断言的语义对齐法

不做逐 DOM 节点找逐组件等价，按**语义锚映射表**对齐（每条契约一张，Phase 4 冻结）：源端锚 = CSS 选择器（data-testid/文本）+ localStorage 键；目标端锚 = uitest 可定位的组件属性（id/key/text）；文本类断言直接比规范化文本。**操作通道允许重映射，语义断言不变**（依据跨平台测试迁移综述的"按语义锚而非原始选择器迁移用例"，https://arxiv.org/pdf/2405.04480 ）。层级映射思想同 scaffold.md 引用的 Android→iOS UI 迁移论文（https://arxiv.org/html/2409.16656v1 ）。

### 承载分流的验证差异

- **ArkWeb 壳页**：双端跑同一 Web 资产，observable 近似"同源自比"——只断言语义文本集合与关键锚，**接受渲染级细微偏差**（字体/滚动条/间距，差分口径依据浏览器渲染属性差分测试 Cornell softsec2024submission37：比语义属性不比渲染细节）；data 维可对键值直比（源端浏览器 localStorage ↔ 目标端 ArkWeb 沙箱 DOM Storage，键集合与值须一致）。
- **ArkUI 重写页**：四维全走语义对齐（组件树断言 + 原生数据探针 + 冷重启 + 副作用对账）。

### 浏览器与鸿蒙差异大时的修复策略

DIFF 先三分类（都只动目标端或映射，不动 oracle）：① 操作通道没重映射对（hover/右键/浏览器快捷键等无鸿蒙直对应）→ 修映射表或标 PLATFORM_LIMITATION 走人工；② 探针/桥没接线 → 修探针；③ 真行为差异 → 修目标端实现。每修一轮重放重验，≤2 轮仍 DIFF → MANUAL_TAKEOVER（verify-core 铁律）。**禁止改源端 Web 资产凑平**——源端是 oracle。

### 环境与工具（双平台，命令两端一致）

- 源端：Node ≥18 + Playwright（重放脚本 `node replay.mjs` 或 `npx playwright test`；trace zip/截图哈希随工单冻结）；工作区 Windows `D:\migrate-runs\<run-id>\`（Git Bash 加 `MSYS_NO_PATHCONV=1`）/ macOS `~/migrate-runs/<run-id>/`。
- 目标端：DevEco 手机模拟器 + hdc——Windows `D:\DevEco Studio\sdk\default\openharmony\toolchains\hdc.exe`；macOS `/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/toolchains/hdc`；命令参数两端一致（`install`/`aa start`/`aa force-stop`/`uitest`/`snapshot_display`，总表见 `skills/_shared/00-CONVENTIONS.md`）。

## 参考（真实 URL，调研 2026-09-01）

- Playwright（trace/断言/connectOverCDP）— https://playwright.dev/ ；Chrome DevTools Protocol — https://chromedevtools.github.io/devtools-protocol/
- @ohos.uitest — https://developer.huawei.com/consumer/cn/doc/harmonyos-references/js-apis-uitest ；arkxtest/hypium — https://gitee.com/openharmony/testfwk_arkxtest
- 跨平台测试迁移综述（语义锚法，正文已引）— https://arxiv.org/pdf/2405.04480 ；录制-重放（正文已引）— https://arxiv.org/pdf/2510.05480 ；浏览器渲染属性差分（Cornell softsec2024submission37，正文已引）；Android→iOS UI 迁移 — https://arxiv.org/html/2409.16656v1
- TodoMVC（最小验证对象）— https://todomvc.com/

## 最小验证设想

todo 单页应用：契约"新增 todo → localStorage 持久 → 冷重启仍在"双端各跑——源端 Playwright 脚本（click/fill/evaluate 读键）对目标端 uitest 驱动 + 数据探针读原生落点，dual-diff 判 MATCH；再故意在目标端漏写持久化，验证差分能捕获 DIFF 且一轮修复后收敛。
