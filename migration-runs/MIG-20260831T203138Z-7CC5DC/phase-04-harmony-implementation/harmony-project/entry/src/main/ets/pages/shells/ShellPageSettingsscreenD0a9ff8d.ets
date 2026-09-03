// SettingsScreen - FEAT-SETTINGS (impl-lead.capy-01 R5 batch 3, SLICE-3 rev2:
// full five-section parity with Android SettingsView panel list).
// Real settings surface on the live prefs store (BC-0018 navigation host,
// BC-0019 Theme picker, BC-0020 article list sort order, BC-0021 reader style):
//   Display & Appearance (container .id PAGE-DISPLAYSETTINGSPANEL-650C8AEE)
//     > Theme (System default / Light / Dark) -> prefs app_theme + theme_mode
//       + ApplicationContext.setColorMode, immediate effect (BC-0019)
//     > Article Display -> font triple choice Small/Medium/Large -> prefs
//       article_font_size (BC-0021 key, shared with the reader Aa picker)
//   General
//     > Sort order (Newest first / Oldest first) -> prefs
//       article_list_sort_order (BC-0020); listArticles flips ORDER BY
//     > Refresh Feeds (Manually only / Every hour / Every 2 hours /
//       Every 6 hours / Every day) -> kv refresh_interval
//     > Open Links In (Default browser / In-app browser) -> kv open_links_in
//   Gestures -> 4 presentation-level switches (Swipe Down / Swipe Up /
//     Swipe Right / Swipe Left) -> kv gesture_swipe_* (default off)
//   Account -> local account info (source + account_id) + Log Out button
//     with AlertDialog confirm (Android settings_remove_account_*_service
//     strings) -> AccountRepository.logOut() -> stack cleared back to
//     PAGE-ADDACCOUNTSCREEN-A9C749BC (MainActivity.startDestination parity)
//   About -> CapyReader title row + Version row (source triple
//     versionCode 1212 / versionName 2026.07.1212)
// All option rows are visible-text anchors (dumpLayout rule: accessibility
// text never enters the layout dump). R3-SLICE-8 localization: every
// user-visible label is now zh-CN (option labels stay display-layer
// only via the *Label() helpers; persisted enum/prefs values such as
// app_theme=LIGHT / NEWEST_FIRST / EVERY_TWO_HOURS are unchanged).
// The section header is split as two text nodes ('显示' + '与外观')
// reading as "显示与外观"; the BC-0018 anchor change Display->显示 is
// recorded in evidence/revision3/anchor-mapping.csv (BC files frozen).
// R3-SLICE-9 (presentation-diff fixes): the five preference selectors
// (Theme / Article Display / Sort / Refresh Feeds / Open Links In) moved
// from inline row expansion to a popup selection list anchored on the row
// (Android ThemePicker.kt ExposedDropdownMenu + PreferenceSelect.kt dialog
// parity: card title + option rows with a trailing ✓ marker and highlight
// on the current value). Selecting an option keeps persisting the same
// prefs keys as before (BC-0019 / BC-0020 / BC-0021 / kv values).
// Page content root carries .id PAGE-SETTINGSVIEW-9331B5E9 (SettingsView
// passthrough surface, P3 surface-plan) while the original shell component
// id below stays untouched.
import { AccountRepository } from '../../data/AccountRepository';
import hilog from '@ohos.hilog';

const TAG = 'P4Settings';

// General > Refresh Feeds options (Android RefreshInterval enum-name keys;
// option set per SLICE-3 spec: Manually only / Every hour / Every 2 hours /
// Every 6 hours / Every day).
const REFRESH_MANUALLY_ONLY = 'MANUALLY_ONLY';
const REFRESH_EVERY_HOUR = 'EVERY_HOUR';
const REFRESH_EVERY_TWO_HOURS = 'EVERY_TWO_HOURS';
const REFRESH_EVERY_SIX_HOURS = 'EVERY_SIX_HOURS';
const REFRESH_EVERY_DAY = 'EVERY_DAY';
// Android RefreshInterval.default = EVERY_TWO_HOURS.
const REFRESH_DEFAULT = REFRESH_EVERY_TWO_HOURS;

// General > Open Links In options (Android canOpenLinksInternally parity:
// default false -> external/default browser).
const OPEN_LINKS_DEFAULT_BROWSER = 'DEFAULT_BROWSER';
const OPEN_LINKS_IN_APP_BROWSER = 'IN_APP_BROWSER';

// Presentation-level kv keys (Gestures default off).
const KEY_REFRESH_INTERVAL = 'refresh_interval';
const KEY_OPEN_LINKS_IN = 'open_links_in';
const KEY_GESTURE_SWIPE_DOWN = 'gesture_swipe_down';
const KEY_GESTURE_SWIPE_UP = 'gesture_swipe_up';
const KEY_GESTURE_SWIPE_RIGHT = 'gesture_swipe_right';
const KEY_GESTURE_SWIPE_LEFT = 'gesture_swipe_left';

// About triple from the Android source (build.gradle.kts versionCode 1212 /
// versionName "2026.07.1212").
const APP_VERSION_TEXT = '1212 (2026.07.1212)';

// R3-SLICE-9: selection popup entries (value = persisted key, label =
// zh-CN display text; persisted enum values stay unchanged).
class PickerEntry {
  value: string = '';
  label: string = '';

  constructor(value: string, label: string) {
    this.value = value;
    this.label = label;
  }
}

const THEME_OPTIONS: PickerEntry[] = [
  new PickerEntry('system', '跟随系统'),
  new PickerEntry('light', '浅色'),
  new PickerEntry('dark', '深色')
];

const FONT_OPTIONS: PickerEntry[] = [
  new PickerEntry('SMALL', '小'),
  new PickerEntry('MEDIUM', '中'),
  new PickerEntry('LARGE', '大')
];

const SORT_OPTIONS: PickerEntry[] = [
  new PickerEntry('NEWEST_FIRST', '最新优先'),
  new PickerEntry('OLDEST_FIRST', '最早优先')
];

const REFRESH_OPTIONS: PickerEntry[] = [
  new PickerEntry(REFRESH_MANUALLY_ONLY, '仅手动'),
  new PickerEntry(REFRESH_EVERY_HOUR, '每小时'),
  new PickerEntry(REFRESH_EVERY_TWO_HOURS, '每 2 小时'),
  new PickerEntry(REFRESH_EVERY_SIX_HOURS, '每 6 小时'),
  new PickerEntry(REFRESH_EVERY_DAY, '每天')
];

const OPEN_LINKS_OPTIONS: PickerEntry[] = [
  new PickerEntry(OPEN_LINKS_DEFAULT_BROWSER, '默认浏览器'),
  new PickerEntry(OPEN_LINKS_IN_APP_BROWSER, '应用内浏览器')
];

@Component
export struct ShellPageSettingsscreenD0a9ff8d {
  @Consume('foundationPathStack') pathStack: NavPathStack | null = null;
  @StorageProp('uiDark') uiDark: boolean = false;
  @State themeMode: string = 'system';
  @State sortOrder: string = 'NEWEST_FIRST';
  @State refreshInterval: string = REFRESH_DEFAULT;
  @State openLinksIn: string = OPEN_LINKS_DEFAULT_BROWSER;
  @State articleFontSize: string = 'MEDIUM';
  @State gestureSwipeDown: boolean = false;
  @State gestureSwipeUp: boolean = false;
  @State gestureSwipeRight: boolean = false;
  @State gestureSwipeLeft: boolean = false;
  @State accountId: string = '';
  @State accountSource: string = 'local';
  // Single exclusive disclosure state: '' | 'theme' | 'sort' | 'refresh' |
  // 'openLinks' | 'font'. Replaces the previous two-flag scheme with equal
  // behavior for BC-0019/0020 (tap row -> options expand, tap again -> fold).
  @State openSection: string = '';
  private repo: AccountRepository | null = null;

  aboutToAppear(): void {
    const ctx = getContext(this);
    this.repo = AccountRepository.obtain(ctx);
    this.themeMode = this.repo.getThemeMode();
    this.sortOrder = this.repo.getSortOrder();
    this.refreshInterval = this.repo.getReaderStyle(KEY_REFRESH_INTERVAL, REFRESH_DEFAULT);
    this.openLinksIn = this.repo.getReaderStyle(KEY_OPEN_LINKS_IN, OPEN_LINKS_DEFAULT_BROWSER);
    // BC-0021 key: shared with the reader Aa style picker (default MEDIUM).
    this.articleFontSize = this.repo.getReaderStyle('article_font_size', 'MEDIUM');
    this.gestureSwipeDown = this.repo.getReaderStyle(KEY_GESTURE_SWIPE_DOWN, 'off') === 'on';
    this.gestureSwipeUp = this.repo.getReaderStyle(KEY_GESTURE_SWIPE_UP, 'off') === 'on';
    this.gestureSwipeRight = this.repo.getReaderStyle(KEY_GESTURE_SWIPE_RIGHT, 'off') === 'on';
    this.gestureSwipeLeft = this.repo.getReaderStyle(KEY_GESTURE_SWIPE_LEFT, 'off') === 'on';
    this.accountId = this.repo.getAccountId();
    if (this.accountId.length > 0) {
      const src = this.repo.getSource(this.accountId);
      this.accountSource = src.length > 0 ? src : 'local';
    }
    hilog.info(0x0000, TAG,
      'settings opened, theme=%{public}s sort=%{public}s refresh=%{public}s links=%{public}s font=%{public}s account=%{public}s',
      this.themeMode, this.sortOrder, this.refreshInterval, this.openLinksIn, this.articleFontSize, this.accountId);
  }

  private goBack(): void {
    if (this.pathStack !== null) {
      this.pathStack.pop();
    }
  }

  private toggleSection(section: string): void {
    this.openSection = this.openSection === section ? '' : section;
  }

  // R3-SLICE-9: popup selection dispatch (rows keep their selectXxx prefs
  // writers; openSection doubles as the popup visibility state).
  private pickerPick(section: string, value: string): void {
    if (section === 'theme') {
      this.selectTheme(value);
    } else if (section === 'font') {
      this.selectFont(value);
    } else if (section === 'sort') {
      this.selectSort(value);
    } else if (section === 'refresh') {
      this.selectRefresh(value);
    } else if (section === 'openLinks') {
      this.selectOpenLinks(value);
    }
    this.openSection = '';
  }

  private themeLabel(mode: string): string {
    if (mode === 'dark') {
      return '深色';
    }
    return mode === 'light' ? '浅色' : '跟随系统';
  }

  private sortLabel(order: string): string {
    return order === 'OLDEST_FIRST' ? '最早优先' : '最新优先';
  }

  private refreshLabel(interval: string): string {
    if (interval === REFRESH_MANUALLY_ONLY) {
      return '仅手动';
    }
    if (interval === REFRESH_EVERY_HOUR) {
      return '每小时';
    }
    if (interval === REFRESH_EVERY_TWO_HOURS) {
      return '每 2 小时';
    }
    if (interval === REFRESH_EVERY_SIX_HOURS) {
      return '每 6 小时';
    }
    if (interval === REFRESH_EVERY_DAY) {
      return '每天';
    }
    return '每 2 小时';
  }

  private openLinksLabel(value: string): string {
    return value === OPEN_LINKS_IN_APP_BROWSER ? '应用内浏览器' : '默认浏览器';
  }

  private fontLabel(size: string): string {
    if (size === 'SMALL') {
      return '小';
    }
    return size === 'LARGE' ? '大' : '中';
  }

  private selectTheme(mode: string): void {
    this.themeMode = mode;
    this.openSection = '';
    if (this.repo !== null) {
      // BC-0019: prefs app_theme/theme_mode + immediate setColorMode
      this.repo.setThemeMode(mode);
    }
  }

  private selectSort(order: string): void {
    this.sortOrder = order;
    this.openSection = '';
    if (this.repo !== null) {
      // BC-0020: prefs article_list_sort_order; the article list re-queries
      // with the flipped ORDER BY when the screen is shown again.
      this.repo.setSortOrder(order);
    }
  }

  private selectRefresh(interval: string): void {
    this.refreshInterval = interval;
    this.openSection = '';
    if (this.repo !== null) {
      this.repo.setReaderStyle(KEY_REFRESH_INTERVAL, interval);
    }
  }

  private selectOpenLinks(value: string): void {
    this.openLinksIn = value;
    this.openSection = '';
    if (this.repo !== null) {
      this.repo.setReaderStyle(KEY_OPEN_LINKS_IN, value);
    }
  }

  private selectFont(size: string): void {
    this.articleFontSize = size;
    this.openSection = '';
    if (this.repo !== null) {
      // BC-0021 parity: the reader page reads the same prefs key, so the
      // Aa picker and this row stay in sync.
      this.repo.setReaderStyle('article_font_size', size);
    }
  }

  private onGestureToggle(key: string, on: boolean): void {
    if (this.repo !== null) {
      this.repo.setReaderStyle(key, on ? 'on' : 'off');
    }
    if (key === KEY_GESTURE_SWIPE_DOWN) {
      this.gestureSwipeDown = on;
    } else if (key === KEY_GESTURE_SWIPE_UP) {
      this.gestureSwipeUp = on;
    } else if (key === KEY_GESTURE_SWIPE_RIGHT) {
      this.gestureSwipeRight = on;
    } else if (key === KEY_GESTURE_SWIPE_LEFT) {
      this.gestureSwipeLeft = on;
    }
  }

  // Account > Log Out (Android settings_remove_account_*_service parity:
  // title "Log Out", message "Are you sure you want to log out?",
  // dismiss "Cancel", confirm "Log Out").
  private requestLogOut(): void {
    AlertDialog.show({
      title: '退出登录',
      message: '确定要退出登录吗？',
      primaryButton: {
        value: '取消',
        action: () => {
        }
      },
      secondaryButton: {
        value: '退出登录',
        fontColor: '#e23c3c',
        action: () => {
          this.confirmLogOut();
        }
      },
      autoCancel: true,
      alignment: DialogAlignment.Center
    });
  }

  private confirmLogOut(): void {
    if (this.repo !== null) {
      this.repo.logOut();
    }
    hilog.info(0x0000, TAG, 'log out confirmed, returning to add account');
    if (this.pathStack !== null) {
      // MainActivity.startDestination parity: no account left -> the add
      // account screen becomes the only stack entry.
      this.pathStack.clear();
      this.pathStack.replacePathByName('PAGE-ADDACCOUNTSCREEN-A9C749BC', undefined, true);
    }
  }

  // R3-SLICE-9: param-less popup wrappers (PopupOptions.builder takes a
  // builder reference, so each section gets its own no-arg @Builder).
  @Builder
  themePanel() {
    this.pickerPanel('主题', 'theme', THEME_OPTIONS, this.themeMode)
  }

  @Builder
  fontPanel() {
    this.pickerPanel('文章显示', 'font', FONT_OPTIONS, this.articleFontSize)
  }

  @Builder
  sortPanel() {
    this.pickerPanel('排序', 'sort', SORT_OPTIONS, this.sortOrder)
  }

  @Builder
  refreshPanel() {
    this.pickerPanel('刷新频率', 'refresh', REFRESH_OPTIONS, this.refreshInterval)
  }

  @Builder
  openLinksPanel() {
    this.pickerPanel('链接打开方式', 'openLinks', OPEN_LINKS_OPTIONS, this.openLinksIn)
  }

  // R3-SLICE-9: selection list popup card (Android PreferenceSelect.kt
  // DialogCard parity: headline title + option rows with trailing ✓ marker
  // and highlight background on the current value).
  @Builder
  pickerPanel(title: string, section: string, entries: PickerEntry[], current: string) {
    Column() {
      Text(title)
        .fontSize(18)
        .fontWeight(FontWeight.Bold)
        .fontColor(this.uiDark ? '#ffffff' : '#1a1a1a')
        .width('100%')
        .padding({ top: 16, bottom: 6, left: 24, right: 24 })
      ForEach(entries, (e: PickerEntry) => {
        Row() {
          Text(e.label)
            .fontSize(16)
            .fontColor(e.value === current
              ? '#2b7cf6'
              : (this.uiDark ? '#ffffff' : '#1a1a1a'))
            .layoutWeight(1)
          if (e.value === current) {
            Text('✓')
              .fontSize(16)
              .fontWeight(FontWeight.Bold)
              .fontColor('#2b7cf6')
          }
        }
        .width('100%')
        .padding({ top: 13, bottom: 13, left: 24, right: 24 })
        .borderRadius(8)
        .backgroundColor(e.value === current
          ? (this.uiDark ? '#262b7cf6' : '#0A2b7cf6')
          : Color.Transparent)
        .onClick(() => this.pickerPick(section, e.value))
      }, (e: PickerEntry) => section + '_' + e.value)
    }
    .width(300)
    .padding({ bottom: 10 })
    .backgroundColor(this.uiDark ? '#1a1a1a' : '#ffffff')
    .borderRadius(16)
    .alignItems(HorizontalAlign.Start)
  }

  @Builder
  sectionDivider() {
    Divider().color(this.uiDark ? '#22FFFFFF' : '#11000000')
  }

  @Builder
  gestureSwitchRow(title: string, key: string, isOn: boolean) {
    Row() {
      Text(title)
        .fontSize(16)
        .fontColor(this.uiDark ? '#ffffff' : '#1a1a1a')
        .layoutWeight(1)
      Toggle({ type: ToggleType.Switch, isOn: isOn })
        .selectedColor('#2b7cf6')
        .onChange((on: boolean) => {
          this.onGestureToggle(key, on);
        })
    }
    .width('100%')
    .padding({ top: 10, bottom: 10, left: 16, right: 16 })
  }

  build() {
    NavDestination() {
      Column() {
        // back bar
        Row({ space: 10 }) {
          Text('←')
            .fontSize(20)
            .padding(10)
            .fontColor(this.uiDark ? '#ffffff' : '#1a1a1a')
            .onClick(() => this.goBack())
          Text('设置')
            .fontSize(16)
            .fontWeight(FontWeight.Medium)
            .fontColor(this.uiDark ? '#ffffff' : '#1a1a1a')
            .layoutWeight(1)
        }
        .width('100%')
        .alignItems(VerticalAlign.Center)
        .border({ width: { bottom: 1 }, color: this.uiDark ? '#22FFFFFF' : '#11000000' })

        Scroll() {
          // SettingsView passthrough surface root (P3 surface-plan
          // PAGE-SETTINGSVIEW-9331B5E9); the shell component id on the
          // NavDestination below stays as-is.
          Column() {
            // ---- Display & Appearance section ----
            // Container anchor for the passthrough panel surface
            // PAGE-DISPLAYSETTINGSPANEL-650C8AEE. R3-SLICE-8: header split
            // kept as two text nodes ('显示' + '与外观'); the BC-0018 anchor
            // change Display->显示 is tracked in anchor-mapping.csv.
            Column() {
              Row() {
                Text('显示')
                  .fontSize(13)
                  .fontWeight(FontWeight.Medium)
                  .fontColor(this.uiDark ? '#eceef2' : '#6f7682')
                Text('与外观')
                  .fontSize(13)
                  .fontWeight(FontWeight.Medium)
                  .fontColor(this.uiDark ? '#eceef2' : '#6f7682')
              }
              .width('100%')
              .padding({ top: 16, bottom: 4, left: 16 })

              Row() {
                Text('主题')
                  .fontSize(16)
                  .fontColor(this.uiDark ? '#ffffff' : '#1a1a1a')
                  .layoutWeight(1)
                Text(this.themeLabel(this.themeMode))
                  .fontSize(14)
                  .fontColor(this.uiDark ? '#eceef2' : '#6f7682')
              }
              .width('100%')
              .padding({ top: 12, bottom: 12, left: 16, right: 16 })
              .onClick(() => {
                this.toggleSection('theme');
              })
              .bindPopup(this.openSection === 'theme', {
                builder: this.themePanel,
                placement: Placement.BottomLeft,
                autoCancel: true,
                enableArrow: false,
                onStateChange: (event: PopupStateChangeParam) => {
                  if (!event.isVisible && this.openSection === 'theme') {
                    this.openSection = '';
                  }
                }
              })
              this.sectionDivider()

              Row() {
                Text('文章显示')
                  .fontSize(16)
                  .fontColor(this.uiDark ? '#ffffff' : '#1a1a1a')
                  .layoutWeight(1)
                Text(this.fontLabel(this.articleFontSize))
                  .fontSize(14)
                  .fontColor(this.uiDark ? '#eceef2' : '#6f7682')
              }
              .width('100%')
              .padding({ top: 12, bottom: 12, left: 16, right: 16 })
              .onClick(() => {
                this.toggleSection('font');
              })
              .bindPopup(this.openSection === 'font', {
                builder: this.fontPanel,
                placement: Placement.BottomLeft,
                autoCancel: true,
                enableArrow: false,
                onStateChange: (event: PopupStateChangeParam) => {
                  if (!event.isVisible && this.openSection === 'font') {
                    this.openSection = '';
                  }
                }
              })
              this.sectionDivider()
            }
            .width('100%')
            .alignItems(HorizontalAlign.Start)
            .id('PAGE-DISPLAYSETTINGSPANEL-650C8AEE')

            // ---- General section (BC-0020 anchor: text=General) ----
            Text('通用')
              .fontSize(13)
              .fontWeight(FontWeight.Medium)
              .fontColor(this.uiDark ? '#eceef2' : '#6f7682')
              .width('100%')
              .padding({ top: 20, bottom: 4, left: 16 })
            Row() {
              Text('排序')
                .fontSize(16)
                .fontColor(this.uiDark ? '#ffffff' : '#1a1a1a')
                .layoutWeight(1)
              Text(this.sortLabel(this.sortOrder))
                .fontSize(14)
                .fontColor(this.uiDark ? '#eceef2' : '#6f7682')
            }
            .width('100%')
            .padding({ top: 12, bottom: 12, left: 16, right: 16 })
            .onClick(() => {
              this.toggleSection('sort');
            })
            .bindPopup(this.openSection === 'sort', {
              builder: this.sortPanel,
              placement: Placement.BottomLeft,
              autoCancel: true,
              enableArrow: false,
              onStateChange: (event: PopupStateChangeParam) => {
                if (!event.isVisible && this.openSection === 'sort') {
                  this.openSection = '';
                }
              }
            })
            this.sectionDivider()

            Row() {
              Text('刷新频率')
                .fontSize(16)
                .fontColor(this.uiDark ? '#ffffff' : '#1a1a1a')
                .layoutWeight(1)
              Text(this.refreshLabel(this.refreshInterval))
                .fontSize(14)
                .fontColor(this.uiDark ? '#eceef2' : '#6f7682')
            }
            .width('100%')
            .padding({ top: 12, bottom: 12, left: 16, right: 16 })
            .onClick(() => {
              this.toggleSection('refresh');
            })
            .bindPopup(this.openSection === 'refresh', {
              builder: this.refreshPanel,
              placement: Placement.BottomLeft,
              autoCancel: true,
              enableArrow: false,
              onStateChange: (event: PopupStateChangeParam) => {
                if (!event.isVisible && this.openSection === 'refresh') {
                  this.openSection = '';
                }
              }
            })
            this.sectionDivider()

            Row() {
              Text('链接打开方式')
                .fontSize(16)
                .fontColor(this.uiDark ? '#ffffff' : '#1a1a1a')
                .layoutWeight(1)
              Text(this.openLinksLabel(this.openLinksIn))
                .fontSize(14)
                .fontColor(this.uiDark ? '#eceef2' : '#6f7682')
            }
            .width('100%')
            .padding({ top: 12, bottom: 12, left: 16, right: 16 })
            .onClick(() => {
              this.toggleSection('openLinks');
            })
            .bindPopup(this.openSection === 'openLinks', {
              builder: this.openLinksPanel,
              placement: Placement.BottomLeft,
              autoCancel: true,
              enableArrow: false,
              onStateChange: (event: PopupStateChangeParam) => {
                if (!event.isVisible && this.openSection === 'openLinks') {
                  this.openSection = '';
                }
              }
            })
            this.sectionDivider()

            // ---- Gestures section (presentation-level switches) ----
            Text('手势')
              .fontSize(13)
              .fontWeight(FontWeight.Medium)
              .fontColor(this.uiDark ? '#eceef2' : '#6f7682')
              .width('100%')
              .padding({ top: 20, bottom: 4, left: 16 })
            this.gestureSwitchRow('下滑', KEY_GESTURE_SWIPE_DOWN, this.gestureSwipeDown)
            this.sectionDivider()
            this.gestureSwitchRow('上滑', KEY_GESTURE_SWIPE_UP, this.gestureSwipeUp)
            this.sectionDivider()
            this.gestureSwitchRow('右滑', KEY_GESTURE_SWIPE_RIGHT, this.gestureSwipeRight)
            this.sectionDivider()
            this.gestureSwitchRow('左滑', KEY_GESTURE_SWIPE_LEFT, this.gestureSwipeLeft)
            this.sectionDivider()

            // ---- Account section ----
            Text('账号')
              .fontSize(13)
              .fontWeight(FontWeight.Medium)
              .fontColor(this.uiDark ? '#eceef2' : '#6f7682')
              .width('100%')
              .padding({ top: 20, bottom: 4, left: 16 })
            Row() {
              Text('账号')
                .fontSize(16)
                .fontColor(this.uiDark ? '#ffffff' : '#1a1a1a')
                .layoutWeight(1)
              Text(this.accountSource === 'local' ? '本地' : this.accountSource)
                .fontSize(14)
                .fontColor(this.uiDark ? '#eceef2' : '#6f7682')
            }
            .width('100%')
            .padding({ top: 12, bottom: 12, left: 16, right: 16 })
            this.sectionDivider()
            Text(this.accountId.length > 0 ? this.accountId : '（暂无账号）')
              .fontSize(12)
              .fontColor(this.uiDark ? '#eceef2' : '#6f7682')
              .width('100%')
              .padding({ top: 10, bottom: 10, left: 16, right: 16 })
            this.sectionDivider()
            Row() {
              Text('退出登录')
                .fontSize(16)
                .fontWeight(FontWeight.Medium)
                .fontColor('#e23c3c')
            }
            .width('100%')
            .justifyContent(FlexAlign.Center)
            .padding({ top: 14, bottom: 14 })
            .onClick(() => {
              this.requestLogOut();
            })
            this.sectionDivider()

            // ---- About section ----
            Text('关于')
              .fontSize(13)
              .fontWeight(FontWeight.Medium)
              .fontColor(this.uiDark ? '#eceef2' : '#6f7682')
              .width('100%')
              .padding({ top: 20, bottom: 4, left: 16 })
            Row() {
              Text('CapyReader')
                .fontSize(16)
                .fontColor(this.uiDark ? '#ffffff' : '#1a1a1a')
                .layoutWeight(1)
            }
            .width('100%')
            .padding({ top: 12, bottom: 12, left: 16, right: 16 })
            this.sectionDivider()
            Row() {
              Text('版本')
                .fontSize(16)
                .fontColor(this.uiDark ? '#ffffff' : '#1a1a1a')
                .layoutWeight(1)
              Text(APP_VERSION_TEXT)
                .fontSize(14)
                .fontColor(this.uiDark ? '#eceef2' : '#6f7682')
            }
            .width('100%')
            .padding({ top: 12, bottom: 12, left: 16, right: 16 })
            this.sectionDivider()
            Row() {
              Text('源码')
                .fontSize(16)
                .fontColor(this.uiDark ? '#ffffff' : '#1a1a1a')
                .layoutWeight(1)
              Text('github.com/jocmp/capyreader')
                .fontSize(14)
                .fontColor('#2b7cf6')
            }
            .width('100%')
            .padding({ top: 12, bottom: 12, left: 16, right: 16 })
            this.sectionDivider()
            Row() {
              Text('开源许可')
                .fontSize(16)
                .fontColor(this.uiDark ? '#ffffff' : '#1a1a1a')
                .layoutWeight(1)
              Text('GPL-3.0')
                .fontSize(14)
                .fontColor(this.uiDark ? '#eceef2' : '#6f7682')
            }
            .width('100%')
            .padding({ top: 12, bottom: 12, left: 16, right: 16 })
            this.sectionDivider()
          }
          .width('100%')
          .alignItems(HorizontalAlign.Start)
          .id('PAGE-SETTINGSVIEW-9331B5E9')
        }
        .layoutWeight(1)
        .scrollBar(BarState.Off)
        .align(Alignment.TopStart)
      }
      .width('100%')
      .height('100%')
      .backgroundColor(this.uiDark ? '#1a1a1a' : '#f5f6f8')
    }
    .hideTitleBar(true)
    .title('PAGE-SETTINGSSCREEN-D0A9FF8D')
    .id('ShellPageSettingsscreenD0a9ff8d')
  }
}
