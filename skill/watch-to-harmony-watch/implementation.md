---
name: watch-to-harmony-watch-implementation
description: watchOS/Wear OS→鸿蒙手表 Phase 4 实现与差分薄壳：目标端手表模拟器真实运行取证、静态契约（watchOS）或运行 oracle（Wear OS）两种差分口径、无法等价项（触觉/联动/复杂功能/Tile）的人工裁决通道。当且仅当 Gate 3 PASS 后使用；禁止绕过差分直接宣称完成。
---

# watch-to-harmony-watch 实现与验证（薄壳）

## 引用

- `skills/_shared/verify-core.md`（双端行为差分四维 + 修复回环通用内核；源端 oracle/前置对齐/比结果不比路径全部继承）
- `skills/_shared/controller-core.md`（等价契约与失败路由）
- `skills/_shared/scaffold-core-watch.md`（环境与工具：模拟器/hdc/Previewer、交互 API 细节、性能预算）

## 本路径差异

### 目标端验证：手表模拟器真实运行取证（基线，不可豁免）

- 载体：DevEco 手表本地模拟器（Device Manager > Local Emulator > Wearable）优先；Previewer 仅兜底且降级记录；真机 WATCH 5（Wi-Fi HDC）可选增强。
- 取证链（每条 RUNTIME 断言）：`hvigorw assembleHap` 构建输出 → `hdc list targets` 设备在册 → 安装/启动（`hdc install` / `hdc shell aa start`，以本机实际输出为准）→ 操作序列执行 → 前后状态截图（`hdc shell snapshot_display` + `hdc file recv`，工具缺失记 `TOOL_GAP` 不许伪造）。可执行文件路径双平台（Windows `D:\DevEco Studio\tools\hvigor\bin\hvigorw.bat` + `...\toolchains\hdc.exe`；macOS `/Applications/DevEco-Studio.app/Contents/tools/hvigor/bin/hvigorw` + `.../Contents/sdk/default/openharmony/toolchains/hdc`；总表见 `_shared/00-CONVENTIONS.md`）。
- 圆屏适配验证：截图必须过"圆屏三查"——四角无截断内容、列表沿弧形排布（ArcList 上下边缘自动缩放可见）、触达元素在安全区内。
- 交互重映射验证：表冠语义=内置默认响应（如 ArcList 滚动）可由前后截图差分证实；自处理 `onDigitalCrown` 须有事件日志（degree/action 落盘）。**模拟器表冠输入是否可触发 PENDING_CONFIRM**——先探测，不可用则降级为"代码审查 + Previewer 静态验证 + 真机待测"并记 GAP。
- 振动映射验证：`@ohos.vibrator` 调用成功即记"已触发"，触觉质感差异进裁决记录（模拟器无法证实体感）。

### 差分口径（按 source_profile 分派）

- **watchos_static（源端静态 oracle）**：源端无运行，断言 oracle = Phase 2 行为契约文本（双静态锚：源码 file:line + Apple 官方文档语义）；目标端执行结果与契约文本逐条判定，不与"想象中的 watchOS 行为"比对。
- **wearos_runtime（源端运行 oracle，标准差分）**：Wear OS AVD 上用 adb（`input tap/swipe` + `uiautomator dump` + `screencap`）重放同一契约操作序列，采集四维证据作 oracle；目标端按 verify-core 四维直比。旋转边圈注入不可得（PENDING_CONFIRM 项实测落定）时，滚动类操作双端统一降级为 swipe 通道重放（操作通道重映射，语义断言不变）。
- 数据对账（两源同）：手表端本地持久化（如 Preferences/RelationalStore 在穿戴形态的可用性，PENDING_CONFIRM 项以实测落定）与源端（UserDefaults/App Group/HealthKit 或 DataStore/SharedPreferences）按语义对象对账，差异必须可解释。

### 无法等价项的人工裁决通道（PLATFORM_DEVIATION 落地）

- 进入条件（五类，定义见 controller.md 薄壳）：复杂功能/表盘（Complication）、Wear OS Tile、细粒度触觉、手机联动通道（WCSession 五通道 / DataLayer 客户端）、体能训练后台语义。
- 流程：Phase 4 实现中发现无法等价 → 立 deviation 工单（feature_id / 源端语义 / 目标端替代 / 用户可感知差异 / 建议处置）→ **退出自动修复回环**（不消耗 2 轮重试额度，不算 DIFF FAIL）→ controller `WAITING_HUMAN_REVIEW` → 人裁决 `APPROVED_DEVIATION`（留痕入 deviation-registry，从 DIFF 清单移出）或 `REWORK`/`MANUAL_TAKEOVER`。
- 铁律：裁决前该 feature 记 GAP 挂起；禁止实现侧自行选择"最接近的行为"却不上工单；禁止以裁决通道逃避可实现项（可实现的等价项被塞进裁决 = 审核驳回）。

### 性能预算复核（实现侧补充）

- 长列表实现必须保留壳阶段的 `LazyForEach`+`cachedCount` 决策；差分轮发现滚动卡顿/启动拖沓等可观测劣化，登入修复清单按普通 DIFF 处理（不设编造的数值线，以源端体感档位与官方门槛核实后为准）。

## 最小验证设想

watchos_static：承接 scaffold 薄壳的最小骨架，实现一个完整行为链（如：列表选择 → 详情页状态变更 → 重启模拟器后状态仍在）并在手表模拟器上完成全取证链；同时对触觉或手机联动任造一条 PLATFORM_DEVIATION 工单走人工裁决——验证"模拟器真实取证 + 裁决通道"双机制可运转。wearos_runtime：以 wear-os-samples 的列表类示例为源端 oracle（AVD 取证），对同一条"列表选择→详情→重启保持"契约做双端标准差分（四维直比 + 修复回环演示一轮）。

## 参考（调研来源，2026-09 访问）

- 内核：`skills/_shared/verify-core.md`（四维差分/前置对齐/有界回环）、`skills/_shared/scaffold-core-watch.md`（取证链命令/圆屏三查/性能预算）
- 华为官方：snapshot_display 等 hdc 工具链口径见 `_shared/00-CONVENTIONS.md`；Wear Engine Kit（模板化通知替代载体）https://developer.huawei.com/consumer/cn/sdk/wear-engine-kit/
- Wear OS 官方：在模拟器上测试 https://developer.android.com/training/wearables （文档区"previewing/testing"，标题以页面为准）；adb 用户指南 https://developer.android.com/tools/adb
- 开源最小验证例：twostraws/watchOS https://github.com/twostraws/watchOS ；android/wear-os-samples https://github.com/android/wear-os-samples
