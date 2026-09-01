// Articles main screen - FEAT-ADD-FEED + FEAT-FEED-REFRESH (impl-lead.capy-01).
// Real surface on the live feed/article store:
//   sidebar: settings/refresh/add-feed header, All Articles filter,
//            Feeds group with per-feed overflow menu (Mark All as Read /
//            Remove Feed -> confirm dialog), feed-row filtering
//   content: List + LazyForEach article rows (title + timestamp),
//            "Mark All as Read" toolbar when list populated, empty
//            onboarding state otherwise, Add Feed bindSheet (URL input,
//            feedfinder error state), refresh-all with busy indicator.
// Native-first: bindSheet (A23), AlertDialog, Menu, List+LazyForEach,
// TextInput; Navigation stays the single NavPathStack shell (R2).
// Batch 2 reading domain: status filter bar (Unread/All/Starred, BC-0009,
// persisted to prefs article_filter), read-row dimming, Mark All as Read
// confirm dialog (BC-0015). Article tap pushes the reader route
// PAGE-ARTICLEREADER-B2B865F0 (pages/reader/ArticleReaderPage.ets).
import hilog from '@ohos.hilog';
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
  @State addSheetOpen: boolean = false;
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
  private repo: FeedRepository | null = null;

  aboutToAppear(): void {
    const ctx = getContext(this);
    const accountRepo = AccountRepository.obtain(ctx);
    this.hasAccount = accountRepo.hasAccount();
    accountRepo.exportReplayData();
    FeedRepository.obtain(ctx).then((repo: FeedRepository) => {
      this.repo = repo;
      // BC-0009 persistence: restore the persisted status filter on launch
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
      this.dataSource.reload(arts);
    });
  }

  private fmtDate(epoch: number): string {
    if (epoch <= 0) {
      return '';
    }
    const d = new Date(epoch * 1000);
    const m = d.getMonth() + 1;
    return d.getFullYear() + '-' + (m < 10 ? '0' + m : m) + '-' + d.getDate();
  }

  // --- Add Feed flow (BC-0004 / BC-0005) ---------------------------------

  private openAddSheet(): void {
    this.urlInput = '';
    this.addErrorText = '';
    this.addSheetOpen = true;
    hilog.info(0x0000, 'P4Sheet', 'openAddSheet set addSheetOpen=true');
  }

  private submitAdd(): void {
    if (this.addLoading || this.repo === null) {
      return;
    }
    const url = this.urlInput.trim();
    if (url.length === 0) {
      this.addErrorText = 'Couldn\'t find feed';
      return;
    }
    this.addLoading = true;
    this.addErrorText = '';
    const repo = this.repo;
    repo.addFeed(url).then((code: AddFeedResultCode) => {
      this.addLoading = false;
      if (code === AddFeedResultCode.SUCCESS) {
        this.addSheetOpen = false;
        this.feedAddedBanner = 'Feed added';
        this.reloadAll();
      } else if (code === AddFeedResultCode.CONNECTION_ERROR) {
        this.addErrorText = 'Couldn\'t find feed. Check your connection.';
      } else if (code === AddFeedResultCode.SAVE_FAILURE) {
        this.addErrorText = 'Couldn\'t save feed';
      } else {
        this.addErrorText = 'Couldn\'t find feed';
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
      title: 'Mark all items as read?',
      message: '',
      primaryButton: {
        value: 'Cancel',
        action: () => {
          this.confirmMarkAll = false;
        }
      },
      secondaryButton: {
        value: 'Confirm',
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

  // --- Remove feed flow (BC-0007) ------------------------------------------

  private confirmRemove(feed: FeedRow): void {
    if (this.repo === null) {
      return;
    }
    this.repo.removeFeed(feed.id).then(() => {
      this.reloadAll();
    });
  }

  @Builder
  addFeedSheet() {
    Column({ space: 16 }) {
      Text('Add Feed')
        .fontSize(20)
        .fontWeight(FontWeight.Bold)
      Column({ space: 4 }) {
        Text('Feed or Website URL')
          .fontSize(12)
          .fontColor(this.addErrorText !== '' ? '#D84026' : '#666666')
        TextInput({ text: this.urlInput, placeholder: 'Feed or Website URL' })
          .onChange((v: string) => {
            this.urlInput = v;
          })
          .height(48)
          .backgroundColor('#0F000000')
          .borderRadius(8)
          .enabled(!this.addLoading)
          // Walkthrough determinism (batch-3): IME overlay can mask the Add
          // button and a raw Back key risks closing the sheet; Enter submits
          // the URL directly from the keyboard.
          .enterKeyType(EnterKeyType.Done)
          .onSubmit(() => this.submitAdd())
        if (this.addErrorText !== '') {
          Text(this.addErrorText)
            .fontSize(12)
            .fontColor('#D84026')
            .width('100%')
        }
      }
      .width('100%')
      Row({ space: 8 }) {
        Button('Cancel')
          .fontSize(14)
          .fontColor('#1B6EF3')
          .backgroundColor('#00000000')
          .layoutWeight(1)
          .onClick(() => {
            this.addSheetOpen = false;
          })
        Button('Add')
          .fontSize(14)
          .fontColor('#FFFFFF')
          .backgroundColor('#1B6EF3')
          .layoutWeight(1)
          .enabled(!this.addLoading)
          .onClick(() => this.submitAdd())
      }
      .width('100%')
      if (this.addLoading) {
        LoadingProgress().width(24).height(24)
      }
    }
    .padding(20)
    .width('100%')
    .backgroundColor(this.uiDark ? '#292730' : '#FFFFFF')
    .borderRadius({ topLeft: 16, topRight: 16 })
  }

  @Builder
  sidebarBuilder() {
    Column({ space: 4 }) {
      Row({ space: 8 }) {
        Text('Settings')
          .fontSize(12)
          .fontColor(this.uiDark ? '#C5C6D0' : '#666666')
          .padding(8)
          .accessibilityText('Open settings navigation')
          .onClick(() => {
            // BC-0018: sidebar settings entry -> PAGE-SETTINGSSCREEN route
            if (this.pathStack !== null) {
              this.pathStack.pushPathByName('PAGE-SETTINGSSCREEN-D0A9FF8D', undefined);
            }
          })
        Text(this.refreshing ? 'Refreshing…' : 'Refresh all')
          .fontSize(12)
          .fontColor('#666666')
          .padding(8)
          .accessibilityText('Refresh all')
          .onClick(() => this.refreshAllFeeds())
        Text('Add Feed')
          .fontSize(12)
          .fontColor('#1B6EF3')
          .padding(8)
          .accessibilityText('Add Feed')
          .onClick(() => this.openAddSheet())
      }
      .width('100%')
      .justifyContent(FlexAlign.End)
      Text('All Articles')
        .fontSize(14)
        .fontWeight(this.selectedFeedId === null && this.statusFilter === 'all' ? FontWeight.Bold : FontWeight.Normal)
        .padding({ top: 8, bottom: 8 })
        .width('100%')
        .onClick(() => {
          this.selectedFeedId = null;
          this.selectStatus('all');
        })
      Text('Starred')
        .fontSize(14)
        .fontColor(this.statusFilter === 'starred' ? '#1B6EF3' : '#000000')
        .fontWeight(this.statusFilter === 'starred' ? FontWeight.Bold : FontWeight.Normal)
        .padding({ top: 4, bottom: 8 })
        .width('100%')
        .onClick(() => {
          this.selectStatus('starred');
        })
      Text('Feeds')
        .fontSize(13)
        .fontWeight(FontWeight.Medium)
        .fontColor('#666666')
        .padding({ top: 8, bottom: 4 })
      List() {
        ForEach(this.feeds, (feed: FeedRow) => {
          ListItem() {
            Row() {
              Text(feed.title)
                .fontSize(14)
                .layoutWeight(1)
                .maxLines(1)
                .textOverflow({ overflow: TextOverflow.Ellipsis })
                .onClick(() => {
                  this.selectedFeedId = feed.id;
                  this.reloadAll();
                })
              Text('More options')
                .fontSize(11)
                .fontColor('#888888')
                .padding(6)
                .onClick(() => {
                  this.menuFeedId = feed.id;
                  this.menuFeedTitle = feed.title;
                  this.menuVisible = true;
                })
            }
            .width('100%')
          }
        }, (feed: FeedRow) => feed.id)
      }
      .layoutWeight(1)
      .scrollBar(BarState.Off)
      Row({ space: 10 }) {
        Text('Unread')
          .fontSize(12)
          .fontColor(this.statusFilter === 'unread' ? '#1B6EF3' : '#666666')
          .padding(6)
          .onClick(() => this.selectStatus('unread'))
        Text('All')
          .fontSize(12)
          .fontColor(this.statusFilter === 'all' ? '#1B6EF3' : '#666666')
          .padding(6)
          .onClick(() => this.selectStatus('all'))
        Text('Starred')
          .fontSize(12)
          .fontColor(this.statusFilter === 'starred' ? '#1B6EF3' : '#666666')
          .padding(6)
          .onClick(() => this.selectStatus('starred'))
      }
      .width('100%')
      .justifyContent(FlexAlign.Center)
      .padding({ top: 6, bottom: 10 })
    }
    .width(220)
    .height('100%')
    .padding({ left: 12, right: 12 })
    .alignItems(HorizontalAlign.Start)
    .backgroundColor(this.uiDark ? '#211F26' : '#FAFAFA')
  }

  build() {
    NavDestination() {
      Stack() {
        Row() {
          this.sidebarBuilder()
          Column() {
            if (this.feedAddedBanner !== '') {
              Text(this.feedAddedBanner)
                .fontSize(14)
                .fontColor('#FFFFFF')
                .backgroundColor('#323232')
                .borderRadius(8)
                .padding({ left: 16, right: 16, top: 10, bottom: 10 })
                .margin({ top: 8 })
                .onAppear(() => {
                  setTimeout(() => {
                    this.feedAddedBanner = '';
                  }, 5000);
                })
            }
            Text(this.selectedFeedId !== null ? this.selectedFeedTitle() : 'Articles')
              .fontSize(18)
              .fontWeight(FontWeight.Bold)
              .fontColor(this.uiDark ? '#E3E2E6' : '#000000')
              .width('100%')
              .padding({ left: 16, right: 16, top: 10, bottom: 4 })
            if (this.dataSource.totalCount() > 0) {
              Text('Mark All as Read')
                .fontSize(13)
                .fontColor('#666666')
                .width('100%')
                .padding({ left: 16, right: 16, top: 8, bottom: 8 })
                .accessibilityText('Mark All as Read')
                .onClick(() => this.requestMarkAllRead())
              List({ space: 0 }) {
                LazyForEach(this.dataSource, (item: ArticleRow) => {
                  ListItem() {
                    Column({ space: 2 }) {
                      Text(item.title.length > 0 ? item.title : '(untitled)')
                        .fontSize(15)
                        .fontColor(item.read === 1
                          ? (this.uiDark ? '#777777' : '#999999')
                          : (this.uiDark ? '#E3E2E6' : '#111111'))
                        .fontWeight(item.read === 1 ? FontWeight.Normal : FontWeight.Medium)
                        .maxLines(2)
                        .textOverflow({ overflow: TextOverflow.Ellipsis })
                      Row({ space: 6 }) {
                        // PD-1 (Android contract alignment): unread = solid
                        // dot, read = hollow dot; same direction as reader.
                        Text(item.read === 1 ? '○' : '●')
                          .fontSize(10)
                          .fontColor(item.read === 1
                            ? (this.uiDark ? '#777777' : '#999999')
                            : '#1B6EF3')
                        Text(this.fmtDate(item.publishedAt))
                          .fontSize(12)
                          .fontColor(this.uiDark ? '#C5C6D0' : '#888888')
                      }
                      .alignItems(VerticalAlign.Center)
                      Divider().color(this.uiDark ? '#22FFFFFF' : '#11000000')
                    }
                    .width('100%')
                    .alignItems(HorizontalAlign.Start)
                    .padding({ left: 16, right: 16, top: 10, bottom: 10 })
                    .opacity(item.read === 1 ? 0.5 : 1.0)
                    .onClick(() => {
                      if (this.pathStack !== null) {
                        this.pathStack.pushPathByName('PAGE-ARTICLEREADER-B2B865F0', item.id);
                      }
                    })
                  }
                }, (item: ArticleRow) => item.id + '_' + item.read + '_' + item.starred)
              }
              .layoutWeight(1)
              .scrollBar(BarState.Off)
            } else if (this.hasAccount) {
              Column({ space: 8 }) {
                Text('No feeds yet')
                  .fontSize(16)
                  .fontWeight(FontWeight.Medium)
                  .textAlign(TextAlign.Center)
                Text('Start by adding a feed')
                  .fontSize(14)
                  .fontColor('#666666')
                  .textAlign(TextAlign.Center)
                Button('Add Feed')
                  .fontSize(14)
                  .fontColor('#1B6EF3')
                  .backgroundColor('#00000000')
                  .border({ width: 1, color: '#1B6EF3', radius: 20 })
                  .padding({ left: 16, right: 16, top: 6, bottom: 6 })
                  .margin({ top: 8 })
                  .accessibilityText('Add Feed')
                  .onClick(() => this.openAddSheet())
              }
              .width('100%')
              .height('100%')
              .justifyContent(FlexAlign.Center)
              .alignItems(HorizontalAlign.Center)
              .padding({ left: 16, right: 16 })
            } else {
              Text('No account')
                .fontSize(16)
                .fontColor('#666666')
            }
          }
          .width('100%')
          .height('100%')
          .layoutWeight(1)
        }
        .width('100%')
        .height('100%')
        .bindSheet($$this.addSheetOpen, this.addFeedSheet(), {
          height: 320, dragBar: true, showClose: false
        })
        // Phase 3 ROUTE_SMOKE modal mounts removed (impl-lead.capy-01):
        // the full-size transparent carrier shells swallow all touch events
        // over the sidebar/content regardless of hitTestBehavior; Phase 4
        // wires the real modal carriers instead (bindSheet AddFeed form,
        // AlertDialog unsubscribe confirm, bindMenu feed actions). The P3
        // ROUTE_SMOKE proof itself is CLOSED and archived in phase-03.
      }
      .width('100%')
      .height('100%')
      .id('PAGE-ARTICLESCREEN-23AF0624')
      .backgroundColor(this.uiDark ? '#1B1B1F' : '#FFFFFF')
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

  @Builder
  buildFeedMenu() {
    Menu() {
      MenuItem({ content: 'Mark All as Read' })
        .onClick(() => {
          this.menuVisible = false;
        })
      MenuItem({ content: 'Remove Feed' })
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
      title: 'Unsubscribe',
      message: 'Are you sure you want to unsubscribe from "' + feed.title + '"?',
      primaryButton: {
        value: 'Cancel',
        action: () => {
        }
      },
      secondaryButton: {
        value: 'Remove',
        action: () => this.confirmRemove(feed)
      }
    });
  }

  private selectedFeedTitle(): string {
    const f = this.findFeed(this.selectedFeedId === null ? '' : this.selectedFeedId);
    return f !== null ? f.title : 'Articles';
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
