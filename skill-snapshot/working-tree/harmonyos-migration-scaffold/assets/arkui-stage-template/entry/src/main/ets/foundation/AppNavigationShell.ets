// Foundation (Phase 3 native UI base): ArkUI-native navigation routing shell.
//
// Pure shell, no business logic. Holds the single NavPathStack and exposes a
// route-registry placeholder. Phase 4 deterministically registers page-shell
// destinations from the Phase 3 route graph (route-graph.json) and Behavior
// Contracts; hand-drawing a custom navigation stack is prohibited.

export interface FoundationRouteEntry {
  routeId: string;
  title: string;
}

@Component
export struct AppNavigationShell {
  @Provide('foundationPathStack') pathStack: NavPathStack = new NavPathStack();
  // Route-registry placeholder: filled from route-graph.json (one entry per Route-ID).
  @State routeRegistry: FoundationRouteEntry[] = [];
  @BuilderParam homeContent: () => void = this.defaultHomeContent;

  @Builder
  defaultHomeContent() {
    Column() {}
      .id('AppNavigationShellHome')
      .width('100%')
      .height('100%')
  }

  // Destination builder placeholder: maps a registered route name to its page shell.
  @Builder
  pageMap(name: string, param?: object) {
    Column() {}
      .id(name)
      .width('100%')
      .height('100%')
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
  }
}
