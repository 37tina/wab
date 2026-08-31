// Entry page: hosts the native navigation foundation and opens the single
// frozen page-shell route (minimum route-opening behavior for smoke tests;
// contract-only, no business logic).
import { AppNavigationShell } from '../foundation/AppNavigationShell';

@Entry
@Component
struct Index {
  build() {
    Column() {
      AppNavigationShell({ initialRoute: 'PAGE-MAINACTIVITY-3FDE9431' })
    }
    .id('MigrationScaffold')
    .width('100%')
    .height('100%')
  }
}
