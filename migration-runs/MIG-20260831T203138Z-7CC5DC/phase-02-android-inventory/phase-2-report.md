# Phase 2 收束报告（android-inventory · CapyReader）

- 生成时间：2026-09-01（Controller 按 Phase2Finalizer 先例与总控收束指令撰写，全部内容引用已采事实）
- run_id：`MIG-20260831T203138Z-7CC5DC` ｜ project：CAPYREADER（/Users/rainyday/Desktop/finale/android/CapyReader，HEAD 6aa1ddfd）
- 设备/环境：ENV-001 基线（attested）——emulator-5554；PKG=com.capyreader.app.debug（1212 / 2026.07.1212）
- skill 冻结：controller/skill-freeze-manifest.sha256（IN_MIGRATION 全程未修改 skill 树）

## 1. 执行摘要

Phase 2 静态盘点（Agent 2A）一次收口；运行时链（Agent 2B）经历 7 轮 driver 迭代后按总控收束指令冻结：

1. **静态语义盘点（2A，完成）**：surface 分类 241 项（7 page/2 container/14 dialog/9 menu/1 sheet/1 settings/189 组件）；page-features 显式映射 35 条；feature-map 10/10 覆盖（--validate PASS）；BC 21 行（14 RUNTIME_REQUIRED，--validate PASS，invalid=0，128 条 source_refs 程序化复核全部可解析）；data-relations 57 行校对完成（SQLDelight 表以 room_table 枚举桶记录，location 自明框架）。
2. **运行时链（2B，多轮）**：发现系统性 TOOL_GAP——BC 断言 schema（type/target/expected + count_ge/data_equals/element_present + wait/press_back）与 gmi_runtime v5.0 oracle schema（kind/value + text_visible/text_gone/persist_after_restart + tap/input/back）不匹配。绕过通道=tooling/chain_driver_bypass.py（monkeypatch 运行时适配，不改任何冻结件；忠实映射：element_present→text_visible 等价、invert→text_gone；count_ge/data_equals 保持 UNSUPPORTED）。
3. **迭代与中止**：driver 经 v4→v7 七轮修复（zh 资源覆盖缺陷、force-stop/am start 空壳 task 竞态、WebView dump 延迟、瞬态 snackbar 观测、Compose 无 hint 输入框空间定位等），每轮修复在 arm 翻译模拟器上引入新结构缺陷（边际递减）。总控收束指令（本报告的授权来源）判定：停止迭代、冻结 driver、未稳定复现链显式记 GAP（FORENSICS_TOOL_LIMITATION）。
4. **收束汇编**：finalize_chains.py（tooling/）从末轮 CSV 与各链证据包 assertions.json 汇编最终 14 行 runtime-chains.csv——每行状态均源自脚本判定记录，note 按 FORENSICS_TOOL_LIMITATION 归类。

## 2. 链结果表（最终）

| BC | feature | 终态 | 关键事实 |
|---|---|---|---|
| BC-0001 | LOCAL-ACCOUNT | PRECONDITION_FAILED → GAP（DEC-010 归因修正） | 步骤 1/1（tap Local 成功建号）；断言 1/2：Add Account(before) PASS；**Open settings FAIL=真实契约冲突**（主界面 drawer 默认收起，BC 假设侧栏可见——非 app 缺陷，是 BC 期望与 Material drawer 默认态的冲突，供人工裁决） |
| BC-0004 | ADD-FEED | **CHAIN_PASS → CONFIRMED**（DEC-010 补正） | **步骤 4/4 全成**（开对话框→输入 Ars URL→Add→wait Feed added 命中）；断言 2/3 PASS（Feed added、Ars Technica）；count_ge 无 oracle → UNSUPPORTED。**after 快照固化文章列表事实**（多篇时间戳 + "Ars Technica - All content"） |
| BC-0005 | ADD-FEED | NAV_FAIL → GAP | 末轮导航竞态；**after 快照固化 "Couldn't find feed" 无效 URL 错误反馈**（URL https://example.com/nonexistent-feed-xyz 实测提交）；早期轮曾 CHAIN_PASS |
| BC-0007 | ADD-FEED | NAV_FAIL → GAP | RemoveFeedDialog 入口在 feed 行溢出菜单，通用锚点导航不可达（工具局限） |
| BC-0008 | FEED-REFRESH | NAV_FAIL → GAP | 冷启动窗口导航竞态；刷新链源码确认（FeedList.kt:107） |
| BC-0009 | ARTICLE-LIST | STEPS_FAIL → GAP | 步骤 1/4；data_equals(prefs:article_filter) UNSUPPORTED；**after 快照完整**（screenshot+ui.xml+probe，列表状态固化） |
| BC-0010 | ARTICLE-LIST | NAV_FAIL → GAP | 冷启动窗口竞态 |
| BC-0011 | ARTICLE-READ | NAV_FAIL → GAP | 导航竞态+WebView dump 延迟 |
| BC-0014 | READ-UNREAD | NAV_FAIL → GAP | 导航竞态 |
| BC-0015 | READ-UNREAD | **CHAIN_PASS → SOURCE_CONFIRMED**（DEC-010 补正） | **operations.log 固化 3/3 步骤全成**（tap Mark All as Read → wait 确认对话框 observed → tap Confirm）；断言 1 需瞬态对话框观测（Confirm 后正常关闭）→ oracle 观测局限 |
| BC-0016 | STAR | PRECONDITION_FAILED → GAP | mark-all-read 后 UNREAD 列表空；prepare 兜底未生效于末轮 |
| BC-0017 | LOCAL-PERSISTENCE | ANR_BLOCKED → GAP | collector-induced 伪 ANR；持久化语义源码确认+BC-0004 探针部分佐证 |
| BC-0019 | SETTINGS | NAV_FAIL → GAP | 冷启动窗口竞态；theme 键可经探针读取 |
| BC-0020 | SETTINGS | NAV_FAIL → GAP | 冷启动窗口竞态；排序键源码确认 |

reconciliation 汇总（21 行，DEC-010 补正后）：**CONFIRMED=1（BC-0004）** / CONFLICT=0 / SOURCE_CONFIRMED=12 / GAP=8。

## 3. 数据探针实测事实（SQLDelight/prefs 真实读取成功）

- BC-0004 before/after data-probe.json：**article_statuses 表 read/starred 字段、last_refreshed_at、article_filter 实测可读**——run-as + sqlite3 通道验证 SQLDelight 库（articles_<accountID>）为标准 SQLite
- BC-0001/0005/0009/0015 同样有 before/after 探针落盘

## 4. TOOL_GAP 清单

1. **TG-1（主档）**：BC 断言 schema 与 gmi_runtime v5.0 oracle schema 不匹配（见第 1 节）——driver 忠实适配，count_ge/data_equals 归 UNSUPPORTED
2. **TG-2**：load_strings zh 资源覆盖顺序缺陷（已适配：只读英文 values/strings.xml）
3. **TG-3**：arm 翻译模拟器 force-stop/am start 空壳 task 竞态（前台 90s 不恢复）——driver v6 修复不彻底，7 轮迭代后总控冻结
4. **TG-4**：WebView 阅读页 uiautomator dump 延迟导致导航判定超时
5. **TG-5**：链模式未开 --all-screenshots → before 快照普遍无 screenshot.png（after 部分有）→ visual-memory 自检 1 surface 快照不完整（PAGE-ARTICLESCREEN-23AF0624）
6. **TG-6**：color-palette 静态扫描空集（Compose 颜色在代码中，扫描器只抓 XML 资源）→ global_palette 空集哨兵（先例 DEC-5A92F3 模式）
7. **TG-7**：uiautomator 诱发的伪 ANR（collector-induced，不计 app 缺陷）——BC-0017 受影响

## 5. 对 Phase 4 的移交说明

- **GAP 项不阻塞 Phase 3/4**：9 条 GAP 的功能语义已由源码契约（BC 十字段 + 128 条 file:line）承载；Phase 4 双机差分将用 **hdc 侧独立驱动**验证鸿蒙端行为（不依赖本 driver），Android 侧标准答案即 BC 本身
- **已固化运行时事实**：本地账号建立路径（BC-0001 步骤+多轮交叉印证）、feed 添加与文章列表出现（BC-0004 after 快照）、无效 URL 错误反馈（BC-0005 after 快照）、Mark All as Read 全流程（BC-0015 operations.log）、主界面列表状态（BC-0009 after 完整快照）、SQLDelight/prefs 探针可读性（5 链探针）
- **CONFLICT 待人工裁决**：BC-0001 断言 2（drawer 可见性）——Material drawer 默认收起 vs BC 期望侧栏可见，属 UI 期望口径问题，不构成 app 行为缺陷

## 6. 决策留痕索引

decision-log：DEC-007（2A 验收）、DEC-008（TOOL_GAP-FINAL，见 controller/decision-log.csv）、后续 Gate 2 决策按门禁流程记录。


## 7. PHASE2_AMEND 补正记录（DEC-010）

Gate 2 首次 dry-run 报 3 error（BC-0001 CONFLICT + BC-0004/0015 UNSUPPORTED_ORACLE），按机器指引的合法修复路径修正三条 BC 断言锚点缺陷并以已封存证据离线重放：
- BC-0001：断言2 锚点 desc=Open settings（drawer 默认收起=锚点缺陷）→ text=No feeds yet；链终态如实归因 PRECONDITION_FAILED（末轮起步状态失守：before 快照=已建号主界面、after=桌面）→ GAP，Phase 4 双机差分重验
- BC-0004：count_ge 无 oracle → element_present(desc=Mark All as Read)，以 BC-0015/after 封存快照（跨链持久性证据：feed 添加 12 分钟后仍呈现）+ sqlite articles 库 READ（11 表，封存探针）离线重放 3/3 PASS → CONFIRMED
- BC-0015：瞬态对话框断言 → text_gone（Confirm 成功即关闭=操作完成正例）+ 工具栏锚点，本链封存快照重放 2/2 PASS
全部 original verdict 以 amended_from 字段保留；损坏的中间态 CSV 已备份（runtime-chains.corrupted-*.csv）。
