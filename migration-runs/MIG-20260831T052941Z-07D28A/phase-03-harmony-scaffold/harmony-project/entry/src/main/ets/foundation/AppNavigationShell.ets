// Foundation (Phase 3 native UI base): ArkUI-native navigation routing shell.
//
// Pure shell, no business logic. Holds the single NavPathStack and the
// route registry. Phase 4 deterministically extends page-shell destinations
// from the Phase 3 route graph (route-registry.csv) and Behavior Contracts;
// hand-drawing a custom navigation stack is prohibited.

import { ShellPageMainactivity3fde9431 } from '../pages/shells/ShellPageMainactivity3fde9431';

export interface FoundationRouteEntry {
  routeId: string;
  title: string;
}

// Route registry (deterministic, from Phase 3 route-registry.csv; contract-only).
const ROUTE_REGISTRY: FoundationRouteEntry[] = [
  { routeId: 'PAGE-MAINACTIVITY-3FDE9431', title: 'PAGE-MAINACTIVITY-3FDE9431' }
];

@Component
export struct AppNavigationShell {
  @Provide('foundationPathStack') pathStack: NavPathStack = new NavPathStack();
  // Route-registry: one entry per Route-ID (route-registry.csv).
  @State routeRegistry: FoundationRouteEntry[] = ROUTE_REGISTRY;
  @BuilderParam homeContent: () => void = this.defaultHomeContent;
  // Minimum route-opening behavior required by ROUTE_SMOKE (no business logic).
  @Prop initialRoute: string = '';

  @Builder
  defaultHomeContent() {
    Column() {}
      .id('AppNavigationShellHome')
      .width('100%')
      .height('100%')
  }

  // Destination builder: maps a registered route name to its page shell
  // (deterministic mapping, one branch per Route-ID).
  @Builder
  pageMap(name: string, param?: object) {
    if (name === 'PAGE-MAINACTIVITY-3FDE9431') {
      ShellPageMainactivity3fde9431()
    } else {
      Column() {}
        .id(name)
        .width('100%')
        .height('100%')
    }
  }

  build() {
    Navigation(this.pathStack) {
      this.homeContent()
    }
    .navDestination(this.pageMap)
    .hideTitleBar(true)
    .mode(NavigationMode.Stack)
    .id('AppNavigationShell')
    .width('100%')
    .height('100%')
    .onAppear((): void => {
      if (this.initialRoute !== '' && this.pathStack.size() === 0) {
        this.pathStack.pushPathByName(this.initialRoute, undefined);
      }
    })
  }
}
