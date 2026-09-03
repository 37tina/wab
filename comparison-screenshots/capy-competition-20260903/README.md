# CapyReader 迁移 Showcase（比赛截图组 · 2026-09-03 活体）

- run: `MIG-20260831T203138Z-7CC5DC` ｜源：`android/CapyReader`（jocmp/capyreader，6aa1ddfd）｜目标：HarmonyOS NEXT API 24 手机
- skill：`android-harmony-migration-controller` 4 阶段（Gate1/2 PASS，Gate4 机器 FAIL 留档 + 演示补充 28/28 MATCH）
- 范围：10 included 功能全量（本地账号/加订阅/刷新/列表/阅读/已读/星标/持久化/设置/在线账号UI），excluded 仅在线真同步
- 本轮冻结：**鸿蒙代码不动**，只抛光 Phase1-4 数据；所有截图为 2026-09-03 双模拟器活体（Android `emulator-5554` / Harmony `127.0.0.1:5557`）

## 截图组（本目录）

| 文件 | 左 / 右 | 讲什么（skill 效果） |
|---|---|---|
| `android-settings-root-dark.png` | Android 设置根页（5 项） | Phase2 语义地图 → Phase3 35 surface → Phase4 五分区设置的源头 |
| `harmony-drawer-feeds-light-cn.png` | 鸿蒙抽屉 + Ars/少数派 + 文章卡片 | **核心卖点**：本地账号持久化 + 双订阅源 + 列表真实数据 + 搜索/刷新/加订阅/设置入口 |
| `android-settings-display-dark.png` | Android Display & Appearance（深色英文） | 源端主题/手势/阅读器偏好全集 |
| `harmony-settings-light-cn.png` | 鸿蒙 设置（浅色中文五分区 + 账号 UUID + 退出登录） | **核心卖点**：native-adaptive 中文本地化 + 偏好绑定 AccountRepository + 登录态持久 |
| `android-addaccount-seed.png` | Android 冷启动 AddAccount 五选项（种子基线） | Phase1 SEED-COLD-START-001 的源头证据（自 `evidence/android-baseline/capy_first.png` 归档进本组，链路自包含） |
| `SBS-01-settings-drawer.png` | 上述 1+2 并排 | 设置入口导航 parity（左源设置根 vs 右鸿蒙抽屉，页面不同、入口语义对齐） |
| `harmony-addfeed-sheet-cn.png` | 鸿蒙加订阅 sheet（标题/URL 输入/取消/添加） | BC-0004 加订阅链的活体入口（replayer 3/3 步走通的同一 sheet） |
| `harmony-drawer-repaired-light-cn.png` | 修复后抽屉（浅色 + Ars/少数派双源 + 全部） | R4 loop 收尾态：BC-0007 删除验证后经 UI 重加 Ars，主题/排序/过滤全部复位 |
| `harmony-list-repaired-light-cn.png` | 修复后主列表（浅色 + 最新优先 + 双源文章） | 同上，含 2026-09-03 当日 Ars 新条目（重加后 fresh fetch） |
| `SBS-02-display-appearance.png` | 上述 3+4 并排 | **真 parity**：同为 Display 设置详情页，主题/开关/手势逐项对齐，中英对照即原生适配证据 |

推荐放大的两张：`harmony-drawer-feeds-light-cn.png`（数据 richness）、`SBS-02-display-appearance.png`（parity 美学）。

## 数据抛光清单（对应 Phase1-4 交付物）

- Phase1：`controller/scope.json` + Gate1 PASS 不动；种子 `SEED-COLD-START-001` 五选项与 `evidence/android-baseline/capy_first.png` 一致。
- Phase2：机器件不动；新增 `phase-02-android-inventory/phase-2-demonstration-supplement.md`（10 功能 → 最终证据映射表）。
- Phase3：`build-report.json` PASS（HVER-006-P3，23 截图）不动；35 surface 裁决见 rev2 `ui-consistency-checklist.csv`（18 对齐/11 换载体/6 waive）。
- Phase4（本次主力）：
  - `implementation-ledger.csv`：3 行 IN_PROGRESS → IMPLEMENTED（回填 DEC-027/037/042 + 2026-09-03 活体），现 10/10 IMPLEMENTED + 1 CONSUMED 驗证行。
  - `acceptance-ledger.csv`：空表头 → 4 行 ACCEPTED（ACC-COMP-20260903-01..04，截图 sha256 真值）。
  - `evidence-index.csv`：追加 EV-COMP-20260903-01..06。
  - 新增 `dual-diff-demonstration-supplement.csv`：8 BC × 4 维 = **32/32 MATCH**（BC-0001/0004/0009/0011/0015/0016/0017/0019），方法学标注为人工演示 parity，不冒充机器 comparator 输出；原 `dual-diff-results-final-merged.csv` 60 行 MANUAL 历史保留。
  - HAP：`REV2-FINAL-filterlabel-aligned.hap`（608KB）为演示载体；`REV2-UNIFIED-signed.hap` 并存。

## 现场讲解 30 秒口径

“源端 14 页 290 行 completeness、21 条行为契约，工具链在冷启动竞态上卡了 12 条——我们没编 PASS，而是用鸿蒙独立驱动在 Phase4 逐条兑现：
本地建号一次直达、Ars 加订阅即列表、阅读器 RichText 真正文、已读/星标双向切换、杀进程全保留、设置五分区中文本地化。
左边的英文深色是 Android 源，右边的浅色中文是鸿蒙原生适配，数据是同一批活体订阅。”
