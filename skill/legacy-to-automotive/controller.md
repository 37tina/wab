---
name: legacy-to-automotive-controller
description: 传统桌面/嵌入式软件（C/C++/Qt/Electron/Delphi/老 Win32）迁移到鸿蒙车机（HarmonyOS 座舱）的治理薄壳。何时用：源端是传统桌面或工控软件、目标端是车机屏；何时禁用：源端是 Android/iOS/Web 或目标端是手机/平板/PC 时走对应套件。
---

# legacy-to-automotive · controller 薄壳

## 引用

- `skills/_shared/controller-core.md`（四阶段状态机/铁律/失败路由，全部继承）
- `skills/_shared/inventory-core.md`（Gate 2 判据）、`skills/_shared/scaffold-core-automotive.md`（Gate 3/4 车机判据）

## 本路径差异（controller 视角）

**源端三态必须在 Gate 1 冻结**（这是本路径最大的治理差异）：

| 源可得性 | 允许的 run 形态 |
|---|---|
| 全源码（Qt/.ui/.qrc、Win32+.rc、Delphi .dfm、Electron 工程等） | 正常四阶段 |
| 部分源码（缺模块/只有窗体资源） | 缺失模块的行为契约全记 GAP，禁止从二进制"补猜" |
| 仅二进制 | 仅限自有/获书面授权/开源许可证允许的样本；只能做黑盒运行取证 + PE 资源提取；契约来源=**契约反推**（见下），整 run 强制 `CONTRACT_INFERRED` 标记，Gate 2/4 增人工复核点；反推覆盖面不足（核心功能 LOW confidence 占比过高）→ 拒绝 run 或转 MANUAL_TAKEOVER（边界见 inventory.md） |

### 契约反推治理（仅二进制态的黑盒取证升级规则）

- 黑盒取证结论升级为行为契约时，逐条强制标注 `confidence ∈ {HIGH, MEDIUM, LOW}`：HIGH=≥3 次稳定复现且≥2 组不同输入验证；MEDIUM=单次稳定复现；LOW=一次性观察或推测。判定规则见 inventory.md。
- LOW/MEDIUM 条目**不得**作为 RUNTIME 断言依据，只能立 GAP 候选或降级 SOURCE_CONFIRM；HIGH 条目进入正常契约流但仍带 `CONTRACT_INFERRED` 痕，Gate 4 差分 verdict 须人工复核后才可判 MATCH。
- 反推契约禁止反推"为什么"（内部算法意图）——只登记可观察行为（输入→可见结果/持久化变化/副作用）。

### 源端取证不可用的降级策略（参照 ios 路径模式，三态验收）

源端本可运行但取证工具链不可得（如无 Windows 环境、GammaRay/pywinauto 均不可用）时：

1. **SOURCE_CONFIRM（有源码，静态可核）**——契约锚=源码 file:line；目标端实现后源端侧只做静态比对。
2. **GAP（既无源码又无运行取证）**——目标端照常实现并自证（车机端模拟器取证），对账状态停 `SELF_ASSERTED_ONLY`：目标端通过 ≠ 与源端等价；人工按 `APPROVED_DEVIATION` 放行或继续挂 GAP，**不许自动闭包为 CONFIRMED**。
3. 降级必须在 Gate 1 冻结批准（与 ipad_static 降级同强度）；伪降级（环境明明可用）Gate 2 驳回。

### 其他 Gate 差异

- **验收标准必须含车机安全四断言**：遮挡避让 / 行车状态管控 / 最小交互 / 音频焦点（定义见 scaffold-core-automotive.md"安全约束规约"节）。Gate 1 不冻结这四类断言的按 feature 门槛 → Gate 1 FAIL。
- **交互范式重设计裁决**：桌面交互（多级菜单/MDI/托盘/右键菜单/快捷键/键鼠精密操作）与车机差异大。允许"交互范式重设计但行为语义等价"：每项裁决记入 decision-log（feature_id + 桌面原交互 + 车机新交互 + 等价依据），裁决权在人（APPROVED_DEVIATION 通道），模型不得自决。
- **硬件依赖裁决**：源端依赖驱动/串口/USB/加密狗/定制板卡的功能，车机无对应硬件 → Gate 1 逐项裁决：平台替换（如蓝牙/网络协议替代串口）/降级（只读展示）/排除（excluded + 理由）。
- **环境冻结差异**：源端环境 = 真实 OS 版本 + 源程序构建产物指纹 + 取证工具版本；目标端环境 = DevEco Studio 版本 + **座舱模拟器实际可得性**（HarmonyOS 7.0.0 Beta1 座舱模拟器，规格与降级策略见 scaffold-core-automotive.md）。模拟器不可得不阻断 run，但行车状态类断言自动降级为 GAP 并在 Gate 报告显式呈现。
- TOOL_GAP 新增两类：源端取证工具缺失（如 GammaRay/Squish 均不可用且降级路径也失败）；座舱模拟器与官方 Mock 工具均不可得。
- **生态对照（非落点）**：AAOS 的驾驶分心优化（DO）分级制度可作管控清单的参照系（哪些功能类型该进管控清单），但四断言的判定口径一律以华为 ICS-v2 官方文档为准，禁止把 AAOS 规则当鸿蒙验收标准。

## 最小验证设想

开源 Qt Widgets 计算器（Qt 官方示例 widgets/widgets/calculator，LGPL/BSD 许可，见参考）为源端：跑一轮四阶段，验证 Gate 1 三态冻结、安全四断言进入验收标准、座舱模拟器上 HAP 启动冒烟。二进制反推链用该示例的 release 构建（自有权）演示：黑盒取证 → HIGH confidence 契约带 CONTRACT_INFERRED 痕过 Gate 2 人工复核。

## 参考（调研来源，2026-09 访问）

- 华为官方：智能座舱 2.0 文档中心（设计规范/驾驶安全管控/工具专区）https://developer.huawei.com/consumer/cn/overview/ICS-v2
- 华为官方：《智能座舱-针对多设备设计》设计指南 https://developer.huawei.com/consumer/cn/doc/design-guides/smart-cockpit-0000002045925712
- 降级模式参照：`skills/ios-to-harmony-phone/implementation.md`（SOURCE_CONFIRM/CONFIRMED/GAP 三态 + SELF_ASSERTED_ONLY 口径）
- 生态对照：Android for Cars（AAOS）文档区（驾驶分心规则/车机应用质量）https://developer.android.com/training/cars
- 源端取证工具：GammaRay https://github.com/KDAB/GammaRay ；pywinauto https://github.com/pywinauto/pywinauto
- 最小验证可跑例：Qt 官方计算器示例 https://github.com/qt/qtbase/tree/dev/examples/widgets/widgets/calculator
