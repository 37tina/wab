最终提交版快照（2026-08-31 09:55）— 含双机行为差分验证升级
============================================================

状态：收敛式重构 + 双机差分升级全部完成并通过终验
  （上一版快照 = 收敛式重构完成版；本版在其上加双机差分升级）

双机差分升级内容：
  1. dual_verify.py 双机差分引擎（~1300 行）：
     两侧恢复同一语义前置状态 → Android 按 android_steps / Harmony
     按 harmony_steps 各自执行 → 机器 A/B 四类结果
     （observable/semantic data/persistence/side effect）——
     比较结果不比较路径，不做 UI 像素 A/B
  2. live oracle cache：Android 结果四元组键控缓存（bc_id+APK sha+
     seed sha+BC sha），命中不重跑；--refresh-oracle 强制重采
  3. 修复回环：DIFF → rework-orders.csv（机器可读修复清单）→
     只修 Harmony → --rework-round 1/2 只重跑 DIFF 的 BC →
     round 2 仍 DIFF → MANUAL_TAKEOVER 转人工（退出码 0/1/2）
  4. SKILL.md 七步流程重写（实现→双机差分→DIFF 走回环→全 MATCH
     →Surface/UI→Gate 4；Gate 4 增 dual_diff 可选消费——文件不存在
     =休眠不激活，任一 DIFF→FAIL）
  5. #91 顺带修复 2 个遗留缺陷（幽灵引用/幽灵字段——基线 9 挂根因）

终验：双树八套测试全绿（0 失败）；治理 5 文件同步 + refresh-freeze
（DEC-20260831 修复回环验证轮次链兼容 validate_stage4 校验）

对照历史：skill-snapshot-20260830.zip（收敛式重构前）/ 
skill-snapshot-converged-20260831.zip（收敛式重构完成版）
