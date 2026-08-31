// Foundation (Phase 3 native UI base): ArkUI-native bottom Tabs shell.
//
// Pure shell, no business logic. The tab registry is a placeholder: Phase 4
// fills it from the route graph (bottom-tab groups only). Hand-drawing a
// custom bottom bar is prohibited.

export interface FoundationTabEntry {
  tabId: string;
  title: string;
}

@Component
export struct AppTabsShell {
  @State currentIndex: number = 0;
  // Tab registry placeholder: filled from route-graph.json (bottom-tab group only).
  @State tabRegistry: FoundationTabEntry[] = [];
  @BuilderParam tabContent: (entry: FoundationTabEntry) => void = this.defaultTabContent;

  @Builder
  defaultTabContent(entry: FoundationTabEntry) {
    Column() {}
      .id(entry.tabId)
      .width('100%')
      .height('100%')
  }

  build() {
    Tabs({ barPosition: BarPosition.End, index: this.currentIndex }) {
      ForEach(this.tabRegistry, (entry: FoundationTabEntry) => {
        TabContent() {
          this.tabContent(entry)
        }
        .tabBar(entry.title)
      }, (entry: FoundationTabEntry) => entry.tabId)
    }
    .scrollable(false)
    .onChange((index: number) => {
      this.currentIndex = index;
    })
    .id('AppTabsShell')
    .width('100%')
    .height('100%')
  }
}
