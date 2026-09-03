// Add Account screen - FEAT-LOCAL-ACCOUNT (impl-lead.capy-01).
// Phase 3 page-shell seed finalized into the real feature surface.
// Visual identity follows the Android source (AddAccountView.kt):
// headline "Add Account" + five account option rows, Local first with
// subtitle "On your device"; the four sync service rows navigate to the
// login screen (BC-0002 onNavigateToLogin -> Route.Login(service),
// FEAT-ONLINE-ACCOUNT-UI R6 wiring).
// Native-first: List + ForEach rows (guidelines R1-R6 respected; no
// custom navigation/dialog/switch/picker shapes).
import { AccountRepository } from '../../data/AccountRepository';

class AccountOption {
  title: string = '';
  subtitle: string = '';
  isLocal: boolean = false;

  constructor(title: string, subtitle: string, isLocal: boolean) {
    this.title = title;
    this.subtitle = subtitle;
    this.isLocal = isLocal;
  }
}

const ACCOUNT_OPTIONS: AccountOption[] = [
  new AccountOption('本地（在设备上）', '存储在本机', true),
  new AccountOption('Feedbin', 'feedbin.com', false),
  new AccountOption('FreshRSS', 'freshrss.org', false),
  new AccountOption('Miniflux', 'miniflux.app', false),
  new AccountOption('Reader', '自托管 Google Reader API', false)
];

@Component
export struct ShellPageAddaccountscreenA9c749bc {
  @Consume('foundationPathStack') pathStack: NavPathStack | null = null;
  @State creating: boolean = false;

  private onSelect(opt: AccountOption): void {
    if (this.creating) {
      return;
    }
    if (opt.isLocal) {
      this.creating = true;
      const repo = AccountRepository.obtain(getContext(this));
      repo.createLocalAccount();
      // Leave Add Account -> Articles main screen (BC-0001 observable).
      if (this.pathStack !== null) {
        this.pathStack.replacePathByName('PAGE-ARTICLESCREEN-23AF0624', undefined, true);
      }
      return;
    }
    // Online service rows -> login screen titled with the service name
    // (BC-0002 onNavigateToLogin -> Route.Login(service) parity).
    AppStorage.setOrCreate('loginService', opt.title);
    if (this.pathStack !== null) {
      this.pathStack.pushPathByName('PAGE-LOGINSCREEN-9D67F9D2', opt.title);
    }
  }

  build() {
    NavDestination() {
      Column() {
        // DESIGN.md H1: 20/600, --text #1a1a1a, spacing 24 between blocks, card padding 16-20
        Text('添加账号')
          .fontSize(20)
          .fontWeight(600)
          .fontColor('#1a1a1a')
          .width('100%')
          .padding({ left: 16, right: 16, top: 24, bottom: 16 })
        // DESIGN.md card list: 白底 + 1px --line (#eceef2) + 12 圆角，间距 12，禁止多层嵌套
        List({ space: 12 }) {
          ForEach(ACCOUNT_OPTIONS, (opt: AccountOption) => {
            ListItem() {
              Column() {
                Row({ space: 12 }) {
                  Text(opt.title)
                    // DESIGN.md 卡片 H3: 15/600，--text #1a1a1a
                    .fontSize(15)
                    .fontWeight(600)
                    .fontColor('#1a1a1a')
                    .layoutWeight(1)
                  Text(opt.subtitle)
                    // DESIGN.md 次要说明: 12.5-13 / 行高 1.6, --text-3 #6f7682
                    .fontSize(13)
                    .fontColor('#6f7682')
                    .maxLines(1)
                    .textOverflow({ overflow: TextOverflow.Ellipsis })
                }
                .width('100%')
                .height(64)
                .padding({ left: 16, right: 16 })
                .alignItems(VerticalAlign.Center)
                .onClick(() => this.onSelect(opt))
              }
              .width('100%')
              .backgroundColor('#ffffff')
              .border({ width: 1, color: '#eceef2', radius: 12 })
            }
          }, (opt: AccountOption) => opt.title)
        }
        .layoutWeight(1)
        .scrollBar(BarState.Off)
        .padding({ left: 16, right: 16 })
        // P3 passthrough surface anchor: this options List carries the
        // reusable AddAccountView component (Android AddAccountView.kt)
        // declared in surface-plan.json passthrough (FEAT-ONLINE-ACCOUNT-UI).
        .id('PAGE-ADDACCOUNTVIEW-A37259FA')
      }
      .width('100%')
      .height('100%')
      .alignItems(HorizontalAlign.Start)
      .backgroundColor('#f5f6f8')
      .id('PAGE-ADDACCOUNTSCREEN-A9C749BC')
    }
    .hideTitleBar(true)
    .id('ShellPageAddaccountscreenA9c749bc')
  }
}
