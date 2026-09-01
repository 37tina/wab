// Foundation (Phase 3 native UI base): error-state shell.
//
// Pure shell, no business logic. Declares the generic error slot layout
// (icon slot + message slot + retry slot); Phase 4 binds concrete error
// copy/behavior through contracts. Registered by public-ui.capy-01
// (RT-P3-0002) to complete the nine public-UI foundation categories.

@Component
export struct ErrorShell {
  @BuilderParam errorIcon: () => void = this.defaultIcon;
  @BuilderParam errorMessage: () => void = this.defaultMessage;
  @BuilderParam retryAction: () => void = this.defaultRetry;

  @Builder
  defaultIcon() {
    Column() {}
      .width(48)
      .height(48)
      .borderRadius(24)
  }

  @Builder
  defaultMessage() {
    Column() {}
      .width('60%')
      .height(20)
  }

  @Builder
  defaultRetry() {
    Column() {}
      .width(96)
      .height(36)
      .borderRadius(18)
  }

  build() {
    Column({ space: 12 }) {
      this.errorIcon()
      this.errorMessage()
      this.retryAction()
    }
    .justifyContent(FlexAlign.Center)
    .alignItems(HorizontalAlign.Center)
    .width('100%')
    .height('100%')
    .id('ErrorShell')
  }
}
