# 脱胎换骨 · 软件国产化迁移工作台

> 异构软件平台 → HarmonyOS 全终端的智能迁移系统：多智能体（AgentTeam）完成软件语义理解、目标平台原生适配与双端行为验证，让迁移后的软件仍然正确工作。

[![verified](https://img.shields.io/badge/case-MiniTodo-brightgreen)](migration-runs) ![paths](https://img.shields.io/badge/skill%20paths-8-blue) ![phases](https://img.shields.io/badge/phases-4-green)

## 架构

```
浏览器 (Vite :5173)
   │  Space 工作台（常驻对话 + 任务概览 + 阶段审核页 + 双机投射）
   ▼
网关 (Node :8080)
   │  glm 推理注册自愈 · RUN 证据 API · 模拟器流转发/反控 · 镜像恢复
   ▼
CodeArts AgentKernel ── AgentTeam（glm-5.3）── skill v2 体系（8 路径 × 4 阶段）
   │
   ├─ Android 模拟器（adb / scrcpy 协议）
   └─ HarmonyOS 模拟器（hdc / uitest）
```

**四阶段流水线**（每阶段机器 Gate + 人工裁决）：

| Phase | 职责 | Gate |
|---|---|---|
| 1 基线建立 | 功能范围/迁移政策/种子/环境/输入指纹冻结 | Gate 1 |
| 2 源端理解 | 功能语义地图 + 行为契约（六要素）+ 真机取证 | Gate 2 |
| 3 目标承载 | 分面搭壳 + UI 蓝图四字段 + interface-only 数据契约 + 构建冒烟 | Gate 3 |
| 4 实现与验证 | 原生优先实现 + 双端行为差分（四维）+ 修复回环 | Gate 4 |

**已验证案例**：`migration-runs/MIG-20260831T052941Z-07D28A`（Android MiniTodo → HarmonyOS：7 功能迁移、可观察行为 5/5 MATCH、操作步骤 16/16、软件缺陷 0、Gate 4 人工裁决通过；证据链含四轮真机取证与双机对比截图）。

## 快速开始

### 1. 环境要求

- Node.js ≥ 18、Python ≥ 3.10
- DevEco Studio（含 HarmonyOS SDK / hvigor / hdc）
- Android SDK（platform-tools；可选 emulator）
- CodeArts Agent（AgentKernel）已运行

### 2. 配置（路径全部可移植，无硬编码）

```bash
cp config.example.json config.json
# 编辑 config.json：
#   skillRoot    —— skill v2 体系目录（默认 <repo>/skill）
#   runWorkspace —— 迁移 RUN 产物根目录（默认 ~/migrate-runs）
#   hdcBin / adbBin —— 双端工具链二进制路径
#   androidSerial / harmonySerial —— 模拟器序列号（默认值对多数机器直接可用）
#   wsScrcpyUrl  —— 可选：ws-scrcpy 服务地址（Android 高清反控）
```

也支持环境变量覆盖：`MIG_SKILL_ROOT / MIG_RUN_WORKSPACE / MIG_HDC_BIN / MIG_ADB_BIN / MIG_ANDROID_SERIAL / MIG_HARMONY_SERIAL / MIG_WS_SCRCPY_URL`。

**双平台工具链参考**（详见 `skill/_shared/00-CONVENTIONS.md`）：

| 项目 | Windows | macOS |
|---|---|---|
| DevEco Studio | `D:\DevEco Studio\` | `/Applications/DevEco-Studio.app/` |
| hdc | `...\toolchains\hdc.exe` | `.../toolchains/hdc` |
| hvigorw | `...\tools\hvigor\bin\hvigorw.bat` | `.../tools/hvigor/bin/hvigorw` |
| Android adb | `%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe` | `~/Library/Android/sdk/platform-tools/adb` |

### 3. 启动

```bash
# 后端网关
cd backend && npm install && npm start        # :8080

# 前端
cd web && npm install && npm run dev          # :5173

# （可选）Android 高清反控
cd tools && git clone https://github.com/NetrisTV/ws-scrcpy && cd ws-scrcpy && npm install && npm start  # :8000
```

### 4. 发起迁移

打开 `http://localhost:5173` → 新建项目：选择 **8 种源平台 × 5 种鸿蒙目标端** 之一（Android→鸿蒙手机为已验证路径），填源码路径与工作区，选择执行模型（如 `glm-5.3`）→ 启动。

## skill v2 体系（8 条迁移路径）

```
skill/
  _shared/                        # 内核（治理/理解/验证/五端型承载 + Apple 取证附录）
  android（根下完整版 5 skill）    # 已验证路径（→ 鸿蒙手机）
  ios-to-harmony-phone/           # 源端取证降级 + mac 补证闭环
  web-to-harmony/                 # DOM/CDP 取证（本机可跑不降级）
  windows-to-harmony-pc/          # UIA/FlaUI 分级取证
  mac-to-harmony-pc/              # mac 机上 AX 取证（不降级）
  tablet-to-harmony-tablet/       # 断点/一多/折叠
  watch-to-harmony-watch/         # watchOS 静态 + Wear OS 双源
  legacy-to-automotive/           # 黑盒契约反推 + 驾驶安全
```

每条路径 = 4 个薄壳（controller/inventory/scaffold/implementation，声明路径差异）+ `_shared` 内核（流程主体）。工单由 `web/src/phasePrompts.ts` 按 (源，目标) 路由自动拼装必读清单。

## 目录说明

| 目录 | 内容 |
|---|---|
| `backend/` | 网关（AgentKernel 代理、模型注册自愈、RUN 证据 API、模拟器流） |
| `web/` | Space 工作台前端 |
| `skill/` | skill v2 体系 |
| `android/MiniTodo` | 已验证案例的源工程（自研极简 Compose 待办） |
| `android/CapyReader` | 第二迁移对象（jocmp/capyreader，RSS 阅读器，保留原作者许可） |
| `migration-runs/` | RUN 产物证据（含真实取证截图；路径为本机运行时记录） |

## 声明

- 迁移证据（migration-runs）中的绝对路径为本机运行时记录，属证据数据不脱敏。
- `tools/`（ws-scrcpy 等第三方仓库）不入库。