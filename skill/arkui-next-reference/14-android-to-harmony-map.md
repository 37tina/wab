# Android（View 体系 + 系统 API）→ HarmonyOS NEXT 原生对照表

> **定位**：compose-mapping.md 覆盖的是 **Jetpack Compose → ArkUI**；本表覆盖 **传统 Android View 体系（XML/View 类）+ 系统/平台 API + 交互视觉模式**，供 Phase 3-4 迁移注入。两者互相引用不重复。
> **口径**：ArkTS 以 API 12（HarmonyOS 5.0/NEXT）为基线；API 签名已对照本地 SDK d.ts（`/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/ets/`）核实；不确定处标 **待验证**。
> **核心原则**：鸿蒙侧一律给**官方原生写法**（组件/系统 Kit/推荐模式），不做"Android 式手搓模仿"。鸿蒙没有的组件（FAB/MaterialCardView/CoordinatorLayout 等）标注并给鸿蒙标准替代模式。
> 记号：⚠ = 高危差异；`〔CM §n〕` = 详见 compose-mapping.md 第 n 条；`〔0n〕` = 详见本库 0n-xx.md。

## 目录
- A. UI 组件层（34 条：基础控件 / 容器 / RecyclerView 专题 / Material 组件 / 弹窗）
- B. 系统与平台能力层（18 条：生命周期 / 路由 / 数据 / 后台 / 硬件 / 权限）
- C. 交互与视觉模式层（12 条）
- D. 踩坑速查（7 条，本项目实战提炼）
- 附录：鸿蒙无直接对应组件清单

---

# A. UI 组件层（传统 View 体系）

## A-1 基础控件

### A1. TextView → Text
```xml
<TextView android:text="标题" android:textSize="16sp" android:textStyle="bold" android:maxLines="1" android:ellipsize="end"/>
```
```ts
Text('标题').fontSize(16).fontWeight(FontWeight.Bold)
  .maxLines(1).textOverflow({ overflow: TextOverflow.Ellipsis })
```
⚠ 单位 sp→fp 同构（ArkUI fontSize 默认 fp）；`android:ellipsize` 必须配 `textOverflow`，且 maxLines 不写默认折行。autoLink→`Text` 不支持，用 `[链接](url)` 格式或 Span+onClick。

### A2. EditText → TextInput / TextArea
```kotlin
val et = findViewById<EditText>(R.id.et); et.addTextChangedListener(object: TextWatcher{ ... })
```
```ts
TextInput({ placeholder: '请输入' })
  .onChange((v: string) => this.query = v)      // ≈ onTextChanged
  .onSubmit(() => this.search())                // ≈ imeOptions action
  .type(InputType.Normal)                       // ≈ inputType
TextArea({ placeholder: '多行' }).height(120)    // ≈ EditText multiline
```
⚠ 受控陷阱：不要回写 `.text`（IME 组合输入丢字），程序设值用 controller〔CM §21〕。inputTypePassword→`type(InputType.Password)`；maxLength→`.maxLength(20)`。

### A3. Button / MaterialButton → Button
```xml
<Button android:text="保存"/>
<com.google.android.material.button.MaterialButton app:icon="@drawable/ic_save"/>
```
```ts
Button('保存', { type: ButtonType.Capsule }).onClick(() => this.save())
// 带图标：Button 内部放 Row（图标+文字）
Button() { Row({ space: 6 }) { SymbolGlyph($r('sys.symbol.save')); Text('保存') } }
```
⚠ 无 icon 属性，图标自组；MaterialButton 的 tonal 风格 → `.backgroundColor(半透明)`+`.stateEffect(true)`（默认按压态就有）。

### A4. ImageView → Image
```xml
<ImageView android:src="@drawable/img" android:scaleType="centerCrop" android:contentDescription="…"/>
```
```ts
Image($r('app.media.img')).objectFit(ImageFit.Cover)   // centerCrop
  .alt($r('app.media.placeholder'))                     // 占位
  .interpolation(ImageInterpolation.Medium)             // 高质量缩放
Image('https://…/a.png')                                // 网络图原生支持（需 INTERNET 权限）
```
⚠ scaleType 对照：fitXY→Fill、fitCenter→Contain、centerInside→Contain、center→None（无缩放）。矢量染色 `.fillColor()` 仅 SVG；无 contentDescription 等价物（无障碍用 `.accessibilityText()`，待验证属性名）。

### A5. Chip（Material）→ 无 Chip 组件，标准替代=自绘胶囊 / SegmentButton
```xml
<com.google.android.material.chip.Chip android:text="标签" app:chipIcon="…" style="@style/Widget.MaterialComponents.Chip.Filter"/>
```
```ts
// 鸿蒙无 Chip 组件（SDK 无 chip d.ts）。标准模式①：胶囊自绘（官方推荐组合）
Row() {
  Text('标签').fontSize(13).fontColor(Color.White).padding({ left: 12, right: 12, top: 6, bottom: 6 })
    .backgroundColor('#FF5B7CF6').borderRadius(14)          // 胶囊=borderRadius=高/2
}.onClick(() => this.toggle())
// 模式②：多选过滤场景用 SegmentButton（@ohos.arkui.advanced.SegmentButton，API 11，签名待验证）
```
⚠ Filter Chip 组（多选）→ 自管数组 + `.backgroundColor(选中色)` 切换；close 图标 → 胶囊内叠 SymbolGlyph+onClick。

## A-2 容器与滚动

### A6. LinearLayout → Row / Column
```xml
<LinearLayout android:orientation="vertical" android:gravity="center"/>
```
```ts
Column({ space: 8 }) { … }.justifyContent(FlexAlign.Center).alignItems(HorizontalAlign.Center)
```
⚠ gravity 拆成主轴 justifyContent + 交叉轴 alignItems；layout_weight → `.layoutWeight(1)`（只对 Row/Column 直接子级生效）。

### A7. FrameLayout → Stack
```xml
<FrameLayout><View/><!-- 居中叠放 --></FrameLayout>
```
```ts
Stack({ alignContent: Alignment.Center }) { A(); B() }
```
⚠ layout_gravity（per-child）→ Stack 子级 `.align(Alignment.X)`（API 10 起，待验证）或 `.offset()`，多对齐需嵌套 Stack〔CM §3〕。

### A8. ConstraintLayout → RelativeContainer
```kotlin
ConstraintLayout { tv1.centerInParent(); tv2.below(tv1).margin(8.dp) }
```
```ts
RelativeContainer() {
  Text('1').id('a').alignRules({ center: { anchor: '__container__', align: VerticalAlign.CENTER } })
  Text('2').id('b').alignRules({ top: { anchor: 'a', align: VerticalAlign.Bottom } }).margin({ top: 8 })
}
```
⚠ 无完整约束求解器；锚点必须先 `.id()`；复杂约束链建议直接转 Row/Column/Stack 组合（更 ArkUI 原生）〔01〕。

### A9. GridLayout → Grid / GridRow-GridCol
```xml
<GridLayout android:columnCount="3"/>
```
```ts
Grid() { ForEach(this.items, (t: Item) => { GridItem() { Cell(t) } }) }
  .columnsTemplate('1fr 1fr 1fr').rowsGap(8).columnsGap(8)   // 不设 columnsTemplate 不生效！
```
⚠ 响应式栅格用 GridRow/GridCol（breakPoints sm/md/lg）〔01 §GridRow〕。

### A10. NestedScrollView → Scroll / List
```xml
<nestedScrollView><LinearLayout>…整页内容…</LinearLayout></nestedScrollView>
```
```ts
Scroller + Scroll(this.scroller) { Column({space:12}) { … } }.edgeEffect(EdgeEffect.Spring)
```
⚠ 嵌套滚动（父列表内子列表）→ List `.nestedScroll({ scrollForward: NestedScrollMode.PARENT_FIRST, … })` 控制协商〔02 §nestedScroll〕；Scroll 内放 List 需给 List 固定高度或用 List 单容器。

### A11. SwipeRefreshLayout → Refresh
```kotlin
SwipeRefreshLayout(isRefreshing, onRefresh) { recyclerView }
```
```ts
Refresh({ refreshing: $$this.isRefreshing }) { this.ListBuilder() }
  .onRefreshing(() => { this.reload(); this.isRefreshing = false })
```
⚠ `$$` 双向绑定才会自动收起指示器〔CM §18〕。

### A12. ViewPager2 → Swiper
```kotlin
ViewPager2(viewPager2).adapter = fragmentsStateAdapter   // 横滑翻页
```
```ts
Swiper() {
  PageA(); PageB(); PageC()
}.index(0).indicator(true).loop(false).duration(400)
 .onChange((i: number) => this.cur = i)
 .cachedCount(1)                       // 预加载，≈ offscreenPageLimit
```
⚠ onPageChangeCallback→onChange；竖向滑动 `.vertical(true)`；禁用户滑动 `.enabled(false)` 配 `controller.swipeTo(i)` 程序翻页（SwiperController）。

### A13. RecyclerView → List + LazyForEach（核心专题）
```kotlin
class TodoAdapter(var items: List<Todo>) : RecyclerView.Adapter<VH>() {
  override fun onCreateViewHolder(p: View, i: Int) = VH(ItemTodoBinding.inflate(p))
  override fun getItemCount() = items.size
  override fun onBindViewHolder(h: VH, pos: Int) = h.bind(items[pos])
}
```
```ts
// 鸿蒙原生：List + LazyForEach + IDataSource（模板见 02 §2）
@Local ds: TodoDataSource = new TodoDataSource()
List({ space: 8 }) {
  LazyForEach(this.ds, (t: Todo) => { ListItem() { TodoRow(t) } }, (t: Todo) => t.id.toString())
}.cachedCount(5)   // 预渲染 ≈ Recycler 缓存
```
⚠ 三大差异：① 无 Adapter 类，数据源实现 `IDataSource` 接口（totalCount/t getData/indexId/registerListener/changeListener）；② **必须写第三个 keyGenerator 参数**（≈ DiffUtil.areItemsTheSame 的 key）；③ 小数据量（<50）可直接 ForEach 简化。

**RecyclerView 通知家族 → IDataSource 通知家族（d.ts 已核对）**

| Android | 鸿蒙（listener 上调用） | 说明 |
|---|---|---|
| notifyDataSetChanged() | `onDataReloaded()` | 全量刷新（性能同 Android 一样差） |
| notifyItemInserted(pos) | `onDataAdd(index)` | 旧名 onDataAdded（@useinstead 弃用） |
| notifyItemRemoved(pos) | `onDataDelete(index)` | 旧名 onDataDeleted |
| notifyItemMoved(f,t) | `onDataMove(from, to)` | 旧名 onDataMoved；配合排序动画 |
| notifyItemChanged(pos) | `onDataChange(index)` | 单项内容变化 |
| DiffUtil.calculateDiff | 无内建 | 手动 diff 后调精细 onData*（推荐）；或懒法 onDataReloaded |
```ts
// 典型 DataSource 骨架（完整模板见 02 §2）
class TodoDataSource implements IDataSource {
  private list: Todo[] = []
  private listeners: DataChangeListener[] = []
  totalCount(): number { return this.list.length }
  getData(i: number): Todo { return this.list[i] }
  registerListener(l: DataChangeListener): void { this.listeners.push(l) }
  unregisterListener(l: DataChangeListener): void { this.listeners = this.listeners.filter(x => x !== l) }
  notifyDataReload(items: Todo[]): void { this.list = items; this.listeners.forEach(l => l.onDataReloaded()) }
  notifyDataAdd(i: number): void { this.listeners.forEach(l => l.onDataAdd(i)) }
}
```

**ItemDecoration → ListItemGroup / Divider**
```kotlin
recyclerView.addItemDecoration(DividerItemDecoration(ctx, VERTICAL))   // 分割线
recyclerView.addItemDecoration(HeaderDecoration(section))               // 吸顶 header
```
```ts
// 分割线：鸿蒙不装饰、直接隔——List({space}) 或列表项自身带 bottom 边距
List({ space: 1 }) { … }.backgroundColor('#FFE5E5EA')   // space 露底色成 1px 分割线
// 分组吸顶：ListItemGroup header + sticky
List().sticky(StickyStyle.Header) {
  ListItemGroup({ header: this.headBuilder('进行中') }) { LazyForEach(…) }
}
```
⚠ 吸顶 sticky 挂在 **List 上**（不是 Group）；分组结构=ListItemGroup 包数据项〔02 §sticky、CM §12〕。

**ItemAnimator → animateTo / transition**
```kotlin
recyclerView.itemAnimator = DefaultItemAnimator()   // 增删位移动画
```
```ts
this.getUIContext().animateTo({ duration: 300 }, () => this.ds.notifyDataDelete(i))  // 通知包进动画闭包
```
⚠ 增删有淡入淡出；**排序重排位移动画部分支持**（onDataMove，效果待验证），降级=接受瞬时重排或逐项 transition。

### A14. WebView → Web
```kotlin
webView.settings.javaScriptEnabled = true; webView.loadUrl("https://a.com"); webView.webViewClient = …
```
```ts
Web({ src: 'https://a.com', controller: this.ctrl })   // this.ctrl: WebController = new WebController()
  .javaScriptAccess(true).domStorageAccess(true)
  .onPageEnd((e) => this.url = e.url)
```
⚠ 无 system WebView 差异问题（ArkWeb 内核）；JS 互调 `this.ctrl.runJavaScript('f()')`（异步取回值）；混合开发页面级用 Web，组件级嵌入同。需在 module.json5 申请 `ohos.permission.INTERNET`。

## A-3 导航与 Material 容器

### A15. Toolbar / ActionBar → Navigation 标题栏 或自绘顶栏
```kotlin
setSupportActionBar(toolbar); supportActionBar.title = "待办"; supportActionBar.setDisplayHomeAsUpEnabled(true)
```
```ts
Navigation(this.stack) { … }
  .title('待办')                       // 系统标题栏（自动避让安全区）
  .menus(this.menuBuilder)             // 右上动作区
// 定制需求（玻璃拟态/大标题）→ 不用 title，Stack 叠加自绘顶栏（playbook 模式）
```
⚠ subtitle/大标题模式系统标题栏不提供 → 自绘；返回键系统自动带（栈空退出）〔03〕。

### A16. CoordinatorLayout + AppBarLayout（滚动联动）→ 无直接对应，@State 联动模式
```xml
<coordinatorLayout><appBarLayout><collapsingToolbarLayout app:layout_scrollFlags="scroll|exitUntilCollapsed"/>…
```
```ts
// 鸿蒙无滚动联动容器。原生模式：Scroll/List 滚动事件 + @State 驱动顶栏
@Local barHeight: number = 200; @Local barTitleOpacity: number = 0
List().onDidScroll((x: number, y: number) => {     // y=每帧滚动增量
  this.barTitleOpacity = Math.min(1, Math.max(0, this.barTitleOpacity + y / 100))
}).onScrollIndex((first: number) => { if (first > 0) this.compact = true })
```
⚠ scrollFlags 行为（enterAlways/exitUntilCollapsed/snap）全部手驱动；本库既有方案=onDidScroll 阈值〔CM §14/§65、playbook〕。

### A17. DrawerLayout + NavigationView（抽屉）→ SideBarContainer
```kotlin
DrawerLayout { content; NavigationView(menuRes) }   // 侧滑抽屉
```
```ts
SideBarContainer(SideBarContainerType.Overlay) {
  Column() { this.DrawerMenuBuilder() }              // 侧边栏内容（菜单自绘）
  this.MainContent()                                 // 主内容
}.sideBarWidth(280).showSideBar(false)               // 初始收起；showControlIcon 收起后留把手
```
⚠ Overlay 模式浮在内容上（≈抽屉）；菜单项无 NavigationView menu XML，用 List/Column+onClick 自绘；侧滑手势侧栏容器自带。**多数鸿蒙应用底部 Tab（Tabs）替代抽屉导航**——新页面建议直接 Tabs〔03 §选型〕。

### A18. BottomNavigationView → Tabs(barPosition: End)
```kotlin
BottomNavigationView.menu.add(…); bottomNav.setOnItemSelectedListener { … }
```
```ts
Tabs({ barPosition: BarPosition.End }) {           // End=底部；Start=顶部（≈TabLayout）
  TabContent() { PageHome() }.tabBar('首页')
  TabContent() { PageMine() }.tabBar('我的')
}.scrollable(false).barMode(BarMode.Fixed)
 .onChange((i: number) => this.cur = i)
```
⚠ badge（角标）→ `.tabBar()` 传 `{ builder }` 自绘或 Badge 组件叠加〔03 §自定义 TabBar〕；图标+文字 tabBar 用 `{ icon: …, text: … }` 对象。**Tabs 切换不销毁子页**（≈ ViewPager keepalive），但也意味着首屏全建，重页面懒加载自管〔03 陷阱〕。

### A19. TabLayout + ViewPager2 联动 → Tabs 一体化
```kotlin
TabLayoutMediator(tabLayout, viewPager2) { tab, pos -> tab.text = titles[pos] }.attach()
```
```ts
// Tabs 本身=TabLayout+ViewPager 合体，无 mediator；顶部模式：
Tabs({ barPosition: BarPosition.Start, index: this.cur }) { TabContent()… }.onContentWillChange(…)   // 拦截切换（待验证）
```
⚠ 需"页面内嵌横滑区"（Tabs 嵌 List 内）→ Swiper + 自绘 tab 指示条（Tabs 是页面级容器不嵌入滚动）。

### A20. FloatingActionButton → 无 FAB 组件（鸿蒙模式两选一）
```kotlin
FloatingActionButton(onClick = { newTodo() })   // 右下角悬浮圆钮
```
```ts
// ① 官方推荐位置：NavDestination/Toolbar 的操作按钮（menus 区，主操作右上角）
Navigation(…).menus(@Builder 提供圆形加号按钮)
// ② 需"悬浮内容区"时：Stack 叠加模式（见 CM §29 完整代码）
Stack({ alignContent: Alignment.BottomEnd }) {
  this.ListBuilder()
  Button({ type: ButtonType.Circle }) { SymbolGlyph($r('sys.symbol.plus')) }
    .width(56).height(56).margin(24).shadow({ radius: 12 }).onClick(() => this.create())
}
```
⚠ 鸿蒙设计规范（HM Design）**不提倡 Material FAB 位**；新迁移先问"这个操作能否进顶栏 menus"——能则用①，全局常驻入口才用②〔CM §29〕。

### A21. MaterialCardView → 无卡片组件，Column 组合模式
```xml
<MaterialCardView app:cardCornerRadius="16dp" app:cardElevation="4dp" app:strokeWidth="1dp">
```
```ts
// ArkUI 卡片=官方组合：Column + borderRadius + backgroundColor + shadow
Column({ space: 8 }) { … }
  .padding(16).borderRadius(16).backgroundColor(Color.White)
  .shadow({ radius: 12, color: 'rgba(0,0,0,0.08)', offsetY: 4 })
  .clip(true)                       // 裁圆角内容（子内容溢出时必需）
// 描边：.border({ width: 1, color: '#FFE5E5EA', radius: 16 })
```
⚠ elevation 有阴影梯度（1-24dp），ArkUI shadow 无梯度档位，radius/color 手调；列表项卡片性能：阴影+圆角有开销，长列表可降级为"背景色块+无边框"。

### A22. Snackbar → showToast / 自绘轻提示
```kotlin
Snackbar.make(view, "已删除", LENGTH_SHORT).setAction("撤销"){ undo() }.show()
```
```ts
// 无操作按钮版（系统原生）：
this.getUIContext().getPromptAction().showToast({ message: '已删除', duration: 2000, bottom: '40%' })
// 带撤销按钮：无 Snackbar 等价物 → bindSheet/自绘底部横幅（Stack 底部叠层+transition）
```
⚠ Toast 常驻底部且不可点；"删除+撤销"模式鸿蒙惯用 bindSheet 确认或列表项 swipeAction 内直接给撤销窗口〔CM §35〕。

### A23. AlertDialog / MaterialAlertDialog → showAlertDialog（或声明式 AlertDialog）
```kotlin
MaterialAlertDialogBuilder(ctx).setTitle("删除？").setMessage("不可恢复")
  .setPositiveButton("删除"){ del() }.setNegativeButton("取消", null).show()
```
```ts
this.getUIContext().showAlertDialog('不可恢复', '删除该待办？', {
  primaryButton: { value: '取消', action: (): void => {} },
  secondaryButton: { value: '删除', fontColor: '#FFF44336', action: (): void => this.del() }
}, { alignment: DialogAlignment.Center })
```
⚠ positive/negative 按钮顺序：primary=左（取消）、secondary=右（确认），与 Android 相反（Android 左取消右确认——顺序一致，但**危险操作放 secondary 右侧**要手动给 fontColor）；回调签名必须显式 `(): void =>`（见 D-5）。列表选项对话框用 ActionSheet。

### A24. BottomSheetDialog / ModalBottomSheet → bindSheet
```kotlin
val sheet = BottomSheetDialog(ctx); sheet.setContentView(content); sheet.show()
```
```ts
Column(){ … }.bindSheet($$this.showSheet, this.sheetBuilder(), {
  detents: [SheetSize.MEDIUM, SheetSize.LARGE], showClose: true, dragBar: true
})
```
⚠ `$$` 双向绑定（点关闭自动置 false）；builder 传 `this.xxx()` 调用形；**无 onDismiss 回调**（见 D-2）〔CM §33、07 §bindSheet〕。

### A25. DatePickerDialog / TimePickerDialog → DatePicker / TimePicker（组件式）或 bindDatePicker
```kotlin
DatePickerDialog(ctx).setOnDateSetListener{ _,y,m,d -> … }.show()
```
```ts
// 方式①（官方推荐、轻量）：任意组件绑日期选择
Text('2026-01-01').bindDatePicker(this.due, (v: Date): string => v.toDateString())  // 回调 return 展示串
// 方式②：弹层内嵌组件式
DatePicker({ start: new Date('2020-1-1'), end: new Date('2030-12-31'), selected: this.due })
  .onDateChange((d: Date) => this.due = d)
// 时间：TimePicker({ selected: this.time }).onChange((h: number, m: number) => { … })
```
⚠ CalendarPickerDialog（月历选择）**必须静态 `CalendarPickerDialog.show({...})` 且确认回调是 `onAccept`** 不是 onConfirm（D-1）；bindTimePicker 存在性**待验证**，保底 TimePicker+bindSheet〔CM §30、05〕。

### A26. PopupMenu → bindMenu
```kotlin
PopupMenu(ctx, anchor).apply { menuInflater.inflate(R.menu.sort, menu); setOnMenuItemClickListener{…} }.show()
```
```ts
Image($r('app.media.ic_more')).bindMenu(this.menuBuilder)   // 自动锚定+自动开关，免 expanded 状态
@Builder menuBuilder() {
  Menu() {
    MenuItem({ content: '按时间' }).selected(this.sort === 0).onClick((): void => this.setSort(0))
    MenuDivider()
    MenuItem({ content: '按优先级' }).onClick((): void => this.setSort(1))
  }
}
```
⚠ MenuItem options 是 `{ content }`（无 value/action 字段），事件挂 `.onClick`（D-3）；长按菜单 `.bindContextMenu(this.menuBuilder, ResponseType.LongPress)`〔CM §34〕。

### A27. Spinner → Select（下拉单选）
```xml
<Spinner android:entries="@array/cities"/>   <!-- 点击弹下拉单选 -->
```
```ts
Select([{ value: '北京' }, { value: '上海' }, { value: '深圳' }])
  .selected(this.idx).value('北京').font({ size: 16 })
  .onSelect((index: number, text?: string) => { this.idx = index })   // SelectOption 文本字段为 value（非 label）
```
⚠ 选项少且要弹层确认感也可 bindMenu；Select 的 on veiled 事件名核对：onSelect(index, text)（text 可选，d.ts 以 onSelect((index: number, value?: string)) 形态——字段顺序已核对）。

## A-4 表单与指示器

### A28. SeekBar → Slider
```kotlin
seekBar.setOnSeekBarChangeListener(object: OnSeekBarChangeListener{ onProgressChanged{…} })
```
```ts
Slider({ value: 50, min: 0, max: 100, step: 1, style: SliderStyle.OutSet })
  .showTips(true).blockColor('#FF5B7CF6')
  .onChange((v: number, mode: ChangeMode) => { if (mode === ChangeMode.End) this.commit(v) })
```
⚠ onChange 带 mode（Start/Moving/End）——只认松手值用 ChangeMode.End 过滤，比 Android 干净。

### A29. Switch → Switch
```kotlin
switch.setOnCheckedChangeListener { _, c -> vm.setNotify(c) }
```
```ts
Switch({ isOn: this.on }).selectedColor('#FF34C759')
  .onChange((v: boolean) => { this.on = v; this.vm.setNotify(v) })
```
⚠ isOn 单向初值；无受控回写问题（与 Checkbox 不同，Switch onChange 后 UI 自切）〔CM §28〕。

### A30. CheckBox → Checkbox
```kotlin
checkBox.setOnCheckedChangeListener{ _, c -> todo.done = c }
```
```ts
Checkbox().select(this.item.done).onChange((v: boolean) => this.vm.toggle(this.item.id))
// 多选组：CheckboxGroup({ group: 'fruits' }).onChange((v, items) => …)  ≈ 全选/反选
```
⚠ select 是**单向初值**，乐观更新需自持 @Local 态防闪变；勾选形状 `.shape(CircleShape)`〔CM §27、05 §2〕。

### A31. RadioGroup + RadioButton → Radio + RadioContainer
```kotlin
radioGroup.setOnCheckedChangeListener{ _, id -> when(id){ R.id.rb1 -> … } }
```
```ts
RadioContainer() {
  Radio({ value: '高', group: 'prio' }).checked(this.prio === '高')
  Radio({ value: '中', group: 'prio' }).checked(this.prio === '中')
}.onChange((v: string) => this.prio = v)     // 回调直接给 value 字符串
```
⚠ Radio 必须同 group 名；onChange 返回的是 value 串（不是 index）。

### A32. ProgressBar / CircularProgressIndicator → Progress
```xml
<ProgressBar style="?android:attr/progressBarStyleHorizontal" android:progress="60"/>
<ProgressBar/>   <!-- 不确定旋转 -->
```
```ts
Progress({ value: 60, total: 100, type: ProgressType.Linear })      // 水平条
LoadingProgress().width(36).height(36).color('#FF5B7CF6')            // 不定旋转（≈ 小菊花）
Progress({ value: 24, type: ProgressType.Capsule })                  // 胶囊形（鸿蒙特色）
```
⚠ 不确定进度没有"旋转圈 ProgressBar"对应物——LoadingProgress 是官方部件〔06〕。

---

# B. 系统与平台能力层

## B-1 生命周期与路由

### B1. Activity 生命周期 → 组件生命周期 + UIAbility 生命周期（双轨）
```kotlin
class DetailActivity : AppCompatActivity() {
  override fun onCreate(b: Bundle?) { … }     override fun onResume() { … }
  override fun onPause() { … }                override fun onDestroy() { … }
}
```
```ts
// ArkUI 是"UIAbility(窗口容器) + 页面组件"双轨：
@Entry @ComponentV2 struct DetailPage {
  aboutToAppear(): void { … }      // ≈ onCreate（首次创建，先于 build）
  onPageShow(): void { … }         // ≈ onResume（页面可见，含路由返回）
  onPageHide(): void { … }         // ≈ onPause（页面不可见）
  aboutToDisappear(): void { … }   // ≈ onDestroy
}
// UIAbility（≈ Application+Activity 容器合体）：onCreate→onWindowStageCreate→onForeground→onBackground→onDestroy
```
⚠ 两大坑：① **onPageShow 在每次路由返回都触发**（Android onResume 等价，刷新数据放这里）；② 组件销毁不等于 Ability 销毁——重资源释开放 aboutToDisappear，Ability 级放 onBackground。savedInstanceState 无对应→PersistentStorage〔CM §57〕。

### B2. startActivity + Intent → NavPathStack.pushPathByName（首选）/ router.pushUrl
```kotlin
startActivity(Intent(this, DetailActivity::class.java).putExtra("id", 42))
```
```ts
// 首选 Navigation 体系（官方主推，带转场/拦截全）：
this.pathStack.pushPathByName('detail', { id: 42 })      // params 为普通对象（需 interface 类型，见 D-6）
// 旧 router（@ohos.router，简单页可用）：
router.pushUrl({ url: 'pages/Detail', params: { id: 42 } })
```
⚠ 页面需在 resources/base/profile/route_map.json 注册（Navigation）或 main_pages.json（router）；Intent 的 action/data/filter 语义→want 或 App Linking（B-14）。

### B3. startActivityForResult → 回调注入 / router events
```kotlin
registerForActivityResult(StartActivityForResult()){ r -> if(r.resultCode == RESULT_OK) … }
```
```ts
// Navigation 无内置 result API（待验证）。惯用法 A——参数对象携带回调：
this.pathStack.pushPathByName('detail', { id: 42, onDeleted: (id: number): void => this.vm.delete(id) } as DetailParam)
// detail 页返回前调 params.onDeleted?.(this.id)；惯用法 B——@ohos.events.emitter 事件总线（跨层级）
```
⚠ 完整模式（含 300ms 延迟删除惯用）见 CM §64〔11 §emitter〕。

### B4. onBackPressed → onBackPress / NavDestination.onBackPressed
```kotlin
override fun onBackPressed() { if (selectionMode) exitSelection() else super.onBackPressed() }
```
```ts
// @Entry 页面：
onBackPress(): boolean {           // 返回 true = 消费，不退出
  if (this.vm.isSelecting) { this.vm.clearSelection(); return true }
  return false
}
// NavDestination 内：
NavDestination(){ … }.onBackPressed((): boolean => { …; return true })
```
⚠ 返回手势（侧滑）同走路由；Navigation 内 NavDestination 的 onBackPressed 优先于页面 onBackPress〔CM §63、03〕。

### B5. finish() → pop
```kotlin
finish()
```
```ts
this.pathStack.pop()                    // Navigation
router.back()                           // router
```

## B-2 数据与存储

### B6. SharedPreferences → @ohos.data.preferences
```kotlin
val sp = getSharedPreferences("settings", MODE_PRIVATE)
sp.edit().putString("theme", "dark").putBoolean("notify", true).apply()
val t = sp.getString("theme", "light")
```
```ts
import { preferences } from '@kit.ArkData';
let p: preferences.Preferences = preferences.getPreferencesSync(this.context, { name: 'settings' })
p.putSync('theme', 'dark'); p.putSync('notify', true); p.flush()   // flush 落盘 ≈ apply
let t: string = p.getSync('theme', 'light') as string              // getSync 返回 ValueType，需 as
```
⚠ 异步版 getPreferences(ctx, name): Promise；**put 不 flush 不持久**（apply≈flush）；轻量 KV 官方另有 @ohos.data.storage（已废弃并入 preferences，勿用）。高频小状态可用 PersistentStorage 直通 AppStorage〔CM §57、11 §preferences〕。

### B7. Room（Entity/DAO/Database）→ @ohos.data.relationalStore
```kotlin
@Entity data class Todo(@PrimaryKey(autoGenerate=true) val id:Int=0, var title:String, var done:Boolean=false)
@Dao interface TodoDao { @Insert suspend fun insert(t:Todo): Long
  @Query("SELECT * FROM todo WHERE done=0") suspend fun active(): List<Todo> }
@Database(entities=[Todo::class], version=1) abstract class AppDB: RoomDatabase()
```
```ts
import { relationalStore } from '@kit.ArkData';
// ① 建库建表（≈ RoomDatabaseBuilder + onCreate migration 手写）
let db: relationalStore.RdbStore = await relationalStore.getRdbStore(this.context, { name: 'app.db', securityLevel: relationalStore.SecurityLevel.S1 })
db.executeSql('CREATE TABLE IF NOT EXISTS todo (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, done INTEGER DEFAULT 0)')
// ② 插入（insert 返回 rowId）
let rowId: number = await db.insert('todo', { title: '买牛奶', done: 0 } as relationalStore.ValuesBucket)
// ③ 查询（RdbPredicates ≈ @Query WHERE；无注解生成，结果手遍历）
let rs: relationalStore.ResultSet = await db.query(new relationalStore.RdbPredicates('todo').equalTo('done', 0).orderByAsc('id'))
while (rs.goToNextRow()) { let title: string = rs.getString(rs.getColumnIndex('title')) }
rs.close()      // 必须手动关！
// ④ 更删
db.update({ done: 1 } as relationalStore.ValuesBucket, new relationalStore.RdbPredicates('todo').equalTo('id', 42))
db.delete(new relationalStore.RdbPredicates('todo').equalTo('id', 42))
```
⚠ 四大差异：① 无 ORM 映射——ResultSet 手动取值手转 Todo[]；② 无 Flow/LiveData——改完**重新 query 手动刷 UI**（VM 里 reload）〔CM §61〕；③ 事务 `db.beginTransaction()/commit()/rollBack()`（try-finally 包）；④ 升级迁移手写 onVersion。键值小数据先问 preferences 够不够〔11 §RelationalStore〕。

### B8. FileProvider + content:// → 沙箱路径直接用
```kotlin
FileProvider.getUriForFile(ctx, authority, file); Intent(Intent.ACTION_VIEW).setDataAndType(uri, "image/*")
```
```ts
// 鸿蒙无 content:// 暴露机制：应用沙箱路径直接给 API/Want
import { fileIo } from '@kit.CoreFileKit';
let path: string = this.context.filesDir + '/a.png'      // 沙箱内路径直接读写
// 系统分享/打开：want 带 uri(file://沙箱路径) 或调系统能力（如 photoAccessHelper 存图）
```
⚠ 跨应用共享文件用系统 Picker（photoAccessHelper.PhotoViewPicker 等）而不是自建 Provider；具体分享 Want 参数**待验证**〔11 §文件沙箱〕。

## B-3 后台与调度

### B9. WorkManager → @ohos.resourceschedule.workScheduler
```kotlin
WorkManager.enqueue(OneTimeWorkRequestBuilder<SyncWorker>().setConstraints(Constraints.Builder().setRequiresCharging(true).build()).build())
```
```ts
import { workScheduler } from '@kit.BackgroundTasksKit';
workScheduler.startWork({
  workId: 1, taskType: workScheduler.WorkType.NETWORK,           // 延迟后台任务须 NETWORK 型
  bundleName: 'com.example.app', abilityName: 'SyncAbility',     // 回调落在该 ExtensionAbility
  isRepeat: false, networkType: workScheduler.NetworkType.NETWORK_ANY
} as workScheduler.WorkInfo)
workScheduler.stopWork({ workId: 1 } as workScheduler.WorkInfo)
```
⚠ 鸿蒙**无 WorkerManager 式任意后台执行**——延迟任务要求 `taskType: NETWORK` 且由系统统管（最小间隔约束）；确需后台跑→长时任务（backgroundTaskManager，需场景化权限+通知）或 Agent 优先。Worker 参数细节**待验证**（WorkInfo 完整字段以 d.ts 为准）。

### B10. AlarmManager → @ohos.reminderAgentManager（代理提醒）
```kotlin
AlarmManager.setExactAndAllowWhileIdle(RTC_WAKEUP, time, pi)
```
```ts
import { reminderAgentManager } from '@kit.BackgroundTasksKit';
let id: number = await reminderAgentManager.publishReminder({
  reminderType: reminderAgentManager.ReminderType.REMINDER_TYPE_CALENDAR,  // 日历/闹钟/倒计时三类
  … // ReminderRequestCalendar 字段（dateTime/repeatMonths 等，细节待验证）
} as reminderAgentManager.ReminderRequest)
// 取消：reminderAgentManager.cancelReminder(id)
```
⚠ 精确闹钟语义被"代理提醒"收编（系统统一排程，应用被杀也响）；需通知权限配合；纯本地 setTimeout 不可靠。字段细节**待验证**。

### B11. NotificationCompat → @ohos.notificationManager
```kotlin
NotificationCompat.Builder(ctx, CH).setSmallIcon(R.drawable.ic).setContentTitle("T").setContentText("…").build()
```
```ts
import { notificationManager } from '@kit.NotificationKit';
await notificationManager.requestEnableNotification(this.context)          // 先申请开关
notificationManager.publish({
  id: 1, content: {
    notificationContentType: notificationManager.ContentType.NOTIFICATION_CONTENT_BASIC_TEXT,
    normal: { title: '待办提醒', text: '该买牛奶了', additionalText: '' }
  }
} as notificationManager.NotificationRequest)
```
⚠ 发通知前**必须 requestEnableNotification**（用户授权开关，仅首次弹）；渠道→-notificationManager 无 channel 概念（有 slot，一般不用手动建）。字段名 NOTIFICATION_CONTENT_BASIC_TEXT 已按 d.ts 常见形态，**待验证枚举字面量**〔12〕。

## B-4 硬件与感知

### B12. Vibrator → @ohos.vibrator
```kotlin
vibrator.vibrate(VibrationEffect.createPredefined(VibrationEffect.EFFECT_CLICK))
```
```ts
import { vibrator } from '@kit.SensorServiceKit';
vibrator.startVibration({ type: 'preset', effectId: 'haptic.clock.timer', count: 1 } as vibrator.VibratePreset,
  { id: 0, usage: 'touch' } as vibrator.VibrateAttribute)
```
⚠ 权限 `ohos.permission.VIBRATE`；effectId 预设表**待验证**（haptic.clock.timer 等字符串以官方文档枚举为准）〔CM 附表〕。

### B13. SensorManager → @ohos.sensor
```kotlin
sensorManager.getDefaultSensor(Sensor.TYPE_ACCELEROMETER)
sensorManager.registerListener(ls, sensor, SAMPLING)
```
```ts
import { sensor } from '@kit.SensorServiceKit';
sensor.on(sensor.SensorId.ACCELEROMETER, (d: sensor.AccelerometerResponse) => {
  this.x = d.x; this.y = d.y; this.z = d.z      // SI 单位 m/s²
});
// 一次性：sensor.once(sensor.SensorId.ACCELEROMETER, cb)；注销：sensor.off(sensor.SensorId.ACCELEROMETER)
```
⚠ 回调频率由 interval 参数控制（默认游戏级）；摇一摇阈值判定逻辑照抄 Android。SensorId 枚举已核对（ACCELEROMETER/AMBIENT_LIGHT/…）。

## B-5 平台机制

### B14. 深链接 scheme/intent-filter → App Linking（module.json5 skills）
```xml
<intent-filter><action VIEW/><category DEFAULT/><data android:scheme="myapp" android:host="detail"/></intent-filter>
```
```json
// module.json5 → abilities[].skills（应用内 want 路由）：
"skills": [{ "actions": ["ohos.want.action.viewData"], "uris": [{ "scheme": "myapp", "host": "detail" }] }]
// 页面侧在 aboutToAppear 里取参：this.getUIContext().getHostContext()… want.parameters（细节待验证）
```
⚠ 跨应用点击 → want 分发进 UIAbility.onNewWant（单实例）/onCreate（冷启）；https 域名校验的 Deep Linking（App Linking，需华为后台配置域名 asset）**待验证流程**。

### B15. 运行时权限 → abilityAccessCtrl.requestPermissionsFromUser
```kotlin
ActivityCompat.requestPermissions(this, arrayOf(Manifest.permission.CAMERA), 1)
onRequestPermissionsResult { … }
```
```ts
import { abilityAccessCtrl, Permissions } from '@kit.AbilityKit';
let at: abilityAccessCtrl.AtManager = abilityAccessCtrl.createAtManager()
let res = await at.requestPermissionsFromUser(this.context,
  ['ohos.permission.READ_CALENDAR', 'ohos.permission.WRITE_CALENDAR'] as Permissions)
if (res.authResults.every((r: number): boolean => r === 0)) { /* 0=授予 */ }
```
⚠ 权限串在 module.json5 `requestPermissions` 声明（同 Manifest）；拒绝两次弹系统"不再询问"→ 需 `at.requestPermissionOnSetting`（API 12，待验证）引导跳设置。results 里 -1=拒绝。

### B16. dp/px/sp → vp/px/fp 换算
```kotlin
val px = dp * resources.displayMetrics.density
```
```ts
// vp≈dp（布局默认单位，数字即 vp）；fp≈sp（fontSize 默认）
let px: number = vp2px(24); let v: number = px2vp(720)   // 全局函数，随屏幕密度
// 百分比：.width('50%')；资源尺寸 $r('app.float.size_16') 也是 vp
```
⚠ 逻辑分辨率：设计稿按 1vp=1px(720×1280 基准) 换算；**代码里拼接单位字符串是错的**（`'24vp'` 仅资源/样式串合法，属性数值直接写 number）。

### B17. Application/Context → Context 层级
```kotlin
class App : Application() { val db = buildDb() }   // 全局单例入口
```
```ts
// 无 Application 类：AbilityStage（模块级生命周期，entryability 前触发）+ 全局单例直接模块导出
// export const appDb: Db = createDb()   // 模块级单例（懒初始化用方触发）
// Context：UIAbilityContext（页面 this.getUIContext().getHostContext()，含 filesDir/资源）
//   / Context（Stage 模型 skills 透传）……UIAbility.context 静态可达（待验证推荐入口）
```
⚠ 全局单例模块导出即常驻（恰好满足"切 Tab 保状态"）；Context 用途对照：filesDir≈filesDir、resourceManager≈Resources、createBundleContext≈createBundleContext（跨包）。

### B18. WebView JS 桥（addJavascriptInterface）→ registerJavaScriptProxy
```kotlin
webView.addJavascriptInterface(bridgeObj, "Native")
```
```ts
this.ctrl.registerJavaScriptProxy(bridgeObj, 'Native', ['save', 'load'])   // 必须列方法白名单
Web({ src: …, controller: this.ctrl }).javaScriptProxy(…)                  // 或属性式配置
```
⚠ 方法名数组白名单必填；调用时机需 onControllerAttached 后 refresh。字段**待验证**〔ArkWeb 文档〕。

---

# C. 交互与视觉模式层

### C1. Ripple 水波纹 → stateStyles(pressed) / clickEffect
```xml
android:background="?attr/selectableItemBackground"
```
```ts
// 官方按压反馈两件套：
Button('保存').stateStyles({ pressed: this.pressedStyle })   // @Styles pressedStyle(){ .opacity(0.7).scale(0.98) }
Image(ic).clickEffect({ scale: 0.9, level: 1 })              // 轻量级：按压缩放
```
⚠ 鸿蒙**无 ripple 涟漪动画内建**；系统默认 stateEffect（按钮自带按压）；自定义涟漪=半径动画自绘（成本高，不推荐）；clickEffect 的 level 1/2/3 = 轻中重。〔12 §多态样式〕

### C2. elevation 阴影 → shadow 属性
```xml
android:elevation="8dp"   <!-- Z 轴投影 -->
```
```ts
.shadow({ radius: 12, color: 'rgba(0,0,0,0.10)', offsetX: 0, offsetY: 4 })
```
⚠ 无 Z 轴层级语义——elevation 同时管"层级+投影"，ArkUI 层级由**组件声明顺序/Stack 叠放**决定，shadow 只管视觉；阴影颜色必须带 alpha 否则黑块〔12 §阴影〕。

### C3. Material 主题色（theme overlay）→ 资源 token 化
```xml
<style name="Theme.App" parent="Theme.Material3"><item name="colorPrimary">@color/brand</item></style>
```
```ts
// 无全局 Theme 注入机制：官方模式=资源层 token 化 + 逐组件引用
// resources/base/element/color.json: { "name": "brand", "value": "#FF5B7CF6" }
Button('保存').backgroundColor($r('app.color.brand'))
// 深浅色差异值放 dark 限定词目录同名资源（见 C4），运行时自动切换
```
⚠ 没有"改一处全局生效"的 MaterialTheme；封装 @Styles/@Builder 统一取色可减少散点〔10 §Styles〕。

### C4. values-night 暗色模式 → colorMode 限定词资源目录
```
res/values-night/themes.xml  →  resources/dark/element/color.json（API 12 目录名 dark）
res/values/…                →  resources/base/element/…
```
```ts
// 资源同名覆盖：base/color.json brand=#FF5B7CF6；dark/color.json brand=#FF8FA8FF
// 代码感知：this.getUIContext().getHostContext()!.config.colorMode（待验证链式入口；官方 Application.colorMode）
// 跟随系统：默认跟随；ConfigurationConstant.ColorMode 常量判定
```
⚠ 目录名：API 12+ 是 `resources/dark/`（旧 `resources/dark/element` 结构一致）；**AppStorage 里 colorMode 有系统键注入**（'colorMode'，待验证）；JS 侧硬编码色在暗色下不跟切——尽量 $r 引用。

### C5. 矢量 drawable → SVG 资源 / SymbolGlyph（HM Symbol）
```xml
<vector drawable: ic_add.xml>  /  drawableTint
```
```ts
Image($r('app.media.ic_add')).fillColor($r('app.color.brand'))   // SVG 染色（fillColor 仅对 svg 生效）
SymbolGlyph($r('sys.symbol.plus')).fontSize(28)                   // 系统谐波符号（≈ Material Icons 官方库）
  .fontColor([$r('app.color.brand')]).fontWeight(400)
```
⚠ VectorDrawable XML **不通用**——须转标准 SVG 放 resources/base/media（文件名即资源名）；图标优先用 sys.symbol 官方符号库（数千枚、自动适配深浅色与字重）；位图染色 colorBlend（API 10，待验证）〔06 §SymbolGlyph〕。

### C6. .9 点九图 → .9 图支持 / resizable(slice)
```xml
<image android:src="@drawable/bubble.9.png"/>
```
```ts
// 鸿蒙支持 .9 图：文件命名 xxx.9.png 放 media 目录，Image 直接用（API 版本待验证）
Image($r('app.media.bubble')).objectFit(ImageFit.Fill)
// 代码级拉伸（≈ nine-patch slice 语义）：Image.resizable({ slice: { left, top, right, bottom } })   // d.ts 已核对存在
```
⚠ resizable 的 ResizableOptions 字段（slice 四边数值）**待验证精确形态**；气泡/按钮拉伸背景更推荐 .9 图或 border+borderRadius 组合。

### C7. SpannableString 富文本 → Text 内 Span 家族
```kotlin
textView.text = SpannableString("已删 3 项").apply { setSpan(ForegroundColorSpan(red), 0, 2, …) }
```
```ts
Text() {
  Span('已删 ').fontColor('#FF666666').fontSize(14)
  Span('3').fontColor('#FFF44336').fontWeight(FontWeight.Bold).fontSize(18)
  ImageSpan($r('app.media.ic_check')).width(16).verticalAlign(ImageSpanAlignment.CENTER)
  SymbolSpan($r('sys.symbol.checkmark'))     // 符号 span
}
```
⚠ Span 只能在 Text 内、不能独立用；高亮子串点击（ClickableSpan）→ Span.onClick（待验证）或整段拆多个 Text〔04 §Span、CM §20〕。

### C8. 触摸事件分发（onInterceptTouchEvent）→ nestedScroll 协商 + 手势优先级
```kotlin
parent.setOnInterceptTouchListener { … }   // 父拦截子手势（横向滑删 vs 纵向滚动）
```
```ts
// 滚动嵌套协商：List 属性（API 10）
List().nestedScroll({ scrollForward: NestedScrollMode.SELF_FIRST, scrollBackward: NestedScrollMode.SELF_FIRST })
// 多手势冲突：gesture 挂法决定优先级
.gesture(GestureGroup(GestureMode.Exclusive, panX, panY))      // 互斥
.priorityGesture(panX, parallelGesture(tap))                   // 主/并行
```
⚠ 无"事件先给父再问子"的拦截链模型——ArkUI 按手势识别仲裁；滑删方向冲突系统已处理（swipeAction 内建）〔09 §手势仲裁、02 §nestedScroll〕。

### C9. ObjectAnimator → animateTo / @AnimatableExtend
```kotlin
ObjectAnimator.ofFloat(view, "translationY", 0f, 100f).setDuration(300).start()
```
```ts
this.getUIContext().animateTo({ duration: 300, curve: Curve.EaseOut }, () => { this.offsetY = 100 })
// 使用：.offset({ y: this.offsetY })
// 属性驱动型（链式隐式，≈ XML propertyAnimator）：.offset({y:this.y}).animation({duration:300})
```
⚠ "target 属性联动"用隐式 `.animation()`（更贴近）；多属性协同改@Local 后一个 animateTo 闭包全包〔CM §49-50、09〕。

### C10. ValueAnimator（进度驱动）→ keyframeAnimateTo / animatableArithmetic
```kotlin
ValueAnimator.ofFloat(0f,1f).addUpdateListener{ a -> view.alpha = a.animatedValue }
```
```ts
this.getUIContext().animateTo({duration:400}, () => this.p = 1)      // p 即进度值，UI 绑 p 计算
// 关键帧：keyframeAnimateTo({iterations:1}, [ {value:0, duration:0}, {value:0.5, duration:200, curve:…}, … ])
```
⚠ 无 addUpdateListener 回调型动画——把进度值做成 @Local 状态，UI 表达式引用它即逐帧更新；连续自定义插值用 @ohos.curves 或 animatableArithmetic（自定义算术域，09 §B）。

### C11. shared_element 过渡 → sharedTransition / geometryTransition
```kotlin
supportFragmentManager.beginTransaction().addSharedElement(iv, "hero").commit()
```
```ts
// router 页面间：两端同 key
Image(src).sharedTransition('hero', { duration: 500, curve: Curve.EaseInOut })
// Navigation/同页（官方主推）：geometryTransition(key)
Image(src).geometryTransition('hero')
```
⚠ Navigation 体系用 geometryTransition；sharedTransition 主要服务 router〔CM §55、09 §sharedTransition〕。

### C12. LayoutTransition / view.animate() → transition / 隐式 animation
```kotlin
view.animate().alpha(0f).translationY(-20f).setDuration(200)
```
```ts
// 进出场动画：if 分支 + transition（两件套）
if (this.visible) { Panel().transition(TransitionEffect.OPACITY.combine(TransitionEffect.translate({ y: -20 })).animation({ duration: 200 })) }
// 属性微动：直接隐式 animation
Panel().opacity(this.o).offset({ y: this.oy }).animation({ duration: 200 })
```
⚠ if/else 挂 transition + 外层 animateTo 切 visible 缺一不可〔CM §51/54、09 §transition〕。

---

# D. 踩坑速查（本项目实战提炼，附正确代码）

### D-1. CalendarPickerDialog：必须静态 show()，确认回调叫 onAccept
```ts
// ✗ 错：new CalendarPickerDialog(...).open()；✗ 错：onConfirm/onDateSet
// ✓ 对（d.ts 已核对：static show(options)，onAccept?: Callback<Date>）：
CalendarPickerDialog.show({
  selected: this.due,
  onAccept: (d: Date): void => { this.due = d }      // onAccept 才是"确定"
})
// 另有 onChange（选择即回调，未点确定也触发）——只想要确定值别用 onChange
```

### D-2. bindSheet 的 SheetOptions 无 onDismiss → 用 $$ 双向绑定感知关闭
```ts
// ✗ 错：bindSheet(..., { onDismiss: () => … })   // d.ts 无此字段（有 shouldDismiss/onWillDismiss 拦截型，API 12+）
// ✓ 对：$$ 绑定 + @Monitor 监听值变化：
@Local showSheet: boolean = false
@Monitor('showSheet') onSheetChange(): void {
  if (!this.showSheet) this.afterSheetClosed()      // 关闭后逻辑
}
Column(){ … }.bindSheet($$this.showSheet, this.sheetBuilder(), { detents: [SheetSize.MEDIUM] })
```
⚠ 需拦截"用户下滑关闭"时用 `shouldDismiss: (sheetDismiss: SheetDismiss) => { sheetDismiss.dismiss() }`（d.ts 已核对存在，API 12+）。

### D-3. MenuItem：options 只有 {content}，事件挂 .onClick
```ts
// ✗ 错：MenuItem({ content: '删除', value: 1, action: () => del() })   // 无 value/action 字段
// ✓ 对（d.ts 已核对 MenuItemOptions.content?: ResourceStr）：
MenuItem({ content: '删除' }).onClick((): void => this.del())
MenuItem({ content: '置顶' }).selected(this.pinned).onClick((): void => this.pin())
```

### D-4. TextPicker onChange 签名是双联合类型
```ts
// ✗ 错：onChange((v: string) => …)   // 编译过但单选时拿到 string；多选炸
// ✓ 对（d.ts 已核对：((value: string | string[], index: number | number[]) => void)）：
TextPicker({ range: this.cities }).onChange((v: string | string[], i: number | number[]): void => {
  this.city = Array.isArray(v) ? v[0] : v
})
```

### D-5. arkts-no-implicit-return-types：回调/方法必须显式 (): void / (): string
```ts
// ✗ 错：onClick(() => this.del())   // 严格 ArkTS 报 no-implicit-return-types（部分链路）
// ✓ 对：
.onClick((): void => this.del())
@Builder item() { … }
function fmt(v: number): string { return `第${v}天` }
```

### D-6. ArkTS 严格模式三连（no-any / no-untyped-literal / 字面量须接口）
```ts
// ✗ 错：let p: any = {…};  let u = { name: 'a', age: 1 };  pushPathByName('d', { id: 1 })
// ✓ 对：
interface DetailParam { id: number; onDeleted?: (id: number) => void }
let u: UserInfo = { name: 'a', age: 1 }                       // 对象字面量必须有 interface/class 类型
this.pathStack.pushPathByName('detail', { id: 1 } as DetailParam)
let n: number = 1                                             // 禁 any/unknown 兜底
```
⚠ 路由 params、emit 事件 data、ValuesBucket 都是重灾区——一律 as Interface 或显式类型。

### D-7. V2 装饰器混用禁令
```ts
// ✗ 错：@Entry @ComponentV2 struct P { @State a: number = 0 }        // V2 组件里禁用 V1 状态装饰器
//        @Observed class M {}  与  @ObservedV2/@Trace 混用
// ✓ 对（本项目统一 V2）：
@Entry @ComponentV2 struct P {
  @Local a: number = 0                  // 组件内状态
  @Param item: Todo = …                 // 父传子（V2 版 @Prop+@Link 合体语义）
  @Monitor('a') onA(): void { … }       // 观察变化
}
@ObservedV2 class TodoVM { @Trace todos: Todo[] = [] }
```
⚠ @Local/@Param/@Monitor/@Computed 只在 V2；@Link/@Prop/@State/@Provide 属 V1。整页 V2 化是新迁移推荐姿势〔10 §V2〕。

---

# 附录：鸿蒙无直接对应的 Android 组件清单（及官方替代模式）

| Android 组件 | 鸿蒙状况 | 原生替代模式 |
|---|---|---|
| FloatingActionButton | 无 FAB 组件 | 首选 NavDestination/Navigation `.menus()` 操作按钮（HM Design 主操作进顶栏）；确需悬浮→Stack 叠加 Circle Button（A-20、CM §29） |
| MaterialCardView | 无卡片组件 | Column + borderRadius + backgroundColor(+shadow/border/clip) 官方组合（A-21） |
| CoordinatorLayout+AppBarLayout+CollapsingToolbar | 无滚动联动容器 | Scroll/List onDidScroll + @State 联动自绘顶栏（A-16、playbook） |
| Chip | 无 Chip 组件 | 胶囊自绘（Text+borderRadius）/ SegmentButton（A-5） |
| Snackbar（带 Action） | Toast 无按钮 | 自绘底部横幅或改交互模式（A-22） |
| TabLayout + ViewPager2 + Mediator | 无 mediator 概念 | Tabs 一体化（barPosition Start）（A-19） |
| RecyclerView ItemAnimator 全家 | 部分支持 | animateTo 包数据通知；重排位移动画待验证（A-13） |
| Ripple 涟漪 | 无内建涟漪 | stateStyles(pressed)/clickEffect + 系统 stateEffect（C-1） |
| Material Theme（colorPrimary 全局注入） | 无全局主题机制 | 资源 token 化 $r('app.color.x') + dark 限定词目录（C-3/C-4） |
| ContentProvider/FileProvider | 无跨应用内容提供方 | 系统 Picker + 沙箱路径 + want（B-8） |
| WorkManager（任意后台任务） | 严格收编 | workScheduler（NETWORK 型）+ 长时任务 + 代理提醒（B-9/B-10） |
| Intent filter action/data 泛化 | want 定向 | skills uris + App Linking（B-14） |
| Handler/Looper | 无消息循环心智 | TaskPool/Worker + emitter（〔11〕） |

## 与既有知识库的引用关系
- Compose 侧同组件映射：一律先查 compose-mapping.md（65 条，CM §n 编号引用）
- 深度模板：01 布局 / 02 列表滚动 / 03 导航 / 04 文本输入 / 05 按钮选择 / 06 信息展示 / 07 弹窗菜单 / 08 媒体图形 / 09 手势动画 / 10 状态管理 / 11 线程数据 / 12 杂项（0n 编号引用）
- 页面级完整方案：home-page-playbook.md

## 待验证条目汇总（实施代理使用前查官方文档核对）
1. A-1 Text `.accessibilityText()` 属性名
2. A-5 SegmentButton（advanced 组件库）精确签名
3. A-7 Stack 子级 `.align()` API 10 起可用性
4. A-13 onDataMove 重排位移动画效果
5. A-25 bindTimePicker 存在性；TimePicker onChange 参数顺序（h, m）
6. A-27 Select onSelect 第二参数（value?: string）语义
7. B-2 route_map.json 注册 Navigation 页面的配置形态
8. B-8 跨应用文件分享 Want 精确参数
9. B-9 WorkInfo 完整字段约束（isPersisted/networkType…）
10. B-10 ReminderRequestCalendar 完整字段
11. B-11 notification ContentType 枚举字面量（NOTIFICATION_CONTENT_BASIC_TEXT）
12. B-12 VibratePreset effectId 预设表
13. B-14 App Linking https 域名配置流程；want 取参链式入口
14. B-15 requestPermissionOnSetting（API 12）
15. B-17 UIAbility.context 全局获取推荐入口
16. B-18 registerJavaScriptProxy 白名单/refresh 时机
17. C-4 AppStorage 'colorMode' 系统注入键
18. C-6 .9 图 API 版本与 resizable slice 字段形态
19. C-7 Span.onClick 可点击 span 支持性

> 以上 19 处标"待验证"均不影响选型结论（有保底方案）；实施时以 DevEco 官方文档 + 本地 d.ts 二次核对为准。
## 图标映射（Material Icons → HarmonyOS SymbolGlyph，2026-09-01 增补）

R8 红线的执行依据。SymbolGlyph 用 `sys.symbol.*` 资源（DevEco SDK 内置，无需导入图片资源）。

| Android Material Icon | 用途 | 鸿蒙 SymbolGlyph | 备注 |
|---|---|---|---|
| ic_add / Add | 添加 | `sys.symbol.plus` | 添加订阅/FAB |
| ic_menu / Menu | 汉堡菜单 | `sys.symbol.line_3_horizontal` | 侧边栏开关 |
| ic_arrow_back | 返回 | `sys.symbol.chevron_left` | 导航返回 |
| ic_done / CheckCircle | 已读标记 | `sys.symbol.circle`（filled/solid 区分） | 已读=描边圆，未读=实心圆（或用 checkmark 切换） |
| ic_star / StarBorder | 星标 | `sys.symbol.star` / `sys.symbol.star_slash` | 星标切换 |
| ic_delete | 删除 | `sys.symbol.trash` | 列表项删除 |
| ic_refresh | 刷新 | `sys.symbol.arrow_clockwise` | 下拉刷新/手动刷新 |
| ic_settings | 设置 | `sys.symbol.gearshape` | 设置入口 |
| ic_search | 搜索 | `sys.symbol.magnifyingglass` | 搜索 |
| ic_share | 分享 | `sys.symbol.square_and_arrow_up` | 分享 |
| ic_open_in_new / OpenInBrowser | 浏览器打开 | `sys.symbol.arrow_up_right_square` | 阅读页"Open in Browser" |
| ic_close | 关闭 | `sys.symbol.xmark` | 对话框关闭 |
| ic_list | 列表/目录 | `sys.symbol.list_bullet` | 目录 |
| ic_person / Account | 账号 | `sys.symbol.person` | 账号 |
| ic_filter_list | 过滤 | `sys.symbol.line_3_horizontal_decrease` | 过滤器 |

> 完整可用图标集：DevEco Studio → HarmonyOS Symbol 库（或 SDK `systemres` 中 `sys.symbol.*`）。若某个图标无精确对应，用语义最接近的 + 书面记录（不算豁免 R8）。
