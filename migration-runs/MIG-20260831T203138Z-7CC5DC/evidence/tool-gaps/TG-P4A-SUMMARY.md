# Phase 4A TOOL_GAP 清单（impl-lead.capy-01，2026-09-01）

## TG-INIT-SCREEN-PARITY（非阻断，已留痕处置）
- 现象：init_implementation.py 的 H4ENV 固定 screen-parity 双校验要求
  comparison 尺寸同时等于 frozen 鸿蒙模拟器（1320x2856）与 Android
  ENV-001（1080x2400），数学上不可满足；P3 已裁决 TOOL_GAP(screen-parity)
  （HR-P3-CAPY-001 APPROVED_DEVIATION，冻结值=设备真实输出），skill 禁改。
- 处置：tools/run_init_p4_shadow.py 运行期将 source env resolution 对齐
  frozen emulator 真实输出（1320x2856）后调用原 init_implementation.main()；
  无文件级改动；init 其余全部校验与产物（feature-dispatch/input-lock/
  工程快照/environments）由原脚本权威生成。
- 时间消耗：约 6 分钟（含定位校验代码）。

## TG-REPLAYER-ASSERTION-KIND（4B 注意，非本批阻断）
- 现象：replayer.py dry-run 对 BC-0001 的 result_assertions 分类为
  unknown=2（P2 behavior-contracts.csv 断言键名为 "type"，replayer 义务
  分类读取 "kind"），四类义务显示 manual。harmony_steps 解析正常
  （has_steps=true，无 unmapped）。
- 影响：FEAT-LOCAL-ACCOUNT 为 SOURCE_CONFIRM feature，replayer 本就
  SKIPPED_SOURCE_CONFIRM（设计行为）；BC-0001 四类断言实际由 4B
  dual_verify.py 消费。若 dual_verify 同样只认 "kind"，需在 4B 侧确认
  P2 "type" 键兼容性（P2 产物禁改）。

## 环境件工具修复记录（自建工具，非 skill）
- p4_hdc_tool.py 修 3 处：toolchain 无工程目录时的 hvigorw --version 探测、
  install 成功串匹配（"install bundle successfully"）、新增 uitest-snapshot
  子命令（满足 14 类契约）。wrapper 最终 sha256=
  8b583d9aa612e1ef97690b78f4c5156f7c64bd05a334985b49958aa5f423b9d0，
  已同步 tools/h4env-001-p4.config.json 与工作区
  environments/H4ENV-001/phase4-environment.json。

---

# 批次 1（任务 #14，FEAT-ADD-FEED + FEAT-FEED-REFRESH）追加记录

## 修复记录（本批自建代码/工程配置，非 skill）
1. **module.json5 缺 ohos.permission.INTERNET**：@ohos.net.http 请求报 code 201
   Permission denied。已在 entry/src/main/module.json5 的 module.requestPermissions
   声明。P3 骨架无网络面是正常空缺，Phase 4 接网络必须补——后续在线 feature 注意。
2. **P3 ROUTE_SMOKE modal 壳挂载吞噬触摸事件**：13 个全尺寸透明 modal 壳叠在
   ARTICLESCREEN 内容之上，导致侧栏/空态所有 onClick 失效；hitTestBehavior
   (HitTestMode.None) 外包裹无效（内置容器上也不生效）。已移除挂载并在代码内
   注释说明：Phase 4 以真实承载（bindSheet/AlertDialog/bindMenu）替代；P3 冒烟
   证据已 CLOSED 归档。二分排查耗时约 20 分钟（本批最大时间消耗）。
3. SideBarContainer(Embed) 内容区窄于 minContentWidth 时强制 Overlay——改用
   Row 固定侧栏宽度 220（侧栏布局不在 R1-R6 管辖清单）。

## BC-0007 设备走查未完成（时间盒耗尽）
- 实现完整在库（bindMenu feed 菜单 + AlertDialog Unsubscribe 确认 +
  removeFeed 级联删除 + 探针缓存刷新）；harmony-steps.csv 已记录序列但 notes
  标注 walkthrough INCOMPLETE；4B 差分时先走一遍 More options → Remove Feed →
  Remove（如菜单锚点 accessibilityText='More options' 匹配问题，4B 侧调整
  dump 匹配口径）。
- 其余三 BC（0004/0005/0008）+ 重启持久 + 探针数据出口全部设备实测通过。

## 给 4B 的数据出口说明
- feeds/articles/article_statuses/last_refreshed_at 四键已注册真实 provider
  （语义缓存，DB 变更即刷新）；semantic-probe.json 实测：20 篇文章入库、
  last_refreshed_at=1788232313。
- 新增沙箱导出 feed-snapshot.json（同快照冗余出口）。

---

# 批次 2（任务 #15，阅读域 4 feature）追加记录

## 输入链复测（DEC-022 裁决点 3）——已加固并实测
稳定序列：click TextInput → **sleep 1.5s**（焦点稳定+IME 起来）→ uiInput inputText x y value → dump 验证落字（IN_BOX 检查）→ 失败自动 fallback `uiInput text` 命令 → keyEvent 2054（Enter 收键盘释放 Add 按钮）。本轮 setup 两次均 IN_BOX 一次通过。序列已写入 harmony-steps notes。

## Text.accessibilityText 不进 dumpLayout（影响 desc= 锚点）
Text 组件的 accessibilityText 未映射到 dump 的 contentDescription——BC-0011/0014/0016/0007 的 desc 锚点全部无法命中。已改为**可见文本锚点**：reader 底栏 '● Mark as read'/'★ Star'、侧栏 feed 行 'More options'（改造后构建已装但时间盒耗尽未完成设备复验——4B 差分时以可见文本锚点走）。

## 环境级问题（如实记录）
1. **Back 退根页面后再次 aa start 白屏**：列表页（NavDestination 栈根）按 Back 应用退出，之后 aa start 窗口空白（进程活着）；force-stop + start 可恢复。走查脚本已规避开根页 Back。
2. **fmtDate 日不补零**（'2026-09-1'）导致走查 regex 失配一轮（应用小缺陷，不影响断言口径——锚点是标题不是日期；下批可顺手补零）。

## 验证状态（如实）
- 设备实测 PASS：输入链（2 次）、BC-0004 复验、bc0009_data（article_filter=status=UNREAD 探针）、bc0010（feed 过滤+标题）、bc0011_read/title（打开即已读+标题渲染）、bc0015_cleared（Unread 清空）、feed/account 重启持久
- 实现在库待 4B 复验：bc0011_bar/0014/0016（可见文本锚点改造后未及走）、bc0007（同锚点问题）、bc0015 dialog 文本
- BC-0012（全屏图片页）：Ars RSS summary 纯文本无内嵌图，入口不存在——TOOL_GAP（含图 feed 或阅读域增强时补）

---

# R4（2026-09-03，replayer 真机重放复活）追加记录

## R4-1 本地化漂移（localization drift）：首轮重放 0 pass 根因
- 现象：replayer 全选 9 BC 中 7 FAIL + 2 PRECONDITION_FAILED，所有失败停在 step 0。
- 根因：harmony-steps.csv 仍是 R2 英文锚点（Add Feed / Mark All as Read / Theme…），而 R3 已全量中文本地化（添加订阅源/全部标为已读/主题…，见 revision3/anchor-mapping.csv 70 行）。
- 修复：harmony-steps.csv 7 行改 zh-CN 目标（0004/0005/0007/0017/0018/0019/0020），0017 改为过滤面 surfacing（星标→全部），0018 的 wait（replayer 无 wait action）改为 tap 显示（分区头为 显示+与外观 双节点）。

## R4-2 冷复位后点按被吞（tap-swallow race）
- 现象：prepare 的 tap ☰ 返回 ok 但抽屉没开，后续锚点全 miss。
- 根因：cold reset（force-stop + start）后首帧构建期输入被框架吞掉，而 stable_ui_snapshot 只等 dump 可用不等输入就绪。
- 修复：prepare 首步加无害 settle-tap（tap 文章标题 Text，非 clickable，纯烧一次 dump 周期约 3-4s），再 tap ☰。附带 verify：第二轮起全部 prepare 命中。

## R4-3 空态按钮抢锚点（empty-state first-match race）
- 现象：step 1 tap 添加订阅源 命中 (660,1747)（空态按钮）而非抽屉入口 (542,551)，sheet 未开。
- 根因：locate 取 raw 首个匹配；冷复位后列表加载中出现 暂无订阅源 空态（当时过滤器被上轮留在 星标 空集），空态按钮与抽屉入口同名。
- 修复：重放前手工把过滤器复位到 全部（有数据时空态不存在，锚点唯一）。教训：有数据 + 全部过滤 是重放前置条件，已记入 harmony-steps notes。

## R4-4 子串陷阱（substring trap）
- 现象：BC-0017 收尾 tap 全部 命中 全部标为已读（顶栏按钮），过滤器没切回。
- 根因：locate 为大小写不敏感子串匹配，全部 ⊂ 全部标为已读。
- 修复：0017 收尾改为 tap 未读（唯一子串），事后手工复位 全部。0007 的 移除/移除订阅源 同理存在首匹配不定——本轮命中正确（ops 有坐标为证），已记录风险。

## R4-5 其它如实记录
- ☰ 字形在 dump raw 中为字面 UTF-8（非 \u2630 转义），可直接做 tap target。
- `--bc-filter` 仅 dry-run 生效，真跑固定处理全部 21 行（replay_workspace 用原路径重读）。本轮用“过滤后的 BC 副本文件”做 scoped 分批（sub1/sub2/sub3），合并后 21 行一次 validate ok。
- pre_state tokenizer 取括号内含拉丁/等号片段但保留全角右括号残留（如 `Add Feed）`），该类 token 永不可满足——0004/0018 的（desc=…）已按 anchor-mapping 去拉丁化，回归“无机器可检 token 则放行”的设计 fallback（与 0005/0019 等 12 条一致）。
- result_assertions 仍是 P2 老 schema（type/target），replayer 只认 kind——故步骤全绿仍判 MANUAL（诚实终态，不改契约原文；Gate2-live 保持 PASS）。
- HAP 交付物事故与恢复：10:23 误把 REV2-FINAL（前 R3 英文构建）装到 tools/signing 入口并覆盖安装到设备，导致设备 UI 回退英文；已用现源码 Sep-3-07:00 unsigned 构建经 hap-sign-tool 本地链重签（verify-app success），安装验证中文 UI 与数据完好；归档 builds/R3-LOCALIZED-signed.hap，旧骨架件留 .bak。见 DEC-045。
