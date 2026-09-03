// AccountRepository - FEAT-LOCAL-ACCOUNT data layer (impl-lead.capy-01).
// Implements Phase 3 data-contract repository interfaces:
//   account_id (AccountIdRepository: create/restore/get/set)
//   source (SourceRepository: create/set)
//   accounts_dir (AccountsDirRepository: set)
// Physical carriers are implementer-chosen (semantic parity only):
//   account_id -> Preferences(default_prefs).account_id
//   source -> Preferences(account_<UUID>).source = 'local'
//   accounts_dir -> filesDir/accounts/<UUID>/ directory
// Mirrors Android: AccountManager.createAccount(Source.LOCAL) +
// AddAccountViewModel.selectAccount(id) + MainActivity.startDestination().
import preferences from '@ohos.data.preferences';
import util from '@ohos.util';
import fs from '@ohos.file.fs';
import hilog from '@ohos.hilog';
import { ConfigurationConstant } from '@kit.AbilityKit';
import { registerProbe } from '../probe/SemanticProbeRegistry';

const TAG = 'CapyAccountRepo';
const PREF_DEFAULT = 'capy_default_prefs';
const KEY_ACCOUNT_ID = 'account_id';
const KEY_SOURCE = 'source';
// FEAT-SETTINGS pref keys (Android AppPreferences parity, BC-0019/0020/0021)
export const KEY_APP_THEME = 'app_theme';
export const KEY_THEME_MODE = 'theme_mode';
export const KEY_SORT_ORDER = 'article_list_sort_order';
export const KEY_ARTICLE_FONT_SIZE = 'article_font_size';
export const KEY_TITLE_ALIGNMENT = 'article_title_text_alignment';

// Semantic snapshot shape exported to <files>/replay-data.json
// (self-check interface obligation for RUNTIME features; consumed by the
// Phase 4 differential verifier alongside the frozen semantic probe).
export class AccountSemanticSnapshot {
  account_id: string | null = null;
  source: string | null = null;
  accounts_dir: string | null = null;
  settings: Record<string, string> = {};
}

export class AccountRepository {
  private ctx: Context;

  private constructor(ctx: Context) {
    this.ctx = ctx;
  }

  public static obtain(ctx: Context): AccountRepository {
    return new AccountRepository(ctx);
  }

  // --- data-contract: account_id (AccountIdRepository) ---

  private defaultPrefs(): preferences.Preferences {
    return preferences.getPreferencesSync(this.ctx, { name: PREF_DEFAULT } as preferences.Options);
  }

  public getAccountId(): string {
    const p = this.defaultPrefs();
    return p.getSync(KEY_ACCOUNT_ID, '') as string;
  }

  public hasAccount(): boolean {
    return this.getAccountId().length > 0;
  }

  // --- data-contract: source (SourceRepository) ---

  private accountPrefs(accountId: string): preferences.Preferences {
    return preferences.getPreferencesSync(this.ctx,
      { name: 'account_' + accountId } as preferences.Options);
  }

  public getSource(accountId: string): string {
    const p = this.accountPrefs(accountId);
    return p.getSync(KEY_SOURCE, '') as string;
  }

  // --- domain op createLocal (BC-0001) ---
  // Select Local -> UUID account id; account_<UUID>.prefs source=local;
  // filesDir/accounts/<UUID>/ created; default prefs account_id written.

  public createLocalAccount(): string {
    const accountId = util.generateRandomUUID(true);
    const ap = this.accountPrefs(accountId);
    ap.putSync(KEY_SOURCE, 'local');
    ap.flushSync();
    const dir = this.accountsDirFor(accountId);
    if (!fs.accessSync(dir)) {
      fs.mkdirSync(dir, true);
    }
    const dp = this.defaultPrefs();
    dp.putSync(KEY_ACCOUNT_ID, accountId);
    dp.flushSync();
    hilog.info(0x0000, TAG, 'local account created: %{public}s', accountId);
    this.exportReplayData();
    return accountId;
  }

  // Rev2 #27: Settings > Account > Log Out (Android parity
  // settings_remove_account_button_service). Clears the selected account
  // id; next launch lands on Add Account (MainActivity.startDestination).
  public logOut(): void {
    const dp = this.defaultPrefs();
    dp.deleteSync(KEY_ACCOUNT_ID);
    dp.flushSync();
    hilog.info(0x0000, TAG, 'account logged out');
    this.exportReplayData();
  }

  // --- data-contract: accounts_dir (AccountsDirRepository) ---

  public accountsDirFor(accountId: string): string {
    return this.ctx.filesDir + '/accounts/' + accountId;
  }

  // --- FEAT-SETTINGS (BC-0019 theme / BC-0020 sort / BC-0021 reader style) --

  public getThemeMode(): string {
    const p = this.defaultPrefs();
    const v = p.getSync(KEY_THEME_MODE, 'system') as string;
    return v;
  }

  public setThemeMode(mode: string): void {
    const dp = this.defaultPrefs();
    // app_theme mirrors the Android enum-name persistence (BC-0019
    // data_equals prefs:app_theme); theme_mode drives setColorMode parity.
    const appTheme = mode === 'dark' ? 'DARK' : (mode === 'light' ? 'LIGHT' : 'SYSTEM');
    dp.putSync(KEY_APP_THEME, appTheme);
    dp.putSync(KEY_THEME_MODE, mode);
    dp.flushSync();
    this.applyColorMode(mode);
    hilog.info(0x0000, TAG, 'theme set: %{public}s', mode);
    this.exportReplayData();
  }

  // Applies a persisted/selected theme to the running application:
  // ApplicationContext.setColorMode gives immediate platform-level dark
  // (dialogs, system chrome) and AppStorage 'uiDark' drives the in-app
  // token swap on every page built on @StorageProp('uiDark').
  public applyColorMode(mode: string): void {
    try {
      const appCtx = this.ctx.getApplicationContext();
      if (mode === 'dark') {
        appCtx.setColorMode(ConfigurationConstant.ColorMode.COLOR_MODE_DARK);
      } else if (mode === 'light') {
        appCtx.setColorMode(ConfigurationConstant.ColorMode.COLOR_MODE_LIGHT);
      } else {
        appCtx.setColorMode(ConfigurationConstant.ColorMode.COLOR_MODE_NOT_SET);
      }
      AppStorage.setOrCreate('uiDark', mode === 'dark');
    } catch (e) {
      hilog.error(0x0000, TAG, 'setColorMode failed: %{public}s', JSON.stringify(e));
    }
  }

  // BC-0017 cold-start leg: restore the persisted theme before the first
  // frame (called from EntryAbility.onCreate).
  public applyPersistedTheme(): void {
    this.applyColorMode(this.getThemeMode());
  }

  public getSortOrder(): string {
    const p = this.defaultPrefs();
    return p.getSync(KEY_SORT_ORDER, 'NEWEST_FIRST') as string;
  }

  public setSortOrder(order: string): void {
    const dp = this.defaultPrefs();
    dp.putSync(KEY_SORT_ORDER, order);
    dp.flushSync();
    hilog.info(0x0000, TAG, 'sort order set: %{public}s', order);
    this.exportReplayData();
  }

  // BC-0021 reader style prefs (font size / title alignment)
  public getReaderStyle(key: string, fallback: string): string {
    const p = this.defaultPrefs();
    return p.getSync(key, fallback) as string;
  }

  public setReaderStyle(key: string, value: string): void {
    const dp = this.defaultPrefs();
    dp.putSync(key, value);
    dp.flushSync();
  }

  // --- semantic snapshot + self-check export ---

  public snapshot(): AccountSemanticSnapshot {
    const snap = new AccountSemanticSnapshot();
    const id = this.getAccountId();
    if (id.length > 0) {
      snap.account_id = id;
      const s = this.getSource(id);
      snap.source = s.length > 0 ? s : null;
      const dir = this.accountsDirFor(id);
      snap.accounts_dir = fs.accessSync(dir) ? dir : null;
    }
    const p = this.defaultPrefs();
    snap.settings = {
      'app_theme': p.getSync(KEY_APP_THEME, 'SYSTEM') as string,
      'theme_mode': p.getSync(KEY_THEME_MODE, 'system') as string,
      'article_list_sort_order': p.getSync(KEY_SORT_ORDER, 'NEWEST_FIRST') as string,
      'article_filter': p.getSync('article_filter', 'status=ALL') as string
    };
    return snap;
  }

  public exportReplayData(): void {
    try {
      const json = JSON.stringify(this.snapshot());
      const target = this.ctx.filesDir + '/replay-data.json';
      const exists = fs.accessSync(target);
      const file = fs.openSync(target,
        fs.OpenMode.READ_WRITE | fs.OpenMode.CREATE | (exists ? fs.OpenMode.TRUNC : 0));
      fs.writeSync(file.fd, json);
      fs.closeSync(file);
      hilog.info(0x0000, TAG, 'replay-data.json exported');
    } catch (e) {
      hilog.error(0x0000, TAG, 'replay-data export failed: %{public}s',
        JSON.stringify(e));
    }
  }
}

// --- SemanticProbeRegistry wiring (real providers, read the live store) ---
// Frozen probe (DebugSemanticProbe.ets) polls collectProbeSnapshot() and
// writes files/semantic-probe.json + hilog SNAPSHOT lines; these providers
// are the real data exit consumed by the Phase 4 differential verifier.

let providersRegistered = false;

export function registerAccountProbeProviders(ctx: Context): void {
  if (providersRegistered) {
    return;
  }
  providersRegistered = true;
  const repo = AccountRepository.obtain(ctx);
  registerProbe('account_id', (): object | null => {
    const v = repo.getAccountId();
    if (v.length === 0) {
      return null;
    }
    return v as Object;
  });
  registerProbe('source', (): object | null => {
    const id = repo.getAccountId();
    if (id.length === 0) {
      return null;
    }
    const s = repo.getSource(id);
    return s.length > 0 ? s as Object : null;
  });
  registerProbe('accounts_dir', (): object | null => {
    const id = repo.getAccountId();
    if (id.length === 0) {
      return null;
    }
    const dir = repo.accountsDirFor(id);
    return fs.accessSync(dir) ? dir as Object : null;
  });
  registerProbe('settings', (): object | null => {
    // FEAT-SETTINGS probe keys (BC-0019/0020 data anchors): app_theme /
    // theme_mode / article_list_sort_order now read the live prefs.
    const p = preferences.getPreferencesSync(ctx,
      { name: PREF_DEFAULT } as preferences.Options);
    const settingsMap: Record<string, Object> = {};
    settingsMap['article_filter'] = p.getSync('article_filter', 'status=ALL') as Object;
    settingsMap['app_theme'] = p.getSync(KEY_APP_THEME, 'SYSTEM') as Object;
    settingsMap['theme_mode'] = p.getSync(KEY_THEME_MODE, 'system') as Object;
    settingsMap['article_list_sort_order'] = p.getSync(KEY_SORT_ORDER, 'NEWEST_FIRST') as Object;
    settingsMap['article_font_size'] = p.getSync(KEY_ARTICLE_FONT_SIZE, 'MEDIUM') as Object;
    settingsMap['article_title_text_alignment'] =
      p.getSync(KEY_TITLE_ALIGNMENT, 'START') as Object;
    return JSON.stringify(settingsMap) as Object;
  });
  hilog.info(0x0000, TAG, 'probe providers registered');
}
