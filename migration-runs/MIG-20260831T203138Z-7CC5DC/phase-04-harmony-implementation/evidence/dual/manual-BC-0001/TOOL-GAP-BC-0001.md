# TOOL_GAP 报告 — BC-0001 双机差分（Agent 4B / verify-exec.capy-01 / 2026-09-01）

## 机器 verdict（最终，dual-diff-results.csv）
BC-0001 四类（observable / data / persistence / side_effect）= **MANUAL**（0 MATCH / 0 DIFF / 4 MANUAL）
最终轮 note：`execution-incomplete:android: chain-not-executed`；Harmony 侧 replay_verdict=`MANUAL_VERIFY_REQUIRED`（断言解析为空）。
退出码 0（无 DIFF，非执行受阻终局）。

## TG-P4-001（主因，阻断机器判定）：BC 断言键名 "type" vs 冻结脚本消费 "kind"
- 位置：phase-02-android-inventory/behavior-contracts.csv 的 result_assertions（P2 产物，用 `"type"` 键）
  vs skill 冻结脚本 replayer.py（L381/833/896/1367：`assertion.get("kind")`）与 dual_verify.py（L303/309：`a.get("kind")`）。
- 实测证据：dry-run `text_anchors=[]`；oracle cache `anchor_assertions=[]`、`executed=false(chain-not-executed)`；
  Harmony replay `assertions=[]` → 四类 MANUAL_VERIFY_REQUIRED。
- 后果：Android oracle 无锚点链不跑；Harmony 链执行成功（tap 'Local' @(482,503)、重启 ok）但无断言可判。
  两侧均无法机器对比 → 按 skill 第 4 步口径归 MANUAL（人工队列），不算 DIFF、不触发修复回环。
- 4A 预警（harmony-steps.csv notes 之外的项目层观察）已被本轮实际运行证实。
- 处置建议（需 controller/team-leader 裁决，Agent 4B 无权改任何一方）：
  a) skill 脚本侧兼容 `"type"` 别名（改冻结脚本，需授权）；
  b) P2 产物侧键名规范化 `"kind"`（改 BC，P2 冻结需授权）；
  c) 维持 MANUAL 走 Gate 4 人工队列。
- 影响面预估：BC-0002~0021 的 result_assertions 同为 P2 产出，若同样用 "type" 键，机器差分将全部降级 MANUAL。

## TG-P4-002（调用环境坑，已规避留痕）：不可写 cwd 导致 Harmony PRECONDITION_FAILED
- 现象（第 1 轮）：`post-reset snapshot failed: ui dump stale/empty after retries` → 四类 MANUAL（precondition-unaligned:harmony）。
- 根因：replayer.ui_snapshot() 用相对路径 `replay_ui.json` 做 `hdc file recv` 本地目标；在 cwd=`/` 运行时
  hdc 报 `[Fail]Error opening file: read-only file system` 但 **exit code=0**（已实测复现）→ 本地读 OSError → 判空。
- 规避（已验证有效）：dual_verify 必须在可写 cwd（如 phase-04 workspace）运行；第 2 轮 Harmony 前置 ESTABLISHED、链全通。
- 处置建议：写入 P4 运行手册/后续 4B 轮次前置检查项；如需根治可在脚本侧 recv 前校验 cwd 可写或改用 tempdir（需授权）。

## 两侧手采证据（同口径，人工佐证材料，不替代机器 verdict）
见同目录 android-manual-chain.json / harmony-manual-chain.json（+android-coldstart-uidump.xml）。
语义对齐结论（人工口径，供 Gate 4 人工队列复核）：
- 首屏：Android（zh）「添加账号+本地(在设备上)/Feedbin/FreshRSS/Miniflux/Reader」≡ Harmony（en）「Add Account+Local(On your device)/…/Reader」
- 空态：Android「还没有订阅源」≡ Harmony「No feeds yet」（+侧栏 Feeds/Refresh all/Open settings）
- 数据：两侧均 UUID 账号 + 默认偏好 account_id + 账号偏好 source + accounts/<UUID>/ 目录
- 重启：两侧均直达主界面空态、不再出现 Add Account 首屏
- 差分点记录：source 值大小写 Android='LOCAL' vs Harmony='local'（语义等价，人工裁量）
- locale 差异：Android 设备 zh / Harmony 设备 en（锚点语义等价映射；如需逐字对齐建议统一设备语言后复测）

## oracle cache 状态
- cache 目录：evidence/oracle-cache/999c8e9f….json（bc_row_sha=fe4667aa…，seed=cold-reset-v1，apk_sha 空=弱化键）
- 第 1 轮 cache_miss 现场重采；第 2 轮 cache_hit 复用（APK/seed/BC 行未变）
- 注意：oracle 侧 chain 未执行（executed=false），cache 内 data_after/restart 为设备态 probe 读数（含此前 P2 链残留账号 83f1914d-…），
  非本轮链产物；如控制器裁决修复 TG-P4-001 后，建议 --refresh-oracle 重采。

## attempt-ledger
EXEC-DUAL-BC-0001-R0 / dual-rework-r0:BC-0001:MANUAL / chain_sha256=68f54f45…（第 1 轮已记；第 2 轮同 round 未追加）

---
# 附录 R1（任务 #18，2026-09-01 10:10-10:25）：规范化 BC 重跑结果

## 机器 verdict（--refresh-oracle 重采后，dual-diff-results.csv）
BC-0001 四类 = **4 MANUAL**（0 MATCH / 0 DIFF，退出码 0），
note=`execution-incomplete:android: chain-not-executed`。

## TG-P4-001 状态：Harmony 侧已解除
规范化副本断言被 replayer 正常解析（assertions.json 4 条：text_visible×2 + recheck×2），
Harmony 链全通：precondition=ESTABLISHED、tap 'Local' @(482,503) ok、重启 ok。

## TG-P4-003（新，Android oracle 侧阻断）：gmi_runtime UNRESOLVED_PAGE_REF
- 现象：oracle 重采（cache_miss=1）后仍 executed=false / anchor_assertions=[] / texts 空。
- 手动复现（/tmp 单行 BC + gmi_runtime --mode chain）：chain_status=UNRESOLVED_PAGE_REF，
  note=`page_ref 'PAGE-ADDACCOUNTSCREEN-6F7C29A2' not in candidate Page-ID map`。
- 根因：gmi_runtime 解析 page_ref 依赖 candidate Page-ID map 的**特定文件名/结构**；
  phase-02 candidates/ 目录（inventory.candidates.csv 等）与 feature-map.json 均含该 Page-ID，
  但 gmi_runtime 读不到（接口/文件名不匹配；手动复现 workspace 缺 feature-map 时另报降级 WARNING）。
  dual_verify._build_temp_workspace 仅 symlink `candidates` 与 `feature-map.json` 两名，
  symlink 后真实运行同样 blocked（本轮 cache 证据）。
- 影响：Android oracle 链无法执行 → 四类机器差分不可进行 → MANUAL（非 DIFF）。
- 处置建议（需 controller 裁决）：a) 核查 gmi_runtime 期望的 map 文件名并与 phase-02 产物对齐
  （提供正确 symlink 目标/别名，属调用侧可修）；b) 若 gmi_runtime 期望的 map 需重新导出，
  涉 P2/gmi 两冻结方，需授权。BC-0002~0021 同结构（均带 page_ref）预计同 blocked。

## Harmony 侧断言语义观察（供人工复核，非机器判定）
- text_visible "No feeds yet" after=PASS；recheck(restart)=PASS（持久化语义成立）
- text_visible "Add Account" after=FAIL / recheck=FAIL——DEC-010 语义中它是 **before 锚点**
  （tap Local 后理应离开 Add Account 首屏），规范化平铺为 after 断言产生**伪 FAIL**；
  结合 4B 手采证据（tap 后与重启后 Add Account 均不可见=符合 BC 语义），
  Harmony 实际行为正确，FAIL 为断言时序语义丢失所致，建议规范化映射补 before/after 时序标注
  （同样需 controller 裁决，4B 不改副本）。
- data/side_effect 两类：Harmony 侧 MANUAL_VERIFY_REQUIRED（data 走 DebugSemanticProbe 独立口径，
  机器对齐需 Android 侧链先通，见 TG-P4-003）。

## 双机收尾
Android pm clear ✓ / Harmony seed-reset ✓（无账号冷态对齐点，10:24 完成）。

---
# 附录 R2（任务 #19，2026-09-01 10:15-10:40）：适配 workspace（DEC-017）第三轮结果

## 机器 verdict（dual-diff-results.csv）
BC-0001 四类 = **4 MANUAL**（0 MATCH / 0 DIFF，退出码 0），note=execution-incomplete:android: STEPS_FAIL。

## 进展（DEC-017 适配生效，Android 链真正启动）
- feature-map RUNTIME 对齐后 select_chain_bcs 选中 BC-0001：precondition PASS、链步骤启动、
  texts_after 有机器实测（本轮为 en 首屏文本集）。
- 附带修复（4B 环境语义对齐操作，非代码改动）：Android 设备 zh→en
  （settings system_locales/locale=en-US + adb reboot 刷新 configuration；BC 锚点为英文、与 Harmony(en) 同口径）。
  修复前 tap 'text=Local' 因界面为「本地」确定性失配；修复后首屏英文形态与 Harmony 逐字一致。

## TG-P4-004（新，Android oracle steps 环节阻断）：find_click 对 Compose 列表行不可见
- 现象：STEPS_FAIL；texts_after 停留 Add Account 首屏；anchor "Add Account"=PASS（前置锚点已机器确认）、
  "No feeds yet"=FAIL（tap 未发生）。重试一次形态完全一致 → 确定性失败，非 DEC-008 arm 竞态。
- 函数级实测（gmi_runtime.find_click + 现场 uidump /tmp 样本，已归档 android-en-firstscreen-uidump.xml）：
  find_click(xml,'text=Local')=None；find_click(xml,'Local')=None；find_click(xml,'text=Add Account')=None
  —— ui_nodes() 可点击节点集合未覆盖 Compose 列表行（Local 行文本与 clickable 属性分属不同节点层，
  子串匹配 label 无命中）→ _exec_chain_step 返回 "tap target not found: 'text=Local'"。
- 影响：Android oracle 所有含 tap 列表行步骤的 BC（预计覆盖 BC-0001~0021 绝大多数交互链）无法走通 steps
  → 四类持续 MANUAL。与 P2 时期 DEC-008/TOOL_GAP-FINAL 的 driver 缺陷谱系一致（arm 模拟器+Compose 场景）。
- 处置建议（需 controller 裁决，gmi_runtime 为冻结方）：a) gmi_runtime ui_nodes/tap_targets 扩展
  Compose 语义（clickable 祖先+文本后代合并 label，或 bounds 就近匹配）；b) 若不改，则 Android oracle
  恒不可执行，双机差分四类长期 MANUAL，实质退化为「Harmony 单侧 replayer + 人工对照」模式（我 #13 手采
  证据已提供该模式的全套两侧实测）。

## 时序确认
Controller DEC-017 已确认 compare_observable 为双端可见性对比（a_vis!=h_vis 才 DIFF）——Harmony 侧
replayer 的 before 锚点伪 FAIL（Add Account after=FAIL）不进入差分判定，本轮无需处理，实测未见其泄漏进
dual-diff-results（差分从未到达比较环节，因 android executed=false）。

## data 键域对齐观察
未到达对比环节（Android 链 steps 失败 → execution-incomplete 先短路）。data_keys 中文语义键
（「账号偏好文件 account_<UUID>.xml 写入 source」等）在 oracle data probe 的 --objects 映射沿用 sqlite
对象路径（#13 cache 里 MISSING_IN_DB 两条），待链通后预计仍需交集兜底——留待链路修复后观察。

## 双机收尾
Android pm clear ✓（locale 保持 en-US——为后续 BC 批次与 Harmony(en) 同口径，是否维持请 controller 定夺）；
Harmony seed-reset ✓（无账号冷态对齐点）。
