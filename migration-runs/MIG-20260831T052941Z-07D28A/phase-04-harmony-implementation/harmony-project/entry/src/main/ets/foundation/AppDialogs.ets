// Foundation (Phase 3 native UI base): CustomDialog / bindSheet shells.
//
// Pure shell, no business logic. ArkTS does not export @CustomDialog structs,
// so AppConfirmDialogShell stays file-local and AppDialogHost exposes the
// controller / sheet wiring for page shells to compose.

@CustomDialog
struct AppConfirmDialogShell {
  controller?: CustomDialogController;
  title: string = '';
  onConfirm: () => void = () => {};
  onCancel: () => void = () => {};

  build() {
    Column({ space: 16 }) {
      Text(this.title)
        .fontSize(18)
        .fontWeight(FontWeight.Medium)
        .id('AppConfirmDialogTitle')
      Row({ space: 16 }) {
        Button('Cancel')
          .onClick(() => {
            this.onCancel();
            if (this.controller !== undefined) {
              this.controller.close();
            }
          })
          .id('AppConfirmDialogCancel')
        Button('Confirm')
          .onClick(() => {
            this.onConfirm();
            if (this.controller !== undefined) {
              this.controller.close();
            }
          })
          .id('AppConfirmDialogConfirm')
      }
    }
    .padding(24)
    .width('100%')
    .id('AppConfirmDialogShell')
  }
}

@Component
export struct AppSheetShell {
  @BuilderParam sheetContent: () => void = this.defaultSheetContent;

  @Builder
  defaultSheetContent() {
    Column() {}
      .id('AppSheetShellContent')
      .width('100%')
      .height('100%')
  }

  build() {
    Column() {
      this.sheetContent()
    }
    .id('AppSheetShell')
    .width('100%')
  }
}

@Component
export struct AppDialogHost {
  @State sheetVisible: boolean = false;
  @BuilderParam hostContent: () => void = this.defaultHostContent;
  dialogController: CustomDialogController = new CustomDialogController({
    builder: AppConfirmDialogShell({ title: '' }),
    alignment: DialogAlignment.Center,
    customStyle: false,
  });

  @Builder
  defaultHostContent() {
    Column() {}
      .id('AppDialogHostContent')
      .width('100%')
      .height('100%')
  }

  @Builder
  sheetBuilder() {
    AppSheetShell()
  }

  build() {
    Column() {
      this.hostContent()
    }
    .bindSheet($$this.sheetVisible, this.sheetBuilder(), {
      height: SheetSize.MEDIUM,
      dragBar: true,
    })
    .id('AppDialogHost')
    .width('100%')
    .height('100%')
  }
}
