// Entry page: hosts the native navigation foundation and opens the launch
// route. FEAT-LOCAL-ACCOUNT business rule (MainActivity.startDestination
// parity): an existing account_id goes straight to the Articles main
// screen; a fresh install (no account) lands on Add Account. The
// ROUTE_SMOKE 'routeName' want parameter keeps priority so Phase 3/4
// route injection tooling stays deterministic.
import { AppNavigationShell } from '../foundation/AppNavigationShell';
import { AccountRepository, registerAccountProbeProviders } from '../data/AccountRepository';

const SMOKE_HOME_ROUTE: string = 'PAGE-ARTICLESCREEN-23AF0624';
const ADD_ACCOUNT_ROUTE: string = 'PAGE-ADDACCOUNTSCREEN-A9C749BC';
const smokeRoute: string | undefined = AppStorage.get<string>('smokeRouteName');

@Entry
@Component
struct Index {
  @State initialRoute: string = SMOKE_HOME_ROUTE;

  aboutToAppear(): void {
    const ctx = getContext(this);
    registerAccountProbeProviders(ctx);
    if (typeof smokeRoute === 'string' && smokeRoute !== '') {
      this.initialRoute = smokeRoute;
      return;
    }
    const repo = AccountRepository.obtain(ctx);
    this.initialRoute = repo.hasAccount() ? SMOKE_HOME_ROUTE : ADD_ACCOUNT_ROUTE;
  }

  build() {
    Column() {
      AppNavigationShell({ initialRoute: this.initialRoute })
    }
    .id('MigrationScaffold')
    .width('100%')
    .height('100%')
  }
}
