# Skill 撰写规范（子代理必读）

## 目标体系

任意源平台 → 鸿蒙多终端的迁移技能库，路径成套目录 + `_shared/` 共享内核：

```
skills/
  _shared/                          # 内核（内容主体，认真写）
    controller-core.md              # 通用治理：冻结/Gate 1-4/人工审核/TOOL_GAP
    inventory-core.md               # 源端理解方法论：功能地图/行为契约六要素/分级验证/对账四态
    scaffold-core-{phone|tablet|pc|automotive|watch}.md
    verify-core.md                  # 双端行为差分四维 + 修复回环
  <path>/                           # 8 套薄壳（每套 4 个文件，30-60 行）
    controller.md / inventory.md / scaffold.md / implementation.md
```

8 条路径：android-to-harmony-phone（已有完整版，参考其结构）、ios-to-harmony-phone、web-to-harmony、windows-to-harmony-pc、mac-to-harmony-pc、legacy-to-automotive、tablet-to-harmony-tablet、watch-to-harmony-watch。

## 撰写前必须做的调研（不许凭记忆编）

1. **官方文档优先**：华为开发者联盟（developer.huawei.com）对应终端的开发指南——ArkUI 多设备形态（phone/tablet/PC/车机/手表）、窗口与折叠适配、DevEco 对应模拟器能力；源平台侧的官方工具链（如 Windows 的 WinAppDriver/UI Automation、Web 的 DOM/CDP、Electron 等）
2. **现成项目/论文**：搜该方向的开源迁移工具、行为验证方案、跨端一致性论文（中英文都搜），有就引用其思路并在文末列出
3. 调研结论写进 skill 的「参考」节：真实 URL + 项目名/论文题目

## 文件规范

- 中文撰写；frontmatter 三行：name / description（一句话，含何时用何时禁用）
- 内核文件结构：**定位**（一段）→ **Non-negotiable**（铁律，继承四阶段治理：模型不放行/机器判定/证据不可变/显式 GAP）→ **流程**（编号步骤，可执行）→ **平台差异参数**（本板块涉及的）→ **环境与工具**（真实可用的命令/模拟器名）→ **参考**（调研来源）
- 薄壳文件结构：**引用**（读哪些 `_shared` 内核，给绝对路径式相对路径）→ **本路径差异**（源端特性/目标端组件映射/环境）→ **最小验证设想**（该路径能用什么真实例子验证）
- 禁止空话；每条规则可判定；不确定的事实标 `PENDING_CONFIRM`，不许虚构 API 或工具名

## 环境路径双平台对照（凡写具体路径，一律 Mac / Windows 两式并列）

所有 skill 文件提到工具链路径时，按下表给两种形式，不许只写一种；本机实际位置以 `deveco-preflight` 实测输出为准（与下表不符时以实测为准并在 HENV 冻结）：

| 项目 | Windows（实测本机） | macOS（常规安装） |
|---|---|---|
| DevEco Studio 安装目录 | `D:\DevEco Studio\`（默认 `C:\Program Files\Huawei\DevEco Studio\`） | `/Applications/DevEco-Studio.app/` |
| HarmonyOS SDK | `D:\DevEco Studio\sdk\`（环境变量 `DEVECO_SDK_HOME`） | `/Applications/DevEco-Studio.app/Contents/sdk/` |
| ArkTS d.ts 核对 | `D:\DevEco Studio\sdk\default\openharmony\ets\` | `/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/ets/` |
| hvigorw 构建 | `D:\DevEco Studio\tools\hvigor\bin\hvigorw.js`（用自带 Node：`D:\DevEco Studio\tools\node\node.exe` 调用，或 `hvigorw.bat`） | `/Applications/DevEco-Studio.app/Contents/tools/hvigor/bin/hvigorw` |
| hdc | `D:\DevEco Studio\sdk\default\openharmony\toolchains\hdc.exe` | `/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/toolchains/hdc` |
| 模拟器 CLI | `D:\DevEco Studio\tools\emulator\Emulator.exe`（`-list/-start/-imageList`） | Device Manager 内启动（CLI 形态标 `PENDING_CONFIRM`） |
| 模拟器镜像根 | `D:\hw_device\`（`.emu_config` 的 imagePath） | `~/.hw_device/`（标 `PENDING_CONFIRM`，以本机实测为准） |
| 工作区路径风格 | `D:\migrate-runs\<run-id>\`（Git Bash 下传设备路径需 `MSYS_NO_PATHCONV=1`） | `~/migrate-runs/<run-id>/` |

注意：hdc/hvigorw 的命令参数两端一致（`install`/`aa start`/`uitest`/`snapshot_display`/`assembleHap`）；差异只在可执行文件路径与 shell 转义规则（Windows 反斜杠、PowerShell 引号、Git Bash 路径转换）。


## 与网站的关系

`web/src/phasePrompts.ts` 按 (sourcePlatform, targetPlatform) 路由到对应套件目录，Phase 1-4 提示词令 Agent 先读该套件 4 个文件再执行。

## 薄壳验收清单（终检用）

1. 四文件齐（controller/inventory/scaffold/implementation），每文件 40-120 行，frontmatter 三行规范；
2. 引用节给出所引 _shared 内核的相对路径且文件真实存在；
3. 本路径差异节无空话：源端静态锚点/取证可用性与降级/组件映射/环境工具（Mac/Windows 双式）逐项可判定；
4. 调研参考节条目真实（不确定的已标 PENDING_CONFIRM 而非编造）；
5. 最小验证设想可真实执行（有具体示例工程类型与步骤）；
6. 无 TODO/FIXME 残留；与内核无重复（薄壳只写差异）。
