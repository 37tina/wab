// Foundation (Phase 3 native UI base): List + LazyForEach shell with
// empty/loading state slots.
//
// Pure shell, no business logic. The data source ships empty; Phase 4 binds
// real item data through the registered module contracts. Hand-drawing custom
// virtualized list chassis is prohibited.

export class FoundationListDataSource implements IDataSource {
  private items: string[] = [];
  private listeners: DataChangeListener[] = [];

  totalCount(): number {
    return this.items.length;
  }

  getData(index: number): string {
    return this.items[index];
  }

  registerDataChangeListener(listener: DataChangeListener): void {
    if (this.listeners.indexOf(listener) < 0) {
      this.listeners.push(listener);
    }
  }

  unregisterDataChangeListener(listener: DataChangeListener): void {
    const position = this.listeners.indexOf(listener);
    if (position >= 0) {
      this.listeners.splice(position, 1);
    }
  }
}

@Component
export struct AppListShell {
  private dataSource: FoundationListDataSource = new FoundationListDataSource();
  @Prop isLoading: boolean = false;
  @BuilderParam itemBuilder: (item: string) => void = this.defaultItemBuilder;
  @BuilderParam emptyBuilder: () => void = this.defaultEmptyBuilder;
  @BuilderParam loadingBuilder: () => void = this.defaultLoadingBuilder;

  @Builder
  defaultItemBuilder(item: string) {
    Text(item)
      .id('AppListShellItem')
  }

  @Builder
  defaultEmptyBuilder() {
    Column() {}
      .id('AppListShellEmpty')
      .width('100%')
      .height('100%')
  }

  @Builder
  defaultLoadingBuilder() {
    Column() {
      LoadingProgress()
        .width(32)
        .height(32)
    }
    .justifyContent(FlexAlign.Center)
    .alignItems(HorizontalAlign.Center)
    .id('AppListShellLoading')
    .width('100%')
    .height('100%')
  }

  build() {
    Column() {
      if (this.isLoading) {
        this.loadingBuilder()
      } else if (this.dataSource.totalCount() === 0) {
        this.emptyBuilder()
      } else {
        List({ space: 0 }) {
          LazyForEach(this.dataSource, (item: string) => {
            ListItem() {
              this.itemBuilder(item)
            }
          }, (item: string) => item)
        }
        .width('100%')
        .height('100%')
      }
    }
    .id('AppListShell')
    .width('100%')
    .height('100%')
  }
}
