---
name: verify-core
description: 双端行为差分通用内核（源端为 oracle/四维结果比对/前置对齐/操作通道重映射/有界修复回环）。所有路径 implementation.md 薄壳必须引用本文件并指定双端驱动工具；从 android 套 harmonyos-feature-implementation v5 双机差分范式平台无关化而来。
---

# 双端行为差分内核（比结果不比路径 / 修复回环）

**定位**：Phase 4 验证 = 拿同一份行为考卷（behavior-contracts），源端与目标端各答一遍，**机器判分**。源端是行为基准 **oracle**（输入指纹不变则缓存命中不重跑）；目标端是被验证方，每轮真跑。UI 与操作路径可按目标平台规范改造，但四维结果必须语义等价——阅卷的是机器不是人。

## Non-negotiable

- 继承四阶段治理铁律（模型不放行 / 机器判定 / 证据不可变 / 显式 GAP，见 controller-core）。
- **源端为 oracle，只读不动**：DIFF 一律修目标端；只有 oracle 结果本身可疑（环境/种子/指纹漂移）才强制重采并留痕，不许改源端来"凑平"。
- **比结果不比路径**：操作序列允许按范式重映射表翻译（如浏览器 `click`→鸿蒙 `tap`、edge-swipe→侧滑返回），但契约的语义断言（意图/数据变化/可见结果/重启后状态/副作用）一个字不改——改的是操作通道，不是考卷。
- **四维断言**（每条 RUNTIME 契约）：① observable（语义级文本/锚点集合，非像素）② semantic data（语义对象读写集，经**冻结的独立数据探针**出口采集，应用侧自报不算）③ persistence（冷重启后状态）④ side-effect（外部可见副作用）。数据等价在语义层（对象读写集对等），物理载体自由（Preferences vs RelationalStore 皆可，不比存储引擎与表结构）。
- **前置对齐先行**：双端先各自恢复到**同一语义前置状态**并校验 pre_state；任一侧前置无法建立 → 该契约四维一律 MANUAL 归人工队列，**不算 DIFF**（前置无法对齐 ≠ 行为差异）。
- **断言 FAIL 就是 FAIL**：数据/计算/状态断言失败不可靠解释翻转为 PASS——解释只能伴随，不能翻转。平台确实无法等价 → `PLATFORM_LIMITATION` → 人工裁决通道，且仅平台能力差异可走。
- **无公开 API 可机器对比的副作用标 MANUAL，不是 MATCH**；目标端无法执行标 PLATFORM_LIMITATION。
- 不做 UI 像素 A/B：视觉还原走独立的 visual-fidelity（视觉记忆+蓝图）验收，与行为差分互不替代（差分测试实践依据：比语义属性不比渲染细节，见参考）。
- **修复回环有界**：首轮差分有 DIFF → 机器可读修复清单 → 只修目标端 → 重放重验；**硬上限 2 轮**，round 2 仍 DIFF → `MANUAL_TAKEOVER` 转人工，不再自动重试。轮次只追加记账（哈希链防篡改），不许删证据重置计数。

## 流程（六步）

1. **消费 Gate 3 闭包产物** + 行为契约（双端步骤各自留列）；数据断言出口绑定冻结探针的 expected hash（探针本体禁改，Gate 校验哈希）。
2. **目标端按功能实现**（原生优先规约见 scaffold-core-*；自定义实现登记理由）。
3. **前置对齐**：双端冷复位 → prepare → precondition 校验；失败归 PRECONDITION_FAILED 人工队列。
4. **双端各自执行、分别采集，机器 A/B 直比四维** → dual-diff-results（verdict ∈ MATCH / DIFF / MANUAL）；退出码 0=无 DIFF / 1=有 DIFF / 2=执行受阻。oracle 侧指纹不变可缓存命中；目标端每轮真跑。
5. **DIFF 修复回环**：读修复清单 → 只修目标端 → 回第 4 步重验（轮次与上限见铁律）；全 MATCH 才放行下一步。
6. **Gate 4 判定**：① RUNTIME 功能断言全过（MANUAL 不算 PASS）② 数据对账无未解释差异 ③ PLATFORM_DEVIATION 全裁决且 FAIL 永不翻转 ④ SOURCE_CONFIRM 功能四门槛（实现存在 / 无 placeholder 桩 / 源码可追溯 / 可构建）⑤ 环境链 + 表面契约 + 视觉还原达标。PASS → CLOSED。

## DIFF 语义示例（判分口径）

- 语言/主题切换：源端实测 locale=en 且冷重启仍 en，目标端实测 zh → **DIFF 即 FAIL**，不许以"目标端默认语言不同"解释翻转。
- 持久化：源端重启后 todo 列表保留，目标端丢失 → DIFF；目标端用 Preferences 还是 RelationalStore 保存**不影响判定**（语义层对等即可）。
- observable：比语义文本集合/锚点存在性（"列表含 3 项、完成态 1 项"），不比字号/间距/滚动条。
- 副作用：源端触发网络端点 X，目标端未触发 → 需先确认目标端契约是否声明等价通道；无公开 API 可采证时该维 MANUAL（人工裁决），**绝不自动记 MATCH**。

## 平台差异参数（各路径薄壳必须填）

| 参数 | 说明 |
|---|---|
| 源端驱动与取证工具 | 真实驱动 + 四维采集的命令/脚本（如 adb+uiautomator、Playwright/CDP、XCUITest） |
| 目标端驱动工具 | hdc + uitest（arkxtest）组件树断言等 |
| 数据探针形态 | 源端与目标端各自的语义数据出口（如 DebugSemanticProbe / localStorage 读取桥） |
| 范式重映射表出处 | 操作通道翻译表的来源（各路径 scaffold.md 裁决表） |

## 环境与工具

- 目标端：DevEco 手机模拟器 + `hdc`（冷重启 `aa force-stop`/`aa start`、截图 `snapshot_display`）+ `uitest dumpLayout`（arkxtest 组件树快照，作 observable 断言源）。
- 源端工具由各路径薄壳指定；双端环境指纹均须冻结（版本/序列号/种子/视口）。

## 参考（调研来源）

- android 套 v5 出处：`skills/android-to-harmony-phone/harmonyos-feature-implementation/SKILL.md`（双机差分/oracle cache/修复回环≤2轮/dual-diff-results 语义）。
- 跨平台测试迁移综述 https://arxiv.org/pdf/2405.04480 —— 测试用例跨平台迁移按**语义锚**重映射而非原始选择器，是"操作通道重映射、语义断言不变"的依据。
- 浏览器渲染属性差分测试（Cornell softsec2024submission37）——差分比对语义属性、容忍渲染实现细节差异，是"不做 UI 像素 A/B"的依据。
- Record & Replay 教程 https://arxiv.org/pdf/2510.05480 —— 录制语义步骤并确定性重放，保证双端执行同一操作序列。

## oracle 缓存与指纹

oracle 缓存键 = 源端环境指纹（构建产物 SHA-256 + test_seed + 契约哈希 + 源端运行环境版本）。任一变 → 缓存失效强制重采并留痕（--refresh-oracle 仅此场景合法）。目标端永不缓存。

## dual-diff-results schema

每 RUNTIME 契约 × 四维（observable / data / persistence / side_effect）一格：verdict ∈ MATCH / DIFF / MANUAL / PLATFORM_LIMITATION；两侧实测值（oracle_expected / target_actual）；DIFF 格必须携带归因通道（修复回环或取证伪影定性登记），MANUAL 格必须携带人工队列原因。退出码：0=全 MATCH / 1=存在 DIFF / 2=执行受阻。

## 布局模式核对（observable 维度增补，2026-09-01）

截图对比不能只核对文字锚点——**布局模式漂移**（蓝图声明 Overlay 抽屉但实现用固定并排、bottom-nav 变成 tabs 等）在文字锚点全对的情况下仍会发生。

双机对比时必须核对**布局模式清单**：
| 模式 | 判定要点 |
|---|---|
| Overlay 抽屉/侧边栏 | 展开后**覆盖**内容区（非挤压），有开关状态（默认收起/展开） |
| 固定侧边栏 | 与内容区并排，**源端是固定才是固定**（对齐源端行为，不自作主张） |
| Bottom Navigation | 固定底部，图标+文字 tab |
| Tabs（顶/底） | 对齐源端位置与形式 |
| FAB | 悬浮按钮位置对齐源端 |

每核心页面的截图对比记录中，必须写明「布局模式：Android=X / Harmony=X，一致/不一致」。不一致且无豁免 → 表现差异项。
