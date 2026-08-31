---
name: ios-to-harmony-phone-implementation
description: iOS → 鸿蒙手机 Phase 4 实现与双端差分薄壳（源端 oracle 缺失时的三态验证策略 + 用户在 mac 上补取证的对接协议）。何时用：Gate 3 闭包后的功能实现与双端差分；何时不适用：Phase 1-3。
---

# iOS → 鸿蒙手机 实现与双端差分（薄壳）

## 引用

- `skills/_shared/verify-core.md` —— 双端行为差分四维 + 修复回环通用内核。
- `skills/_shared/controller-core.md` —— 等价契约与失败路由。
- `skills/ios-to-harmony-phone/scaffold.md` —— 交互范式裁决表（本阶段差分的重放依据）。
- `skills/_shared/inventory-ios.md` §4/§6 —— mac 取证命令细节与六要素对接表。

## 本路径差异：源端 oracle 三态

Phase 4 以源端为 oracle；本路径源端证据有三种状态，验证策略不同：

| 状态 | 判据 | 差分策略 | 允许的闭包终点 | 禁止 |
|---|---|---|---|---|
| ① SOURCE_CONFIRM（静态锚点，多数功能） | 目标端契约断言全过 **且** 源码锚点（`文件:行`/sceneID）仍在冻结基线内 | DIFF 只修目标端；源码锚点漂移才回 Phase 2 | Gate 4 的 SOURCE_CONFIRM 四门槛 | 把静态锚说成"源端实测" |
| ② CONFIRMED（mac 已补运行证据） | 用户按附录 §4 产出 xcresult + 截图 + 探针读数，哈希核验入账 | 按 verify-core 四维正常差分（操作序列重放 / 前后快照 / 重启后状态 / 副作用对账），源端为完整运行 oracle | MATCH / DIFF / MANUAL | — |
| ③ GAP（无 mac，未补证，高风险持久化/账号类） | 目标端照常实现并**自证**（鸿蒙侧断言 + 模拟器取证） | 对账状态停在 `SELF_ASSERTED_ONLY`：目标端通过 ≠ 与源端等价 | 人工 `APPROVED_DEVIATION` 放行或继续挂 GAP | **自动闭包为 CONFIRMED** |

状态迁移唯一合法路径：③ → ② 必须经 mac 补证闭环（见 controller.md 六步协议），补证产物新 evidence ID + 旧记录 superseded_by，reconciliation 重算后生效。

## verify-core 平台差异参数（本路径填值）

| 参数 | 本路径取值 |
|---|---|
| 源端驱动与取证工具 | mac 补证态：`xcodebuild test`（XCUITest）+ `xcrun simctl`（launch/terminate/io screenshot/privacy/get_app_container 探针），命令细节见附录 §4 |
| 目标端驱动工具 | hdc（`aa force-stop`/`aa start` 冷重启、`snapshot_display` 截图）+ `uitest dumpLayout`（arkxtest 组件树快照，observable 断言源） |
| 数据探针形态 | 源端：`simctl get_app_container` + `plutil -p`（UserDefaults）/ `sqlite3`（Core Data）前后读数；目标端：Preferences/RelationalStore 读数（冻结探针出口，应用自报不算） |
| 范式重映射表出处 | `skills/ios-to-harmony-phone/scaffold.md` 交互范式裁决表 |

## mac 补取证对接协议（用户侧操作指引，命令细节见 `_shared/inventory-ios.md` §4）

1. **构建自证**：`xcodebuild -project X.xcodeproj -scheme X -destination 'platform=iOS Simulator,…' build` → 保存构建日志（证明源端可构建 + 环境/版本指纹）。
2. **模拟器复位**：`simctl shutdown all && simctl erase all` 后 boot 指定机型——持久化契约取证必须从冷复位态开始。
3. **行为取证**：为 GAP 名单中的行为契约编写 XCUITest（`app.buttons["id"].tap()` + `XCTAssertTrue(x.waitForExistence(timeout:))` 形态），`xcodebuild test -resultBundlePath …` → `.xcresult` 证据包。
4. **快照与探针**：`simctl io booted screenshot` 前后截图；`get_app_container` + `plutil -p` / `sqlite3` 前后读数（③数据变化/⑤重启后状态的运行侧证据）。
5. **产物回填**：按 `evidence/chains/<bc_id>/` 目录规则放入 run 证据区，登记**新 evidence ID**（旧 GAP 记录不删，标 superseded_by），附命令全文与 exit code。
6. **Agent 侧动作仅限两件**：核验产物与登记命令一致（`shasum -a 256`/`sha256sum` 哈希、时间戳）→ 重算 reconciliation（GAP→CONFIRMED 或 CONFLICT）。**Agent 不得代填、推测或转写 xcresult 内容**——读不了二进制证据包时让用户导出文本摘要（`xcrun xcresulttool get test-results summary`）后原样附上。

## 交互范式差异的重放注意（继承 scaffold.md 裁决表）

侧滑返回 / 长按 / 上下文菜单 / 半模态是本路径最高频 DIFF 来源。差分脚本的操作序列须先经"范式重映射表"翻译再重放：iOS edge-swipe-back → 鸿蒙侧滑返回；3D Touch peek → 长按；`present` 全屏 → `bindContentCover`。**语义断言不变**（回到哪个页面、编辑态是否保留、数据是否落盘）——改的是操作通道，不是行为契约。

## 最小验证设想

选 1 个 GAP 项（如 UserDefaults 持久化的设置页，HackingWithSwift 类 todo demo 即含）：无 mac 时走 SELF_ASSERTED_ONLY 流程闭环（目标端模拟器真实取证 + 状态标注，对账行不许出现 CONFIRMED 字样）；mac 补证后走 CONFIRMED 流程闭环——同一 run 内演示三态路由正确、GAP 可升级、旧记录不可变（superseded_by 链完整）。

## 参考

- 取证命令事实来源：`skills/_shared/inventory-ios.md` §4（simctl/xcodebuild/xcresulttool，子命令集 2026-09-01 实测核对）
- verify-core 差分口径与修复回环（≤2 轮）出处：`skills/_shared/verify-core.md`；跨平台测试迁移按语义锚重映射的依据 https://arxiv.org/pdf/2405.04480
- Apple XCUITest 断言语法：https://developer.apple.com/documentation/xctest/xcuiapplication
- 鸿蒙目标端驱动（arkxtest/uitest 组件树）说明入口：华为应用开发测试文档区 https://developer.huawei.com/consumer/cn/doc/ （arkxtest 专页以文档站搜索为准）
