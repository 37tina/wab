# 网站缺陷观察日志（CapyReader 迁移期间 · 任务 #21）

> 如实记录，不修饰；每条含现象/影响/处置。

## D-01 phasePrompts SKILL_ROOT 注入时序缺陷（已修复）
- 现象：setSkillRoot 后生成的 android 完整版工单 skill 路径仍缺前缀（READING 常量模块加载期固化）
- 影响：CapyReader Phase 1 首份工单路径错误（已补发修正消息 msg_capy_p1_pathfix）
- 处置：READING 改运行时函数 readingAt(getSkillRoot())；tsc 0 + tsx 验证通过（2026-09-01 04:3x）

## D-02 镜像项目 autocreate 上报在部分环境失败（未修复，有兜底）
- 现象：browser 工具打开 autocreate URL 后 /api/mirror/project 长时间为空（内嵌浏览器环境 fetch 未达后端）；CapyReader 项目两次触发均未上报
- 影响：新浏览器首次打开项目页需等恢复逻辑，且项目 ID 由配方手动指定（migration-1788209200000）
- 处置：总控手动 POST 配方兜底（P1 汇总 3291 字符）；根因待查（可能与内嵌浏览器 JS 执行环境有关）

## D-03 恢复配方 version 与网页状态的幂等性
- 现象：CapyReader 配方 version=1，后续每阶段 approve 后需手动更新配方 phases[] 并提升 version，否则已恢复过项目的浏览器不刷新
- 影响：多浏览器环境下网页状态推进滞后于迁移实况
- 处置：暂以总控每阶段手动更新配方弥补；建议后续把 approve 流程改为后端直写配方

## D-04 git stash 未 pop 导致工单路径缺陷回归（已彻底修复）
- 现象：merge 远端前 stash 了 readingAt 修复且忘记 pop，P3 工单 skill 路径再次缺前缀（与 D-01 同症状回归）
- 影响：CapyReader P3 首份工单路径错误（已补发 msg_capy_p3_pathfix 修正）
- 处置：stash pop 恢复 + 修复已提交推送（防再丢）；流程教训：merge 前后 stash/pop 必须成对

## D-05 迁移全程功能层缺陷观察（CapyReader run 期间）
- phasePrompts 工单模板偏 Android 特化（如"禁止实现 Todo CRUD"字样出现在非待办项目工单）——通用化工单已由 skill v2 薄壳体系解决大半，完整版模板建议抽象领域无关
- 恢复配方 activePhase 需总控每阶段手动更新（D-03 的实际发生）——5 次手动更新，建议 approve 流程改为后端直写配方
- 网页对话面板在高频消息期（4A/4B 并行）偶有卡顿（5 秒轮询全量拉取 4MB+ 消息）——建议消息 API 支持增量（since 参数）
- Gate 报告展示（overview API）在 P4 进行期读取 gate-report.json 得到的是 P1 快照（覆盖写）——数据源歧义，建议按阶段存档快照
