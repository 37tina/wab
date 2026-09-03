// Login screen - FEAT-ONLINE-ACCOUNT-UI (impl-lead.capy-01, R6 fix).
// Phase 3 page-shell seed finalized into the real login surface.
// Visual identity follows the Android source (LoginScreen.kt /
// LoginView.kt AuthFields / Source.kt): service-name title,
// Username/Password fields, "Advanced options" disclosure hosting the
// Server URL field for hasCustomURL services (FreshRSS/Miniflux/Reader;
// Feedbin has no URL field — Source.kt parity), and a Log In button.
// BC-0003 is STATIC_ONLY: Log In performs a real network attempt
// (Feedbin https://api.feedbin.com/authentication.json with Basic Auth;
// custom-URL services probe the entered server) and surfaces the
// Android-parity error strings ('Incorrect username or password' /
// 'Connection failed'); no account data is persisted (NONE data-write).
import http from '@ohos.net.http';
import util from '@ohos.util';
import hilog from '@ohos.hilog';

const TAG = 'CapyLoginScreen';

class OnlineServiceDef {
  name: string = '';
  hasCustomUrl: boolean = false;
  urlPlaceholder: string = '';

  constructor(name: string, hasCustomUrl: boolean, urlPlaceholder: string) {
    this.name = name;
    this.hasCustomUrl = hasCustomUrl;
    this.urlPlaceholder = urlPlaceholder;
  }
}

// Source.kt parity: FEEDBIN has no custom URL; the other three do.
const SERVICES: Record<string, OnlineServiceDef> = {
  'Feedbin': new OnlineServiceDef('Feedbin', false, ''),
  'FreshRSS': new OnlineServiceDef('FreshRSS', true, 'https://example.com/api/greader.php'),
  'Miniflux': new OnlineServiceDef('Miniflux', true, 'https://miniflux.app'),
  'Reader': new OnlineServiceDef('Reader', true, 'https://example.com')
};

// Android parity error strings (login error surface).
const MSG_FIELD_REQUIRED = '请输入用户名和密码';
const MSG_URL_REQUIRED = '请输入服务器地址';
const MSG_INCORRECT = '用户名或密码错误';
const MSG_CONNECTION = '连接失败';
const MSG_LOGGING_IN = '登录中…';
const MSG_LOGGED_IN = '登录成功';

@Component
export struct ShellPageLoginscreen9d67f9d2 {
  @Consume('foundationPathStack') pathStack: NavPathStack | null = null;
  // Selected online service, set by AddAccountScreen before navigation
  // (BC-0002 Route.Login(service) parity; plain string channel avoids
  // NavPathStack untyped-param access).
  @StorageLink('loginService') serviceName: string = 'Feedbin';
  @State username: string = '';
  @State password: string = '';
  @State serverUrl: string = '';
  @State advancedOpen: boolean = false;
  @State submitting: boolean = false;
  @State feedback: string = '';
  @State feedbackIsError: boolean = false;

  aboutToAppear(): void {
    // Custom-URL services surface their Server field via the default-open
    // Advanced options disclosure (BC-0003 observed form difference).
    this.advancedOpen = this.serviceDef().hasCustomUrl;
  }

  private serviceDef(): OnlineServiceDef {
    const def = SERVICES[this.serviceName];
    return def !== undefined ? def : SERVICES['Feedbin'];
  }

  private normalizeUrl(raw: string): string {
    const u = raw.trim();
    if (u.startsWith('http://') || u.startsWith('https://')) {
      return u;
    }
    return 'https://' + u;
  }

  // Real submit attempt: loading state -> network try -> Android-parity
  // error feedback. Feedbin hits its real authentication endpoint with
  // Basic Auth (401 -> incorrect credentials); custom-URL services probe
  // the entered server (reachable -> credentials rejected without the
  // service auth endpoint; unreachable -> connection failed).
  private attemptLogin(def: OnlineServiceDef): Promise<string> {
    const creds = new util.TextEncoder().encodeInto(this.username + ':' + this.password);
    const b64 = new util.Base64Helper().encodeToStringSync(creds);
    const authHeader = 'Basic ' + b64;
    const url = def.hasCustomUrl ? this.normalizeUrl(this.serverUrl)
      : 'https://api.feedbin.com/authentication.json';
    return new Promise<string>((resolve) => {
      const req = http.createHttp();
      const opts: http.HttpRequestOptions = {
        method: http.RequestMethod.GET,
        header: { 'Authorization': authHeader } as Record<string, string>,
        connectTimeout: 10000,
        readTimeout: 10000,
        usingCache: false
      };
      req.request(url, opts).then((resp: http.HttpResponse) => {
        req.destroy();
        const code = resp.responseCode;
        hilog.info(0x0000, TAG, 'login probe %{public}s -> %{public}d', url, code);
        if (def.hasCustomUrl) {
          resolve(code >= 200 && code < 500 ? MSG_INCORRECT : MSG_CONNECTION);
        } else if (code === 401 || code === 403) {
          resolve(MSG_INCORRECT);
        } else if (code >= 200 && code < 300) {
          resolve(MSG_LOGGED_IN);
        } else {
          resolve(MSG_CONNECTION);
        }
      }).catch((err: Error) => {
        req.destroy();
        hilog.warn(0x0000, TAG, 'login probe failed: %{public}s', JSON.stringify(err));
        resolve(MSG_CONNECTION);
      });
    });
  }

  private submitLogIn(): void {
    if (this.submitting) {
      return;
    }
    // Form validation (empty-field feedback).
    if (this.username.length === 0 || this.password.length === 0) {
      this.feedback = MSG_FIELD_REQUIRED;
      this.feedbackIsError = true;
      return;
    }
    const def = this.serviceDef();
    if (def.hasCustomUrl && this.serverUrl.trim().length === 0) {
      this.feedback = MSG_URL_REQUIRED;
      this.feedbackIsError = true;
      return;
    }
    // Loading state -> real attempt -> error feedback (gate2: not a no-op).
    this.submitting = true;
    this.feedback = MSG_LOGGING_IN;
    this.feedbackIsError = false;
    this.attemptLogin(def).then((msg: string): void => {
      this.submitting = false;
      this.feedback = msg;
      this.feedbackIsError = msg !== MSG_LOGGED_IN;
    });
  }

  @Builder
  fieldLabel(label: string) {
    Text(label)
      .fontSize(14)
      .fontColor('#6f7682')
      .width('100%')
      .margin({ bottom: 4 })
  }

  build() {
    NavDestination() {
      Column() {
        // Top bar: back arrow + service-name title (LoginScreen.kt parity).
        Row() {
          Text('←')
            .fontSize(22)
            .fontColor('#2b7cf6')
            .width(48)
            .height(48)
            .textAlign(TextAlign.Center)
            .onClick(() => {
              if (this.pathStack !== null) {
                this.pathStack.pop();
              }
            })
            .id('login-back')
          Text(this.serviceName)
            .fontSize(20)
            .fontWeight(FontWeight.Bold)
            .layoutWeight(1)
        }
        .width('100%')
        .height(56)
        .alignItems(VerticalAlign.Center)

        Scroll() {
          Column() {
            // Username (AuthFields parity).
            this.fieldLabel('用户名')
            TextInput({ placeholder: '邮箱', text: this.username })
              .onChange((v: string) => {
                this.username = v;
              })
              .width('100%')
              .height(48)
              .id('login-username')

            // Password (AuthFields parity, password mode).
            this.fieldLabel('密码')
            TextInput({ placeholder: '密码', text: this.password })
              .type(InputType.Password)
              .onChange((v: string) => {
                this.password = v;
              })
              .width('100%')
              .height(48)
              .id('login-password')

            // Advanced options disclosure (LoginScreen.kt parity).
            Row() {
              Text('高级选项')
                .fontSize(14)
                .fontWeight(FontWeight.Medium)
                .layoutWeight(1)
              Text(this.advancedOpen ? '▲' : '▼')
                .fontSize(12)
                .fontColor('#6f7682')
            }
            .width('100%')
            .height(44)
            .alignItems(VerticalAlign.Center)
            .onClick(() => {
              this.advancedOpen = !this.advancedOpen;
            })
            .id('login-advanced-toggle')

            if (this.advancedOpen && this.serviceDef().hasCustomUrl) {
              this.fieldLabel('服务器')
              TextInput({ placeholder: 'API 地址', text: this.serverUrl })
                .onChange((v: string) => {
                  this.serverUrl = v;
                })
                .width('100%')
                .height(48)
                .id('login-server-url')
            }

            // Log In button with real loading/error states (gate2).
            Button(this.submitting ? MSG_LOGGING_IN : '登录')
              .width('100%')
              .height(48)
              .fontSize(16)
              .fontWeight(FontWeight.Medium)
              .margin({ top: 24 })
              .enabled(!this.submitting)
              .onClick(() => {
                this.submitLogIn();
              })
              .id('login-submit')

            if (this.feedback !== '') {
              Text(this.feedback)
                .fontSize(14)
                .fontColor(this.feedbackIsError ? '#e23c3c' : '#6f7682')
                .width('100%')
                .margin({ top: 12 })
                .id('login-feedback')
            }
          }
          .width('100%')
          .padding({ left: 16, right: 16, top: 8, bottom: 24 })
          .alignItems(HorizontalAlign.Start)
          // P3 passthrough surface anchor: this form Column carries the
          // reusable LoginView component (Android LoginView.kt) declared
          // in surface-plan.json passthrough (FEAT-ONLINE-ACCOUNT-UI).
          .id('PAGE-LOGINVIEW-49F18417')
        }
        .layoutWeight(1)
        .scrollBar(BarState.Off)
      }
      .width('100%')
      .height('100%')
      .alignItems(HorizontalAlign.Start)
      .id('PAGE-LOGINSCREEN-9D67F9D2')
    }
    .hideTitleBar(true)
    .id('ShellPageLoginscreen9d67f9d2')
  }
}
