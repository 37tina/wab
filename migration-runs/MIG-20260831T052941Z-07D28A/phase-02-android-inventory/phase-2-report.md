# Phase 2 收束报告（android-inventory · MiniTodo）

- 生成时间：2026-08-31T10:50:29Z（Phase2Finalizer / runtime-oracle-minitodo-r1，总控 task-mandate 授权）
- run_id：`MIG-20260831T052941Z-07D28A` ｜ project：MINITODO（/Users/rainyday/Desktop/finale/android/MiniTodo）
- 设备/环境：ENV-001 基线（attested 2026-08-31T06:43:49Z，status=ATTESTED）——emulator-5554
  env_id=ENV-001；PKG=com.minitodo.app，ACT=MainActivity（冷启动约 1.2s）
- skill 冻结：sha256=2bb2e587bfc86dd793b5d50e（skill 树/静态分析包全程未修改）…

## 1. 执行摘要

Phase 2 经历四轮运行时链跑 + 伪影调查 + 一次宿主中断 + 收束补正：

1. **轮1（attempt-archive/run1，14:59 归档）**：首轮链跑因执行器中断呈 STEPS_FAIL
   （6 链中 5 链 `steps interrupted`，仅 BC-0006 EMPTY-STATE CHAIN_PASS），原始记录归档留档。
2. **伪影调查（15:45-16:26）**：轮中 persist_after_restart 断言 FAIL 疑点排查——
   2b_probe_chains.py 三时点 prefs 探针（data-probe-BC-0001.json，15:50）证明 App 持久化正常；
   2b_min_repro.py 受控实验 + 2b_prefs_monitor.py 文件级追踪定位机制：gmi_runtime
   `_back_to_home` 附近机制把 todos 写成 `"[]"`，链内断言读到被清空的 prefs → FAIL 为**取证链执行器伪影**。
3. **内核中断（16:26）**：CodeArts 内核重启致 Controller 与 2B 会话中断，磁盘产物完好
   （decision `DEC-20260831T104513Z-F36130` RUN_INTERRUPTED/RECOVERED）。
4. **轮4（16:37，2B 续跑）**：最终 6 链完整跑——3 链 CHAIN_PASS，BC-0001/0002/0005
   persist_after_restart FAIL（即伪影）。轮4 结果保留，禁止重跑。
5. **2F 收束（18:31-18:47，本报告）**：按 TOOL_GAP_BYPASS 收束——BC-0002/0005 探针补采
   （一次通过）→ 三行链记录透明补正（FAIL→PASS，amended_from 保留原值，轮4 原件归档）→
   reconcile/visual-memory/phase-2-report/gmi_closure 收尾管线。

收束决策依据（decision-log）：`DEC-20260831T104513Z-B14CA7`（TOOL_GAP_BYPASS）、`DEC-20260831T104513Z-F36130`（RUN_INTERRUPTED）、`DEC-20260831T104513Z-DEB9A1`（PHASE2_AMEND）、`DEC-20260831T104745Z-5A92F3`（palette 空集哨兵）。

## 2. 链结果表（补正前后对照）

| bc_id | feature | 轮4原始（归档件） | 补正后（现行） | 补正依据 |
|---|---|---|---|---|
| BC-0001 | FEAT-TODO-ADD | CHAIN_FAIL 1/2 persist=FAIL | CHAIN_PASS 2/2 persist=PASS(amended_from=FAIL) | data-probe-BC-0001.json 三时点 |
| BC-0002 | FEAT-TODO-TOGGLE | CHAIN_FAIL 1/2 persist=FAIL | CHAIN_PASS 2/2 persist=PASS(amended_from=FAIL) | data-probe-BC-0002.json 三时点 |
| BC-0003 | FEAT-TODO-DELETE | CHAIN_PASS 1/1 persist=- | CHAIN_PASS 1/1 persist=- | —（未补正） |
| BC-0004 | FEAT-TODO-SORT | CHAIN_PASS 2/2 persist=PASS | CHAIN_PASS 2/2 persist=PASS | —（未补正） |
| BC-0005 | FEAT-TODO-PERSIST | CHAIN_FAIL 1/2 persist=FAIL | CHAIN_PASS 2/2 persist=PASS(amended_from=FAIL) | data-probe-BC-0005.json 三时点 |
| BC-0006 | FEAT-TODO-EMPTY-STATE | CHAIN_PASS 1/1 persist=- | CHAIN_PASS 1/1 persist=- | —（未补正） |

轮4 原始记录：`runtime-evidence/attempt-archive/runtime-chains.round4-original.csv`，sha256=`2aec628f6c258386a1883c0636c57578`（同目录 .sha256 文件）。BC-0003/0004/0006 未做任何修改。…

## 3. 探针三时点核对表（persist 断言补正依据）

三时点定义：① after prefs（步骤后 sleep 3 读取）② stopped-state prefs（force-stop → sleep 3，App 停止时读取，证明落盘不依赖重启回写）③ restart dump（am start → sleep 12 后锚点可见）。

| bc_id | BC.data_state_change（源码声明摘要） | ① after prefs 实测 | ② stopped prefs 实测 | ③ restart dump | 判定 |
|---|---|---|---|---|---|
| BC-0001 | todos 新增 T2A-ADD(completed=false) 写回 prefs（MainActivity.kt:97-99） | `T2A-ADD{completed=False,id=1788162575039}` | `T2A-ADD{completed=False,id=1788162575039}` | 可见 | **PASS** |
| BC-0002 | T2A-TOGGLE completed false→true 写回 prefs（MainActivity.kt:115-117） | `T2A-TOGGLE{completed=True,id=1788172911371}` | `T2A-TOGGLE{completed=True,id=1788172911371}` | 可见 | **PASS** |
| BC-0005 | todos 新增 T2A-PERSIST 写回 prefs；重启后 loadTodos 完整恢复（:42-53） | `T2A-PERSIST{completed=False,id=1788172986734}` | `T2A-PERSIST{completed=False,id=1788172986734}` | 可见 | **PASS** |

全称原文证据：`runtime-evidence/data-probe-BC-0001.json`（2B 采集）、`data-probe-BC-0002.json` / `data-probe-BC-0005.json`（2F 补采，含逐命令记录与三时点 prefs 原文）。

## 4. Reconciliation 统计

| verdict | 数量 |
|---|---|
| CONFIRMED | 6 |
| CONFLICT | 0 |
| SOURCE_CONFIRMED | 1 |
| GAP | 0 |

计 7 行（BC-0001..BC-0007）：6 条 RUNTIME 链全 CONFIRMED（其中 BC-0001/0002/0005 persist 维度按 TOOL_GAP_BYPASS 补正），BC-0007 FEAT-INPUT-GUARD SOURCE_CONFIRMED（确定性防御分支，MainActivity.kt:94-95，运行时表现并入 ADD 链）。退出码 0（无 CONFLICT）。

## 5. TOOL_GAP 清单

| # | gap | 定性 | 处置（decision） |
|---|---|---|---|
| 1 | validate_static_analysis.py truthiness 判空（assets=[] 误判缺失） | 2A 断点1 | 空集哨兵 NONE_FOUND + manifest 重算（`DEC-20260831T062415Z-E0C88A`） |
| 2 | feature_map.py 单值 dict 映射覆盖 + data-relations 误报 | 2A 断点2 | LLM 分片填充 + data-relations 重写 17 行 0 UNKNOWN（`DEC-20260831T062415Z-613FCB`） |
| 3 | gmi.py 重跑覆盖 phase-manifest 字段 | 2A 断点3 | 记录性纪律：禁重跑 gmi.py/analyze_static_pages.py（`DEC-20260831T062415Z-37EE2A`） |
| 4 | fill_field 留白机制（BC/feature-map 字段由 LLM 分片填充，非确定性产出） | 设计内留白 | 全部过 --validate 收口（PHASE2_HANDOFF `DEC-20260831T062415Z-4D8941` 三项 exit=0） |
| 5 | forensics-executor：gmi_runtime `_back_to_home` 附近机制把 todos 写成 "[]" → persist 断言伪影 FAIL | 取证链执行器缺陷（App 行为正常） | TOOL_GAP_BYPASS：persist 断言依据改为 prefs 探针三时点；链记录透明补正（`DEC-20260831T104513Z-B14CA7` / `DEC-20260831T104513Z-DEB9A1`） |
| 6 | CodeArts 内核重启（16:26）致 Controller/2B 中断 | 宿主环境事件 | RUN_INTERRUPTED/RECOVERED，产物完好按 task-mandate 收束（`DEC-20260831T104513Z-F36130`） |
| 7 | visual_memory global_palette 空集（纯 Compose 无自定义色板） | 校验器边界（同断点1 类） | color-palette 候选表 NONE_FOUND 哨兵行（无 hex，不编造色值）+ manifest 重算（`DEC-20260831T104745Z-5A92F3`） |

## 6. GAP 清单

- reconciliation GAP = 0（无未跑/未映射功能）。
- 遗留观察（非 GAP）：forensics-executor 修复前，persist_after_restart 断言的运行时依据为 prefs 探针三时点数据（TOOL_GAP_BYPASS 路径），gmi_runtime 链式断言不复用为 persist 依据。
- Phase 3 主题基线：源码零自定义色板（material3 默认），见 CAND-CP-0001 哨兵行。

## 7. Evidence 索引

| 产物 | 路径 |
|---|---|
| 链记录（补正后） | `runtime-evidence/runtime-chains.csv` |
| 轮4 原始链记录（归档） | `runtime-evidence/attempt-archive/runtime-chains.round4-original.csv (+.sha256)` |
| 轮1 归档（中断实验） | `runtime-evidence/attempt-archive/run1/` |
| 探针证据 ×3 | `runtime-evidence/data-probe-BC-0001.json / BC-0002 / BC-0005` |
| 链快照 ×6 | `runtime-evidence/evidence/chains/BC-0001..BC-0006/` |
| 对账结果 | `reconciliation.csv` |
| 视觉记忆 | `visual-memory.json` |
| 闭包 | `phase-2-closure.json` |
| 环境认证 | `environment-attestations/ENV-001.json` |
| 决策日志 | `../controller/decision-log.csv（15 笔）` |
| 2F 辅助脚本 | `../tools/2f_probe.py / 2f_amend_chains.py / 2f_append_decisions.py / 2f_fill_palette_sentinel.py / 2f_report.py` |

----
*本报告由 tools/2f_report.py 生成；补正过程透明可溯（archived sha256 见上）。*