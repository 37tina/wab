# CapyReader 双端对比（2026-09-03 活体 · 新鸿蒙模拟器 · 未改代码）

- Android：`emulator-5554`，`com.capyreader.app.debug` 2026.07.1212（存量：Ars 6 + 少数派 10，共 16）
- 鸿蒙：新模拟器 `Pura 90 test`（`127.0.0.1:5559`），`com.capyreader.app.debug` 9-03 最新 unsigned 构建（刚装上）。现场建本地账号→点添加订阅源→自动拉取少数派实时数据（9-01~9-03）
- 旧设备 5557（capy-competition 组）不动。

## 截图组（左 Android / 右鸿蒙）

| 文件 | 内容 | 结论 |
|---|---|---|
| `SBS-01-addaccount-seed.png` | 添加账号种子页（安卓为归档 `capy_first.png`，鸿蒙为本次活体） | 五选项中英对照：本地/Feedbin/FreshRSS/Miniflux/Reader 一致 |
| `SBS-02-article-list.png` | 文章列表 | 卡片三件套（标题/摘要/时间+圆点+配图）形态一致；安卓深色英文 Ars，鸿蒙浅色中文少数派（原生适配）；两端均为实时数据 |
| `SBS-03-drawer.png` | 抽屉 | 入口语义对齐：搜索/刷新/加订阅/设置＋全部/未读/星标＋订阅源列表；安卓 All 16/Today 6/Ars 6/少数派 10，鸿蒙 全部/未读/星标/少数派（Ars 尚未添加） |
| `SBS-04-reader.png` | 正文阅读器 | RichText 真正文+链接+底部工具栏双端具备（安卓 Ars 英文深色 vs 鸿蒙少数派中文浅色，文章不同，载体能力对标） |

单图：`android-*.png`、`harmony-*.jpeg`（另有 `harmony-empty-nofeed.jpeg` 建号后拉取前空态）。

## 录屏（无声，边操作边录）

- `capy-android.mp4`（45s，1080x2400 设备端 screenrecord）：列表→抽屉→列表→正文→回列表
- `capy-harmony.mp4`（70s，1320x2856 @6fps 设备帧轮询）：列表→抽屉→列表→正文→回列表（无代码改动）
