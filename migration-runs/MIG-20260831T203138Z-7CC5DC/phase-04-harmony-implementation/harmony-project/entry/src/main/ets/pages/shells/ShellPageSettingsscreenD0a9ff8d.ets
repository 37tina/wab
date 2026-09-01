// SettingsScreen - FEAT-SETTINGS (impl-lead.capy-01 R5, batch 3).
// Real settings surface on the live prefs store (BC-0018 navigation host,
// BC-0019 Theme picker, BC-0020 article list sort order):
//   Display  > Theme (System default / Light / Dark) -> prefs app_theme +
//             theme_mode + ApplicationContext.setColorMode, immediate effect
//   General  > Sort order (Newest first / Oldest first) -> prefs
//             article_list_sort_order; listArticles flips ORDER BY direction
// All option rows are visible-text anchors (dumpLayout rule: accessibility
// text never enters the layout dump). Phase 3 ROUTE_SMOKE transparent modal
// mounts removed here (same swallow-touch rationale as the articles shell);
// FEAT-SETTINGS wires the real carriers inline instead.
import { AccountRepository } from '../../data/AccountRepository';
import hilog from '@ohos.hilog';

const TAG = 'P4Settings';

@Component
export struct ShellPageSettingsscreenD0a9ff8d {
  @Consume('foundationPathStack') pathStack: NavPathStack | null = null;
  @StorageProp('uiDark') uiDark: boolean = false;
  @State themeMode: string = 'system';
  @State sortOrder: string = 'NEWEST_FIRST';
  @State themeOptionsOpen: boolean = false;
  @State sortOptionsOpen: boolean = false;
  private repo: AccountRepository | null = null;

  aboutToAppear(): void {
    const ctx = getContext(this);
    this.repo = AccountRepository.obtain(ctx);
    this.themeMode = this.repo.getThemeMode();
    this.sortOrder = this.repo.getSortOrder();
    hilog.info(0x0000, TAG, 'settings opened, theme=%{public}s sort=%{public}s',
      this.themeMode, this.sortOrder);
  }

  private goBack(): void {
    if (this.pathStack !== null) {
      this.pathStack.pop();
    }
  }

  private themeLabel(mode: string): string {
    if (mode === 'dark') {
      return 'Dark';
    }
    return mode === 'light' ? 'Light' : 'System default';
  }

  private sortLabel(order: string): string {
    return order === 'OLDEST_FIRST' ? 'Oldest first' : 'Newest first';
  }

  private selectTheme(mode: string): void {
    this.themeMode = mode;
    this.themeOptionsOpen = false;
    if (this.repo !== null) {
      // BC-0019: prefs app_theme/theme_mode + immediate setColorMode
      this.repo.setThemeMode(mode);
    }
  }

  private selectSort(order: string): void {
    this.sortOrder = order;
    this.sortOptionsOpen = false;
    if (this.repo !== null) {
      // BC-0020: prefs article_list_sort_order; the article list re-queries
      // with the flipped ORDER BY when the screen is shown again.
      this.repo.setSortOrder(order);
    }
  }

  @Builder
  optionRow(label: string, selected: boolean, onTap: () => void) {
    Row() {
      Text(selected ? '✓ ' + label : label)
        .fontSize(15)
        .fontColor(selected ? '#1B6EF3' : (this.uiDark ? '#E3E2E6' : '#1B1B1F'))
    }
    .width('100%')
    .padding({ top: 10, bottom: 10, left: 32 })
    .onClick(() => onTap())
  }

  build() {
    NavDestination() {
      Column() {
        // back bar
        Row({ space: 10 }) {
          Text('←')
            .fontSize(20)
            .padding(10)
            .fontColor(this.uiDark ? '#E3E2E6' : '#1B1B1F')
            .onClick(() => this.goBack())
          Text('Settings')
            .fontSize(16)
            .fontWeight(FontWeight.Medium)
            .fontColor(this.uiDark ? '#E3E2E6' : '#1B1B1F')
            .layoutWeight(1)
        }
        .width('100%')
        .alignItems(VerticalAlign.Center)
        .border({ width: { bottom: 1 }, color: this.uiDark ? '#22FFFFFF' : '#11000000' })

        Scroll() {
          Column() {
            // ---- Display section (BC-0018 anchor: text=Display) ----
            Text('Display')
              .fontSize(13)
              .fontWeight(FontWeight.Medium)
              .fontColor(this.uiDark ? '#C5C6D0' : '#666666')
              .width('100%')
              .padding({ top: 16, bottom: 4, left: 16 })
            Row() {
              Text('Theme')
                .fontSize(16)
                .fontColor(this.uiDark ? '#E3E2E6' : '#1B1B1F')
                .layoutWeight(1)
              Text(this.themeLabel(this.themeMode))
                .fontSize(14)
                .fontColor(this.uiDark ? '#C5C6D0' : '#666666')
            }
            .width('100%')
            .padding({ top: 12, bottom: 12, left: 16, right: 16 })
            .onClick(() => {
              this.sortOptionsOpen = false;
              this.themeOptionsOpen = !this.themeOptionsOpen;
            })
            Divider().color(this.uiDark ? '#22FFFFFF' : '#11000000')
            if (this.themeOptionsOpen) {
              // BC-0019 theme triple choice (visible-text anchors)
              this.optionRow('System default', this.themeMode === 'system', () => this.selectTheme('system'))
              Divider().color(this.uiDark ? '#22FFFFFF' : '#11000000')
              this.optionRow('Light', this.themeMode === 'light', () => this.selectTheme('light'))
              Divider().color(this.uiDark ? '#22FFFFFF' : '#11000000')
              this.optionRow('Dark', this.themeMode === 'dark', () => this.selectTheme('dark'))
              Divider().color(this.uiDark ? '#22FFFFFF' : '#11000000')
            }

            // ---- General section (BC-0020 anchor: text=General) ----
            Text('General')
              .fontSize(13)
              .fontWeight(FontWeight.Medium)
              .fontColor(this.uiDark ? '#C5C6D0' : '#666666')
              .width('100%')
              .padding({ top: 20, bottom: 4, left: 16 })
            Row() {
              Text('Sort order')
                .fontSize(16)
                .fontColor(this.uiDark ? '#E3E2E6' : '#1B1B1F')
                .layoutWeight(1)
              Text(this.sortLabel(this.sortOrder))
                .fontSize(14)
                .fontColor(this.uiDark ? '#C5C6D0' : '#666666')
            }
            .width('100%')
            .padding({ top: 12, bottom: 12, left: 16, right: 16 })
            .onClick(() => {
              this.themeOptionsOpen = false;
              this.sortOptionsOpen = !this.sortOptionsOpen;
            })
            Divider().color(this.uiDark ? '#22FFFFFF' : '#11000000')
            if (this.sortOptionsOpen) {
              // BC-0020 sort pair (visible-text anchors)
              this.optionRow('Newest first', this.sortOrder === 'NEWEST_FIRST', () => this.selectSort('NEWEST_FIRST'))
              Divider().color(this.uiDark ? '#22FFFFFF' : '#11000000')
              this.optionRow('Oldest first', this.sortOrder === 'OLDEST_FIRST', () => this.selectSort('OLDEST_FIRST'))
              Divider().color(this.uiDark ? '#22FFFFFF' : '#11000000')
            }
          }
          .width('100%')
          .alignItems(HorizontalAlign.Start)
        }
        .layoutWeight(1)
        .scrollBar(BarState.Off)
        .align(Alignment.TopStart)
      }
      .width('100%')
      .height('100%')
      .backgroundColor(this.uiDark ? '#1B1B1F' : '#FEFBFF')
    }
    .hideTitleBar(true)
    .title('PAGE-SETTINGSSCREEN-D0A9FF8D')
    .id('ShellPageSettingsscreenD0a9ff8d')
  }
}
