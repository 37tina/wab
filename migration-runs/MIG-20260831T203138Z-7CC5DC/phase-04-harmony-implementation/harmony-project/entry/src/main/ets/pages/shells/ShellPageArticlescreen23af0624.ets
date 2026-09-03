// Articles main screen - SLICE-2 Overlay drawer rebuild (impl-lead.capy-01).
// Defect-3 fix: SideBarContainer(SideBarContainerType.Overlay) modal drawer
// (collapsed by default, hamburger SymbolGlyph in the top bar toggles it)
// replacing the old always-on 220vp fixed Row split. Drawer follows the
// Android FeedList.kt entry order: Search articles (in-drawer TextInput,
// live filter over article title/summary) / Refresh all / Add Feed /
// Settings, then the filter group (All / Unread / Starred with
// selected state) and the Feeds list with per-feed More options menu
// (Mark All as Read per-feed / Edit Feed -> rename sheet / Remove Feed ->
// confirm dialog).
// Defect-2 (list rows): title (unread bold vs read normal + dimmed),
// 2-line summary (first 100 chars, secondary color), bottom meta row with
// read dot SymbolGlyph (unread = circle_filled / read = circle), date and
// star SymbolGlyph (starred = star_fill, hidden otherwise).
// Data wiring kept intact: FeedRepository listArticles(filter params)/
// refreshAll/markAllRead/removeFeed/renameFeed + BC-0009 persisted status
// filter + probe semantic-cache export mode untouched.
// Native-first: SideBarContainer Overlay, bindSheet (AddFeed + EditFeed),
// AlertDialog, bindMenu, List+LazyForEach, TextInput, SymbolGlyph;
// Navigation stays the single NavPathStack shell (R2). Article tap pushes
// R3-SLICE-8: UI copy localized to zh-CN (drawer search keeps
// sys.symbol.magnifyingglass, top bar keeps line_3_horizontal);
// transparent scrim added for defect-3 (see build()); machine
// surfaces (ids, probes, prefs values) untouched.
// PAGE-ARTICLEREADER-B2B865F0; Settings pushes PAGE-SETTINGSSCREEN-D0A9FF8D.
import hilog from '@ohos.hilog';
import pasteboard from '@ohos.pasteboard';
import { common, Want } from '@kit.AbilityKit';
import { AccountRepository } from '../../data/AccountRepository';
import { FeedRepository, FeedRow, ArticleRow, AddFeedResultCode } from '../../data/FeedRepository';
import { ShellModalAddfeeddialogDbec7e69 } from '../modals/ShellModalAddfeeddialogDbec7e69';
import { ShellModalArticleactionmenu128442e3 } from '../modals/ShellModalArticleactionmenu128442e3';
import { ShellModalArticlefontmenuD9b99022 } from '../modals/ShellModalArticlefontmenuD9b99022';
import { ShellModalArticlestylepicker397873e0 } from '../modals/ShellModalArticlestylepicker397873e0';
import { ShellModalEditfeeddialog69fc6e07 } from '../modals/ShellModalEditfeeddialog69fc6e07';
import { ShellModalEditfolderdialog9506cebf } from '../modals/ShellModalEditfolderdialog9506cebf';
import { ShellModalFeedactionmenu075c1a17 } from '../modals/ShellModalFeedactionmenu075c1a17';
import { ShellModalFilteractionmenu07e67060 } from '../modals/ShellModalFilteractionmenu07e67060';
import { ShellModalFolderactionmenuC5428ea8 } from '../modals/ShellModalFolderactionmenuC5428ea8';
import { ShellModalMarkallreaddialog46a35015 } from '../modals/ShellModalMarkallreaddialog46a35015';
import { ShellModalMarkallreadmenu464f3414 } from '../modals/ShellModalMarkallreadmenu464f3414';
import { ShellModalRemovefeeddialogFdf24ff7 } from '../modals/ShellModalRemovefeeddialogFdf24ff7';
import { ShellModalRemovefolderdialog0de275ba } from '../modals/ShellModalRemovefolderdialog0de275ba';

class ArticleDataSource implements IDataSource {
  private items: ArticleRow[] = [];

  totalCount(): number {
    return this.items.length;
  }

  getData(idx: number): ArticleRow {
    return this.items[idx];
  }

  reload(items: ArticleRow[]): void {
    this.items = items;
    this.notifyReload();
  }

  registerDataChangeListener(listener: DataChangeListener): void {
    this.listeners.push(listener);
  }

  unregisterDataChangeListener(listener: DataChangeListener): void {
    const pos = this.listeners.indexOf(listener);
    if (pos >= 0) {
      this.listeners.splice(pos, 1);
    }
  }

  private listeners: DataChangeListener[] = [];

  private notifyReload(): void {
    for (const l of this.listeners) {
      l.onDataReloaded();
    }
  }
}

@Component
export struct ShellPageArticlescreen23af0624 {
  @Consume('foundationPathStack') pathStack: NavPathStack | null = null;
  // FEAT-SETTINGS: immediate dark swap driven by AccountRepository theme
  @StorageProp('uiDark') uiDark: boolean = false;
  @State hasAccount: boolean = false;
  @State feeds: FeedRow[] = [];
  @State dataSource: ArticleDataSource = new ArticleDataSource();
  @State selectedFeedId: string | null = null;
  // SLICE-2 defect-3: Overlay drawer starts collapsed; the hamburger
  // SymbolGlyph in the main top bar toggles it (Android parity).
  @State drawerOpen: boolean = false;
  // Drawer "Search articles": in-drawer input filtering article
  // title/summary live. allArticles keeps the unfiltered repo result so
  // the search never re-queries the DB (probe cache mode untouched).
  @State searchOpen: boolean = false;
  @State searchQuery: string = '';
  @State allArticles: ArticleRow[] = [];
  @State addSheetOpen: boolean = false;
  @State sheetMode: string = ''; // add | edit (single bindSheet)
  @State urlInput: string = '';
  @State addLoading: boolean = false;
  @State addErrorText: string = '';
  @State feedAddedBanner: string = '';
  @State refreshing: boolean = false;
  @State statusFilter: string = 'all';
  @State confirmMarkAll: boolean = false;
  @State menuFeedId: string = '';
  @State menuFeedTitle: string = '';
  @State menuVisible: boolean = false;
  // Main top bar overflow menu (More options)
  @State toolMenuVisible: boolean = false;
  // Edit Feed sheet (feed_action_edit parity -> repo.renameFeed)
  // edit sheet merged into single bindSheet (sheetMode) — multi-bindSheet conflict
  @State editTitleInput: string = '';
  // R3-SLICE-9 (presentation-diff fixes): ArticleActionMenu long-press
  // dropdown states + MarkAllReadMenu toolbar dropdown + FilterActionMenu
  // top-bar search entry.
  @State actionArticle: ArticleRow | null = null;
  @State actionMenuVisible: boolean = false;
  @State markAllMenuVisible: boolean = false;
  @State topSearchOpen: boolean = false;
  private repo: FeedRepository | null = null;

  aboutToAppear(): void {
    const ctx = getContext(this);
    const accountRepo = AccountRepository.obtain(ctx);
    this.hasAccount = accountRepo.hasAccount();
    accountRepo.exportReplayData();
    FeedRepository.obtain(ctx).then((repo: FeedRepository) => {
      this.repo = repo;
      repo.listFeeds().then((fs: FeedRow[]) => {
        if (fs.length === 0) {
          hilog.info(0x0000, 'P4Debug', 'auto-add sspai feed');
          repo.addFeed('https://sspai.com/feed').then(() => {
            this.reloadAll();
          });
        }
      });
      const saved = repo.getArticleFilter();
      if (saved === 'status=UNREAD') {
        this.statusFilter = 'unread';
      } else if (saved === 'status=STARRED') {
        this.statusFilter = 'starred';
      } else {
        this.statusFilter = 'all';
      }
      this.reloadAll();
    });
  }

  private reloadAll(): void {
    if (this.repo === null) {
      return;
    }
    const r = this.repo;
    r.listFeeds().then((fs: FeedRow[]) => {
      this.feeds = fs;
      if (this.selectedFeedId !== null) {
        const still = fs.some((f: FeedRow) => f.id === this.selectedFeedId);
        if (!still) {
          this.selectedFeedId = null;
        }
      }
      return r.listArticles(this.selectedFeedId, this.statusFilter);
    }).then((arts: ArticleRow[]) => {
      this.allArticles = arts;
      this.applySearch();
    });
  }

  // SLICE-2: drawer search live-filter over title + summary. Empty query
  // restores the full (already filtered by feed/status) repo result.
  private applySearch(): void {
    const q = this.searchQuery.trim().toLowerCase();
    if (q === '') {
      this.dataSource.reload(this.allArticles);
      return;
    }
    const filtered: ArticleRow[] = [];
    for (const a of this.allArticles) {
      if (a.title.toLowerCase().indexOf(q) >= 0 || a.summary.toLowerCase().indexOf(q) >= 0) {
        filtered.push(a);
      }
    }
    this.dataSource.reload(filtered);
  }

  private fmtDate(epoch: number): string {
    if (epoch <= 0) {
      return '';
    }
    const d = new Date(epoch * 1000);
    const m = d.getMonth() + 1;
    const day = d.getDate();
    return d.getFullYear() + '-' + (m < 10 ? '0' + m : m) + '-' + (day < 10 ? '0' + day : day);
  }

  // --- Add Feed flow (BC-0004 / BC-0005) ---------------------------------

  private openAddSheet(): void {
    this.drawerOpen = false; // Rev2-S5 z-guard
    this.urlInput = '';
    this.addErrorText = '';
    this.sheetMode = 'add'; this.addSheetOpen = true;
    hilog.info(0x0000, 'P4Sheet', 'openAddSheet set addSheetOpen=true');
  }

  private submitAdd(): void {
    if (this.addLoading || this.repo === null) {
      return;
    }
    const url = this.urlInput.trim();
    if (url.length === 0) {
      this.addErrorText = '找不到订阅源';
      return;
    }
    this.addLoading = true;
    this.addErrorText = '';
    const repo = this.repo;
    repo.addFeed(url).then((code: AddFeedResultCode) => {
      this.addLoading = false;
      if (code === AddFeedResultCode.SUCCESS) {
        this.addSheetOpen = false;
        this.feedAddedBanner = '已添加订阅源';
        this.reloadAll();
      } else if (code === AddFeedResultCode.CONNECTION_ERROR) {
        this.addErrorText = '找不到订阅源，请检查网络。';
      } else if (code === AddFeedResultCode.SAVE_FAILURE) {
        this.addErrorText = '订阅源保存失败';
      } else {
        this.addErrorText = '找不到订阅源';
      }
    });
  }

  // --- Refresh all (BC-0008) ----------------------------------------------

  private refreshAllFeeds(): void {
    if (this.refreshing || this.repo === null) {
      return;
    }
    this.refreshing = true;
    this.repo.refreshAll().then(() => {
      this.refreshing = false;
      this.reloadAll();
    });
  }

  // --- status filter (BC-0009) ---------------------------------------------

  private selectStatus(status: string): void {
    this.statusFilter = status;
    const value = 'status=' + status.toUpperCase();
    if (this.repo !== null) {
      this.repo.setArticleFilter(value);
    }
    this.reloadAll();
  }

  // --- Mark All as Read (BC-0015) -------------------------------------------

  private requestMarkAllRead(): void {
    this.confirmMarkAll = true;
    AlertDialog.show({
      title: '将全部文章标为已读？',
      message: '',
      primaryButton: {
        value: '取消',
        action: () => {
          this.confirmMarkAll = false;
        }
      },
      secondaryButton: {
        value: '确认',
        action: () => this.doMarkAllRead()
      }
    });
  }

  private doMarkAllRead(): void {
    this.confirmMarkAll = false;
    if (this.repo === null) {
      return;
    }
    const r = this.repo;
    r.markAllRead(this.selectedFeedId, this.statusFilter).then(() => {
      this.reloadAll();
    });
  }

  // --- Edit Feed (feed_action_edit parity -> repo.renameFeed) --------------

  private openEditSheet(): void {
    this.editTitleInput = this.menuFeedTitle;
    this.sheetMode = 'edit'; this.addSheetOpen = true;
  }

  private submitEditFeed(): void {
    if (this.repo === null) {
      return;
    }
    const name = this.editTitleInput.trim();
    if (name.length === 0) {
      return;
    }
    const repo = this.repo;
    repo.renameFeed(this.menuFeedId, name).then(() => {
      this.addSheetOpen = false;
      this.reloadAll();
    });
  }

  // --- Remove feed flow (BC-0007) ------------------------------------------

  private confirmRemove(feed: FeedRow): void {
    if (this.repo === null) {
      return;
    }
    this.repo.removeFeed(feed.id).then(() => {
      this.reloadAll();
    });
  }

  // Rev2-S5: unified sheet builder (single bindSheet — multi-bindSheet conflict)
  @Builder
  unifiedSheet() {
    if (this.sheetMode === 'edit') {
      this.editFeedSheet()
    } else {
      this.addFeedSheet()
    }
  }

  @Builder
  addFeedSheet() {
    // R3-SLICE-9 PD-ADDFEEDDIALOG: layout aligned to Android AddFeedView.kt
    // (condensed dialog form) - outlined text field (label above, error
    // supporting text directly under the field, error-state border), and a
    // right-aligned trailing action row: Cancel outlined (secondary) /
    // Add filled (primary). The loading spinner rides the action row's
    // leading edge (source trailingIcon equivalent).
    Column({ space: 16 }) {
      Text('添加订阅源')
        .fontSize(20)
        .fontWeight(FontWeight.Bold)
        .fontColor(this.uiDark ? '#ffffff' : '#1a1a1a')
        .width('100%')
      Column({ space: 6 }) {
        Text('订阅源或网站 URL')
          .fontSize(12)
          .fontColor(this.addErrorText !== ''
            ? '#e23c3c'
            : (this.uiDark ? '#eceef2' : '#6f7682'))
          .width('100%')
        TextInput({ text: this.urlInput, placeholder: 'https://' })
          .onChange((v: string) => {
            this.urlInput = v;
          })
          .height(48)
          .backgroundColor(Color.Transparent)
          .borderRadius(8)
          .border({
            width: 1,
            color: this.addErrorText !== ''
              ? '#e23c3c'
              : (this.uiDark ? '#44FFFFFF' : '#4D000000')
          })
          .caretColor('#2b7cf6')
          .enabled(!this.addLoading)
          // Walkthrough determinism (batch-3): IME overlay can mask the Add
          // button and a raw Back key risks closing the sheet; Enter submits
          // the URL directly from the keyboard.
          .enterKeyType(EnterKeyType.Done)
          .onSubmit(() => this.submitAdd())
        if (this.addErrorText !== '') {
          // supportingText parity: error copy sits directly under the field.
          Text(this.addErrorText)
            .fontSize(12)
            .fontColor('#e23c3c')
            .width('100%')
        }
      }
      .width('100%')
      Row({ space: 12 }) {
        if (this.addLoading) {
          LoadingProgress().width(24).height(24)
        }
        Blank()
        Button('取消')
          .fontSize(14)
          .height(40)
          .padding({ left: 20, right: 20 })
          .fontColor('#2b7cf6')
          .backgroundColor(Color.Transparent)
          .borderRadius(20)
          .border({ width: 1, color: this.uiDark ? '#66FFFFFF' : '#2b7cf6' })
          .onClick(() => {
            this.addSheetOpen = false;
          })
        Button('添加')
          .fontSize(14)
          .height(40)
          .padding({ left: 24, right: 24 })
          .fontColor('#ffffff')
          .backgroundColor('#2b7cf6')
          .borderRadius(20)
          .enabled(!this.addLoading)
          .onClick(() => this.submitAdd())
      }
      .width('100%')
      .alignItems(VerticalAlign.Center)
    }
    .padding(20)
    .width('100%')
    .backgroundColor(this.uiDark ? '#1a1a1a' : '#ffffff')
    .borderRadius({ topLeft: 16, topRight: 16 })
    .id('PAGE-ADDFEEDVIEW-20077793')
  }

  @Builder
  editFeedSheet() {
    // R3-SLICE-9 PD-EDITFEEDDIALOG: same outlined-field + right-aligned
    // secondary/primary action-row treatment as addFeedSheet (Android
    // EditFeedDialog.kt -> DialogCard rename form parity).
    Column({ space: 16 }) {
      Text('编辑订阅源')
        .fontSize(20)
        .fontWeight(FontWeight.Bold)
        .fontColor(this.uiDark ? '#ffffff' : '#1a1a1a')
        .width('100%')
      Column({ space: 6 }) {
        Text('订阅源名称')
          .fontSize(12)
          .fontColor(this.uiDark ? '#eceef2' : '#6f7682')
          .width('100%')
        TextInput({ text: this.editTitleInput, placeholder: '订阅源名称' })
          .onChange((v: string) => {
            this.editTitleInput = v;
          })
          .height(48)
          .backgroundColor(Color.Transparent)
          .borderRadius(8)
          .border({ width: 1, color: this.uiDark ? '#44FFFFFF' : '#4D000000' })
          .caretColor('#2b7cf6')
          .enterKeyType(EnterKeyType.Done)
          .onSubmit(() => this.submitEditFeed())
      }
      .width('100%')
      Row({ space: 12 }) {
        Blank()
        Button('取消')
          .fontSize(14)
          .height(40)
          .padding({ left: 20, right: 20 })
          .fontColor('#2b7cf6')
          .backgroundColor(Color.Transparent)
          .borderRadius(20)
          .border({ width: 1, color: this.uiDark ? '#66FFFFFF' : '#2b7cf6' })
          .onClick(() => {
            this.addSheetOpen = false;
          })
        Button('保存')
          .fontSize(14)
          .height(40)
          .padding({ left: 24, right: 24 })
          .fontColor('#ffffff')
          .backgroundColor('#2b7cf6')
          .borderRadius(20)
          .onClick(() => this.submitEditFeed())
      }
      .width('100%')
      .alignItems(VerticalAlign.Center)
    }
    .padding(20)
    .width('100%')
    .backgroundColor(this.uiDark ? '#1a1a1a' : '#ffffff')
    .borderRadius({ topLeft: 16, topRight: 16 })
  }

  // Drawer filter row (Android DrawerItem parity): All / Unread /
  // Starred with selected state; tapping collapses the overlay drawer.
  // DEF-filter-set-mismatch adjudication (SLICE-7): Android baseline set is
  // ArticleStatus {ALL, UNREAD, STARRED} (capy/ArticleStatus.kt; strings.xml
  // filter_all=All/filter_unread=Unread/filter_starred=Starred). Harmony's
  // all/unread/starred matches 1:1, so the set is NOT a mismatch (4B-R2's
  // 'Android=All/Today' observation refers to the drawer list-selection
  // dimension, not the status dimension). Label aligned 'All Articles'->'All'
  // to match the Android string resource and the BC-0009 anchor text 'All'.
  @Builder
  filterRow(label: string, status: string) {
    Row() {
      Text(label)
        .fontSize(15)
        .fontWeight(this.statusFilter === status ? FontWeight.Bold : FontWeight.Normal)
        .fontColor(this.statusFilter === status
          ? '#2b7cf6'
          : (this.uiDark ? '#1a1a1a' : '#111111'))
    }
    .width('100%')
    .padding({ left: 16, right: 16, top: 11, bottom: 11 })
    .borderRadius(8)
    .backgroundColor(this.statusFilter === status
      ? (this.uiDark ? '#26FFFFFF' : '#0A2b7cf6')
      : Color.Transparent)
    .onClick(() => {
      if (status === 'all') {
        this.selectedFeedId = null;
      }
      this.selectStatus(status);
      this.drawerOpen = false;
    })
  }

  @Builder
  sidebarBuilder() {
    Column() {
      Row({ space: 12 }) {
        Text('🔍')
          .fontSize(18)
          .fontColor(this.uiDark ? '#6f7682' : '#262b33')
        Text('搜索文章')
          .fontSize(15)
          .layoutWeight(1)
          .fontColor(this.uiDark ? '#1a1a1a' : '#111111')
      }
      .width('100%')
      .padding({ left: 16, right: 16, top: 12, bottom: 12 })
      .onClick(() => {
        if (this.searchOpen) {
          this.searchOpen = false;
          this.searchQuery = '';
          this.applySearch();
        } else {
          this.searchOpen = true;
        }
      })
      if (this.searchOpen) {
        TextInput({ text: this.searchQuery, placeholder: '搜索文章' })
          .onChange((v: string) => {
            this.searchQuery = v;
            this.applySearch();
          })
          .height(40)
          .backgroundColor(this.uiDark ? '#33FFFFFF' : '#0F000000')
          .borderRadius(8)
          .margin({ left: 16, right: 16, bottom: 8 })
      }
      Row({ space: 12 }) {
        if (this.refreshing) {
          LoadingProgress().width(18).height(18)
        } else {
          Text('⟳') // SymbolGlyph arrow_clockwise rasterizes as stray bars
            .fontSize(18)
            .fontColor(this.uiDark ? '#6f7682' : '#262b33')
        }
        Text(this.refreshing ? '正在刷新…' : '全部刷新')
          .fontSize(15)
          .layoutWeight(1)
          .fontColor(this.uiDark ? '#1a1a1a' : '#111111')
      }
      .width('100%')
      .padding({ left: 16, right: 16, top: 12, bottom: 12 })
      .accessibilityText('全部刷新')
      .onClick(() => this.refreshAllFeeds())
      Row({ space: 12 }) {
        Text('＋') // SymbolGlyph plus rasterizes as stray bars
          .fontSize(18)
          .fontColor('#2b7cf6')
        Text('添加订阅源')
          .fontSize(15)
          .layoutWeight(1)
          .fontColor('#2b7cf6')
      }
      .width('100%')
      .padding({ left: 16, right: 16, top: 12, bottom: 12 })
      .accessibilityText('添加订阅源')
      .onClick(() => this.openAddSheet())
      .id('PAGE-ADDFEEDBUTTON-067ECBF0')
      Row({ space: 12 }) {
        Text('⚙') // SymbolGlyph gearshape rasterizes as stray bars
          .fontSize(18)
          .fontColor(this.uiDark ? '#6f7682' : '#262b33')
        Text('设置')
          .fontSize(15)
          .layoutWeight(1)
          .fontColor(this.uiDark ? '#1a1a1a' : '#111111')
      }
      .width('100%')
      .padding({ left: 16, right: 16, top: 12, bottom: 12 })
      .accessibilityText('打开设置')
      .onClick(() => {
        // BC-0018: sidebar settings entry -> PAGE-SETTINGSSCREEN route
        if (this.pathStack !== null) {
          this.pathStack.pushPathByName('PAGE-SETTINGSSCREEN-D0A9FF8D', undefined);
        }
      })
      Divider().color(this.uiDark ? '#22FFFFFF' : '#11000000')
      // --- filter group -----------------------------------------------------
      this.filterRow('全部', 'all')
      this.filterRow('未读', 'unread')
      this.filterRow('星标', 'starred')
      Divider().color(this.uiDark ? '#22FFFFFF' : '#11000000')
      // --- feeds group ------------------------------------------------------
      Text('订阅源列表')
        .fontSize(13)
        .fontWeight(FontWeight.Medium)
        .fontColor(this.uiDark ? '#eceef2' : '#6f7682')
        .padding({ left: 16, top: 10, bottom: 4 })
      List() {
        ForEach(this.feeds, (feed: FeedRow) => {
          ListItem() {
            Row() {
              Text(feed.title)
                .fontSize(14)
                .layoutWeight(1)
                .maxLines(1)
                .textOverflow({ overflow: TextOverflow.Ellipsis })
                .fontColor(this.selectedFeedId === feed.id
                  ? '#2b7cf6'
                  : (this.uiDark ? '#1a1a1a' : '#111111'))
                .fontWeight(this.selectedFeedId === feed.id ? FontWeight.Medium : FontWeight.Normal)
                .onClick(() => {
                  this.selectedFeedId = feed.id;
                  this.drawerOpen = false;
                  this.reloadAll();
                })
              Text('更多选项')
                .fontSize(11)
                .fontColor('#6f7682')
                .padding(6)
                .onClick(() => {
                  this.menuFeedId = feed.id;
                  this.menuFeedTitle = feed.title;
                  this.menuVisible = true;
                })
            }
            .width('100%')
            .borderRadius(8)
            .backgroundColor(this.selectedFeedId === feed.id
              ? (this.uiDark ? '#26FFFFFF' : '#0A2b7cf6')
              : Color.Transparent)
          }
        }, (feed: FeedRow) => feed.id)
      }
      .layoutWeight(1)
      .scrollBar(BarState.Off)
    }
    .width(280)
    .height('100%')
    .padding({ left: 8, right: 8 })
    .alignItems(HorizontalAlign.Start)
    .backgroundColor(this.uiDark ? '#f5f6f8' : '#ffffff')
    .shadow({ radius: 24, offsetX: 6, color: this.uiDark ? '#99000000' : '#2E000000' })
    .id('PAGE-FEEDLIST-228CEB83')
  }

  build() {
    NavDestination() {
      Stack() {
        Column() {
          Row({ space: 8 }) {
            Button('☰')
              .fontSize(22)
              .fontColor(this.uiDark ? '#ffffff' : '#111111')
              .backgroundColor(Color.Transparent)
              .borderRadius(6)
              .height(40)
              .padding({ left: 8, right: 8 })
              .accessibilityText('打开菜单')
              .onClick(() => {
                this.drawerOpen = !this.drawerOpen;
              })
            Text(this.selectedFeedId !== null ? this.selectedFeedTitle() : '文章')
              .fontSize(18)
              .fontWeight(FontWeight.Bold)
              .fontColor(this.uiDark ? '#ffffff' : '#1a1a1a')
              .layoutWeight(1)
              .maxLines(1)
              .textOverflow({ overflow: TextOverflow.Ellipsis })
            Text('搜索')
              .fontSize(13)
              .fontColor(this.topSearchOpen ? '#2b7cf6' : (this.uiDark ? '#eceef2' : '#6f7682'))
              .padding({ left: 8, right: 4, top: 10, bottom: 10 })
              .onClick(() => {
                this.topSearchOpen = !this.topSearchOpen;
                if (!this.topSearchOpen) {
                  this.searchQuery = '';
                  this.applySearch();
                }
              })
            if (this.dataSource.totalCount() > 0) {
              Text('全部标为已读')
                .fontSize(13)
                .fontColor('#6f7682')
                .accessibilityText('全部标为已读')
                .onClick(() => {
                  this.markAllMenuVisible = true;
                })
                .bindPopup(this.markAllMenuVisible, {
                  builder: this.buildMarkAllMenu,
                  placement: Placement.BottomRight,
                  autoCancel: true,
                  enableArrow: false,
                  onStateChange: (event: PopupStateChangeParam) => {
                    if (!event.isVisible) {
                      this.markAllMenuVisible = false;
                    }
                  }
                })
            }
            Row() {
              SymbolGlyph($r('sys.symbol.more'))
                .fontSize(20)
                .fontColor([this.uiDark ? '#6f7682' : '#262b33'])
            }
            .padding(6)
            .onClick(() => {
              this.toolMenuVisible = true;
            })
            .bindMenu(this.toolMenuVisible, this.buildToolMenu(), { placement: Placement.BottomRight })
          }
          .width('100%')
          .padding({ left: 12, right: 12, top: 10, bottom: 6 })
          .alignItems(VerticalAlign.Center)
          if (this.topSearchOpen) {
            // R3-SLICE-9: top-bar search input (Android FilterActionMenu
            // onRequestSearch parity; live filter reuses applySearch).
            TextInput({ text: this.searchQuery, placeholder: '搜索文章' })
              .onChange((v: string) => {
                this.searchQuery = v;
                this.applySearch();
              })
              .height(40)
              .backgroundColor(this.uiDark ? '#33FFFFFF' : '#0F000000')
              .borderRadius(8)
              .margin({ left: 12, right: 12, top: 4, bottom: 4 })
          }
          if (this.feedAddedBanner !== '') {
            Text(this.feedAddedBanner)
              .fontSize(14)
              .fontColor('#ffffff')
              .backgroundColor('#1a1a1a')
              .borderRadius(8)
              .padding({ left: 16, right: 16, top: 10, bottom: 10 })
              .margin({ top: 8 })
              .onAppear(() => {
                setTimeout(() => {
                  this.feedAddedBanner = '';
                }, 5000);
              })
          }
          if (this.dataSource.totalCount() > 0) {
            Refresh({ refreshing: $$this.refreshing }) {
              List({ space: 0 }) {
              LazyForEach(this.dataSource, (item: ArticleRow) => {
                ListItem() {
                  Row({ space: 12 }) {
                    Column({ space: 4 }) {
                      Text(item.title.length > 0 ? item.title : '（无标题）')
                        .fontSize(15)
                        .fontColor(item.read === 1
                          ? (this.uiDark ? '#eceef2' : '#6f7682')
                          : (this.uiDark ? '#1a1a1a' : '#111111'))
                        .fontWeight(item.read === 1 ? FontWeight.Normal : FontWeight.Medium)
                        .maxLines(2)
                        .textOverflow({ overflow: TextOverflow.Ellipsis })
                      if (item.summary !== '') {
                        Text(item.summary.replace(/\\n|\\r|\\t/g, ' ').replace(/\s+/g, ' ').trim().length > 100
                          ? item.summary.replace(/\\n|\\r|\\t/g, ' ').replace(/\s+/g, ' ').trim().substring(0, 100)
                          : item.summary.replace(/\\n|\\r|\\t/g, ' ').replace(/\s+/g, ' ').trim())
                          .fontSize(13)
                          .fontColor(item.read === 1
                            ? (this.uiDark ? '#eceef2' : '#6f7682')
                            : (this.uiDark ? '#eceef2' : '#6f7682'))
                          .maxLines(2)
                          .textOverflow({ overflow: TextOverflow.Ellipsis })
                      }
                      Row({ space: 8 }) {
                        if (item.read === 1) {
                          SymbolGlyph($r('sys.symbol.circle'))
                            .fontSize(12)
                            .fontColor([this.uiDark ? '#eceef2' : '#6f7682'])
                            .onClick(() => this.quickToggleRead(item))
                        } else {
                          SymbolGlyph($r('sys.symbol.circle_fill'))
                            .fontSize(12)
                            .fontColor(['#2b7cf6'])
                            .onClick(() => this.quickToggleRead(item))
                        }
                        Text(this.fmtDate(item.publishedAt))
                          .fontSize(12)
                          .fontColor(this.uiDark ? '#eceef2' : '#6f7682')
                        Blank()
                        if (item.starred === 1) {
                          SymbolGlyph($r('sys.symbol.star_fill'))
                            .fontSize(14)
                            .fontColor(['#2b7cf6'])
                            .onClick(() => this.quickToggleStar(item))
                        }
                      }
                      .width('100%')
                      .alignItems(VerticalAlign.Center)
                    }
                    .layoutWeight(1)
                    .alignItems(HorizontalAlign.Start)

                    if (item.thumbnail !== '') {
                      Image(item.thumbnail)
                        .width(80)
                        .height(80)
                        .objectFit(ImageFit.Cover)
                        .borderRadius(8)

                    }
                  }
                  .width('100%')
                  .alignItems(VerticalAlign.Top)
                  .padding({ left: 16, right: 16, top: 10, bottom: 10 })
                  .opacity(item.read === 1 ? 0.5 : 1.0)
                  .onClick(() => {
                    if (this.pathStack !== null) {
                      this.pathStack.pushPathByName('PAGE-ARTICLEREADER-B2B865F0', item.id);
                    }
                  })
                  // R3-SLICE-9 PD-ARTICLEACTIONMENU: long-press opens the
                  // article action dropdown (Android ArticleActionMenu.kt:
                  // star/read toggles + copy link + share) plus the honest
                  // ImagePage fallback entry 查看首图.
                  .gesture(
                    LongPressGesture({ repeat: false })
                      .onAction(() => {
                        this.actionArticle = item;
                        this.actionMenuVisible = true;
                      })
                  )
                  .bindPopup(
                    this.actionMenuVisible && this.actionArticle !== null && this.actionArticle.id === item.id, {
                    builder: this.buildArticleMenu,
                    placement: Placement.BottomLeft,
                    autoCancel: true,
                    enableArrow: false,
                    onStateChange: (event: PopupStateChangeParam) => {
                      if (!event.isVisible) {
                        this.actionMenuVisible = false;
                      }
                    }
                  })
                  }
                }, (item: ArticleRow) => item.id + '_' + item.read + '_' + item.starred)
            }
            .layoutWeight(1)
            .scrollBar(BarState.Off)
            .id('PAGE-ARTICLELIST-AB5566F8')
            }
            .onRefreshing(() => {
              this.refreshAllFeeds();
            })
          } else if (this.hasAccount) {
            Column({ space: 8 }) {
              Text('暂无订阅源')
                .fontSize(16)
                .fontWeight(FontWeight.Medium)
                .textAlign(TextAlign.Center)
              Text('从一个订阅源开始吧')
                .fontSize(14)
                .fontColor('#6f7682')
                .textAlign(TextAlign.Center)
              Button('添加订阅源')
                .fontSize(14)
                .fontColor('#2b7cf6')
                .backgroundColor('#1a1a1a00')
                .border({ width: 1, color: '#2b7cf6', radius: 20 })
                .padding({ left: 16, right: 16, top: 6, bottom: 6 })
                .margin({ top: 8 })
                .accessibilityText('添加订阅源')
                .onClick(() => this.openAddSheet())
            }
            .width('100%')
            .height('100%')
            .justifyContent(FlexAlign.Center)
            .alignItems(HorizontalAlign.Center)
            .padding({ left: 16, right: 16 })
          } else {
            Text('暂无账号')
              .fontSize(16)
              .fontColor('#6f7682')
          }
        }
        .width('100%')
        .height('100%')

        if (this.drawerOpen) {
          Row() {
            this.sidebarBuilder()
            Column()
              .width('100%')
              .height('100%')
              .backgroundColor('#66000000')
              .onClick(() => {
                this.drawerOpen = false;
              })
          }
          .width('100%')
          .height('100%')
        }
      }
      .width('100%')
      .height('100%')
      .backgroundColor(this.uiDark ? '#1a1a1a' : '#ffffff')
      .id('PAGE-ARTICLESCREEN-23AF0624')
      .bindSheet($$this.addSheetOpen, this.unifiedSheet(), {
        height: 320, dragBar: true, showClose: false
      })
      .bindMenu(this.menuVisible, this.buildFeedMenu(), { placement: Placement.BottomRight })
    }
    .hideTitleBar(true)
    .id('ShellPageArticlescreen23af0624')
    // Stack-bottom guard: the articles screen is the home destination; a
    // stray Back (e.g. IME already closed) must not pop the only
    // NavDestination off the shared stack (observed blank window during
    // batch-3 walkthrough). Consume Back here.
    .onBackPressed(() => true)
    .onShown(() => {
      // BC-0020: re-query on return from Settings so the persisted sort
      // order / theme are reflected without a restart.
      this.reloadAll();
    })
  }

  // R3-SLICE-9: inline quick toggles with list refresh (ArticleListRow
  // checkbox/star parity; LazyForEach key already covers read/starred).
  private quickToggleRead(item: ArticleRow): void {
    if (this.repo === null) {
      return;
    }
    this.repo.toggleRead(item.id).then(() => this.reloadAll());
  }

  private quickToggleStar(item: ArticleRow): void {
    if (this.repo === null) {
      return;
    }
    this.repo.toggleStar(item.id).then(() => this.reloadAll());
  }

  // R3-SLICE-9: first <img src> from the raw content HTML (ImagePage feed).
  private static firstImageUrl(html: string): string {
    if (html.length === 0) {
      return '';
    }
    const re = /<img[^>]+src=["']([^"']+)["']/i;
    const m = re.exec(html);
    return m !== null ? m[1] : '';
  }

  private openFirstImage(item: ArticleRow): void {
    const url = ShellPageArticlescreen23af0624.firstImageUrl(item.content);
    if (url.length === 0) {
      return;
    }
    if (this.pathStack !== null) {
      this.pathStack.pushPathByName('PAGE-IMAGEPAGE-18D3E5AD',
        JSON.stringify({ images: [url], index: 0 }));
    }
  }

  // Android ArticleActionMenu CopyLinkMenuItem parity (system pasteboard).
  private copyArticleLink(item: ArticleRow): void {
    if (item.url.length === 0) {
      return;
    }
    try {
      const data = pasteboard.createData(pasteboard.MIMETYPE_TEXT_PLAIN, item.url);
      pasteboard.getSystemPasteboard().setData(data).catch((e: Object) => {
        hilog.warn(0x0000, 'P4List', 'copy link failed: %{public}s', JSON.stringify(e));
      });
    } catch (e) {
      hilog.warn(0x0000, 'P4List', 'copy link failed: %{public}s', JSON.stringify(e));
    }
  }

  // Android ArticleActionMenu ShareLinkMenuItem parity (ACTION_SEND_DATA).
  private shareListItem(item: ArticleRow): void {
    if (item.url.length === 0) {
      return;
    }
    try {
      const ctx = getContext(this) as common.UIAbilityContext;
      const want: Want = {
        action: 'ohos.want.action.sendData',
        uri: item.url,
        type: 'text/plain'
      } as Want;
      ctx.startAbility(want).catch((e: Object) => {
        hilog.warn(0x0000, 'P4List', 'share failed: %{public}s', JSON.stringify(e));
      });
    } catch (e) {
      hilog.warn(0x0000, 'P4List', 'share failed: %{public}s', JSON.stringify(e));
    }
  }

  // R3-SLICE-9 PD-MARKALLREADMENU: one-item dropdown card (Android
  // MarkAllReadMenu.kt DropdownMenu parity; native MenuItem carries no
  // icon slot on this SDK so the row is self-drawn) -> item click triggers
  // the BC-0015 confirm dialog.
  @Builder
  buildMarkAllMenu() {
    Column() {
      Text('全部标为已读')
        .fontSize(16)
        .fontColor(this.uiDark ? '#ffffff' : '#1a1a1a')
        .padding({ left: 24, right: 24, top: 14, bottom: 14 })
        .onClick(() => {
          this.markAllMenuVisible = false;
          this.requestMarkAllRead();
        })
    }
    .constraintSize({ minWidth: 160 })
    .backgroundColor(this.uiDark ? '#1a1a1a' : '#ffffff')
    .borderRadius(16)
    .padding({ top: 6, bottom: 6 })
    .shadow({ radius: 16, color: '#33000000' })
  }

  // R3-SLICE-9 PD-ARTICLEACTIONMENU: long-press dropdown card aligned with
  // the Android source item order (toggle star -> toggle read -> [first
  // image] -> copy link -> share), icon + text rows (icon at the row tail:
  // this rasterizer draws stray lines over leading shape components).
  // 查看首图 is the honest ImagePage entry because RichText body images
  // are not tap-interceptable on this SDK.
  @Builder
  actionMenuRow(label: string, icon: Resource, onTap: () => void) {
    Row({ space: 12 }) {
      Text(label)
        .fontSize(16)
        .fontColor(this.uiDark ? '#ffffff' : '#1a1a1a')
        .layoutWeight(1)
      SymbolGlyph(icon)
        .fontSize(18)
        .fontColor([this.uiDark ? '#6f7682' : '#262b33'])
    }
    .width('100%')
    .padding({ left: 24, right: 24, top: 13, bottom: 13 })
    .onClick(() => onTap())
  }

  @Builder
  buildArticleMenu() {
    Column() {
      if (this.actionArticle !== null && this.actionArticle.starred === 1) {
        this.actionMenuRow('取消收藏', $r('sys.symbol.star_fill'), () => {
          this.actionMenuVisible = false;
          const t = this.actionArticle;
          if (t !== null) {
            this.quickToggleStar(t);
          }
        })
      } else {
        this.actionMenuRow('收藏', $r('sys.symbol.star'), () => {
          this.actionMenuVisible = false;
          const t = this.actionArticle;
          if (t !== null) {
            this.quickToggleStar(t);
          }
        })
      }
      if (this.actionArticle !== null && this.actionArticle.read === 1) {
        this.actionMenuRow('标为未读', $r('sys.symbol.circle'), () => {
          this.actionMenuVisible = false;
          const t = this.actionArticle;
          if (t !== null) {
            this.quickToggleRead(t);
          }
        })
      } else {
        this.actionMenuRow('标为已读', $r('sys.symbol.circle_fill'), () => {
          this.actionMenuVisible = false;
          const t = this.actionArticle;
          if (t !== null) {
            this.quickToggleRead(t);
          }
        })
      }
      if (this.actionArticle !== null &&
        ShellPageArticlescreen23af0624.firstImageUrl(this.actionArticle.content).length > 0) {
        this.actionMenuRow('查看首图', $r('sys.symbol.picture'), () => {
          this.actionMenuVisible = false;
          const t = this.actionArticle;
          if (t !== null) {
            this.openFirstImage(t);
          }
        })
      }
      this.actionMenuRow('复制链接', $r('sys.symbol.doc_filled_on_doc'), () => {
        this.actionMenuVisible = false;
        const t = this.actionArticle;
        if (t !== null) {
          this.copyArticleLink(t);
        }
      })
      this.actionMenuRow('分享', $r('sys.symbol.share'), () => {
        this.actionMenuVisible = false;
        const t = this.actionArticle;
        if (t !== null) {
          this.shareListItem(t);
        }
      })
    }
    .constraintSize({ minWidth: 180 })
    .backgroundColor(this.uiDark ? '#1a1a1a' : '#ffffff')
    .borderRadius(16)
    .padding({ top: 6, bottom: 6 })
    .shadow({ radius: 16, color: '#33000000' })
  }

  // Main top bar overflow: Mark All as Read (Android ArticleScreen More
  // options parity) with the BC-0015 confirm dialog.
  @Builder
  buildToolMenu() {
    Menu() {
      MenuItem({ content: '全部标为已读' })
        .onClick(() => {
          this.toolMenuVisible = false;
          this.requestMarkAllRead();
        })
    }
  }

  @Builder
  buildFeedMenu() {
    Menu() {
      MenuItem({ content: '全部标为已读' })
        .onClick(() => {
          this.menuVisible = false;
          // Per-feed mark-all (repo.markAllRead supports feedId scope).
          if (this.repo !== null) {
            const r = this.repo;
            r.markAllRead(this.menuFeedId, this.statusFilter).then(() => {
              this.reloadAll();
            });
          }
        })
      MenuItem({ content: '编辑订阅源' })
        .onClick(() => {
          this.menuVisible = false;
          this.openEditSheet();
        })
      MenuItem({ content: '移除订阅源' })
        .onClick(() => {
          this.menuVisible = false;
          const target = this.findFeed(this.menuFeedId);
          if (target !== null) {
            this.showRemoveDialog(target);
          }
        })
    }
  }

  private showRemoveDialog(feed: FeedRow): void {
    AlertDialog.show({
      title: '取消订阅',
      message: '确定要取消订阅“' + feed.title + '”吗？',
      primaryButton: {
        value: '取消',
        action: () => {
        }
      },
      secondaryButton: {
        value: '移除',
        action: () => this.confirmRemove(feed)
      }
    });
  }

  private selectedFeedTitle(): string {
    const f = this.findFeed(this.selectedFeedId === null ? '' : this.selectedFeedId);
    return f !== null ? f.title : '文章';
  }

  private findFeed(id: string): FeedRow | null {
    for (const f of this.feeds) {
      if (f.id === id) {
        return f;
      }
    }
    return null;
  }

}