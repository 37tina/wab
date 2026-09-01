// Entry page: hosts the native navigation foundation and opens the frozen
// home route (minimum route-opening behavior for smoke tests; contract-only,
// no business logic). Registered by nav-shell.capy-01.
import { AppNavigationShell } from '../foundation/AppNavigationShell';

// ROUTE_SMOKE route selection (nav-shell.capy-01): EntryAbility stores the
// aa-start 'routeName' want parameter into AppStorage; Index passes it to the
// navigation shell as the launch route (defaults to the frozen home route).
const SMOKE_HOME_ROUTE: string = 'PAGE-ARTICLESCREEN-23AF0624';
const smokeRoute: string | undefined = AppStorage.get<string>('smokeRouteName');

@Entry
@Component
struct Index {
  build() {
    Column() {
      AppNavigationShell({ initialRoute: smokeRoute ?? SMOKE_HOME_ROUTE })
    }
    .id('MigrationScaffold')
    .width('100%')
    .height('100%')
  }
}
