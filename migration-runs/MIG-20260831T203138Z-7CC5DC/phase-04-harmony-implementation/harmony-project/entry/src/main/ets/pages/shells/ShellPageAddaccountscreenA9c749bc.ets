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
  new AccountOption('Local', 'On your device', true),
  new AccountOption('Feedbin', 'feedbin.com', false),
  new AccountOption('FreshRSS', 'freshrss.org', false),
  new AccountOption('Miniflux', 'miniflux.app', false),
  new AccountOption('Reader', 'Self-hosted Google Reader API', false)
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
        Text('Add Account')
          .fontSize(28)
          .fontWeight(FontWeight.Bold)
          .width('100%')
          .padding({ left: 16, right: 16, top: 32, bottom: 8 })
        List({ space: 0 }) {
          ForEach(ACCOUNT_OPTIONS, (opt: AccountOption) => {
            ListItem() {
              Column() {
                Row({ space: 12 }) {
                  Text(opt.title)
                    .fontSize(16)
                    .fontWeight(FontWeight.Medium)
                    .layoutWeight(1)
                  Text(opt.subtitle)
                    .fontSize(13)
                    .fontColor('#666666')
                    .maxLines(1)
                    .textOverflow({ overflow: TextOverflow.Ellipsis })
                }
                .width('100%')
                .height(64)
                .padding({ left: 16, right: 16 })
                .alignItems(VerticalAlign.Center)
                .onClick(() => this.onSelect(opt))
                Divider()
                  .color('#14000000')
                  .margin({ left: 16 })
              }
            }
          }, (opt: AccountOption) => opt.title)
        }
        .layoutWeight(1)
        .scrollBar(BarState.Off)
      }
      .width('100%')
      .height('100%')
      .alignItems(HorizontalAlign.Start)
      .id('PAGE-ADDACCOUNTSCREEN-A9C749BC')
    }
    .hideTitleBar(true)
    .id('ShellPageAddaccountscreenA9c749bc')
  }
}
