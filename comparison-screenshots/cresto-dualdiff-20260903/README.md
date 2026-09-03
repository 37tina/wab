# CRESTO 双端对比（2026-09-03 活体 · 未改代码）

- Android：`emulator-5554`（Pixel_10，Android 17），`com.nevoit.cresto` 1.0(1081)，存量数据（Weekly-report / Water-plants，均 Overdue-8/30）
- 鸿蒙：新模拟器 `Pura 90 test`（`127.0.0.1:5559`），`com.nevoit.cresto` visual-pass78（2026-08-30 构建，刚装上），测试数据为对比现场经 UI 新建的同名两条（未设日期，故无 Overdue 行）
- 操作：只点按截图，不改代码。安卓启动器解析失败插曲：`am start -n com.nevoit.cresto/.AppIconDefault` 报不存在，改全限定 `com.nevoit.cresto/com.nevoit.cresto.AppIconDefault` 拉起成功；另顺手 `install -r` 同版本 APK 一次。

## 截图组（左 Android / 右鸿蒙）

| 文件 | 内容 | 结论 |
|---|---|---|
| `SBS-01-home-withdata.png` | 有数据首页 | 列表/勾选/分组 chips 对齐；差异：安卓英文 vs 鸿蒙中文（原生适配），安卓有 Overdue 红字（存量日期），鸿蒙无日期；顺序相反（安卓 Weekly 在上，鸿蒙 Water 在上，属排序态不同）；鸿蒙 `未完成 1` 计数与 2 行不一致（端上小瑕疵，记录） |
| `SBS-02-search-open.png` | 搜索展开 | 搜索框+清除 X+分组 chips+列表过滤形态一致；中英 placeholder 对照 |
| `SBS-03-sort-menu.png` | 排序菜单 | 逐项对齐：Default/默认✓、Due Date/截止日期、Flag/旗标、Title✓/标题、Ascending/升序、Descending✓/降序✓；勾选项一致 |

单图：`android-*.png`、`harmony-*.jpeg`（另有 `harmony-home-empty.jpeg` 空态）。

## 录屏（无声，边操作边录）

- `cresto-android.mp4`（32s，1080x2400 原生帧率）：首页→搜索开/关→排序菜单开/关→新建表单→回首页
- `cresto-harmony.mp4`（43s，1320x2856 @6fps 设备帧轮询）：首页→搜索→排序→新建表单（安卓用设备端 screenrecord，鸿蒙用 snapshot 轮询，无代码改动）
