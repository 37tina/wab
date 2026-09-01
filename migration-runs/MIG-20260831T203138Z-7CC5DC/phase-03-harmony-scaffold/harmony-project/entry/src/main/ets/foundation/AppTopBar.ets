// Foundation (Phase 3 native UI base): ArkUI-native top bar with back behavior.
//
// Pure shell, no business logic. Back behavior is a callback placeholder;
// Phase 4 binds it to NavPathStack pop / Tabs switching per the route graph.

@Component
export struct AppTopBar {
  @Prop title: string = '';
  @Prop showBack: boolean = true;
  onBack: () => void = () => {};

  build() {
    Row({ space: 8 }) {
      if (this.showBack) {
        Text('←')
          .fontSize(22)
          .onClick(() => {
            this.onBack();
          })
          .id('AppTopBarBack')
      }
      Text(this.title)
        .fontSize(18)
        .fontWeight(FontWeight.Medium)
        .maxLines(1)
        .textOverflow({ overflow: TextOverflow.Ellipsis })
        .layoutWeight(1)
        .id('AppTopBarTitle')
      Blank()
        .width(30)
    }
    .alignItems(VerticalAlign.Center)
    .padding({ left: 16, right: 16 })
    .width('100%')
    .height(56)
    .id('AppTopBar')
  }
}
