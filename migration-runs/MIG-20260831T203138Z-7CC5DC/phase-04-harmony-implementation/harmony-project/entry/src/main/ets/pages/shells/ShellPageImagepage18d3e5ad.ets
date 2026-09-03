// PAGE-IMAGEPAGE-18D3E5AD (FEAT-ARTICLE-READ, BC-0012 surface) -
// R3-SLICE-9 end-to-end implementation, aligned with Android
// ui/articles/media/ArticleMediaView.kt:
//   full-screen black photo viewer over the article images - Swiper paging
//   (multi-image), pinch-to-zoom 1x..4x (base-scale clamp, reset on page
//   change), single tap toggles the overlay (top-right close button +
//   bottom page counter), close button / system Back pops back to the
//   previous page (reader / article list).
// Honest entry note (TOOL_GAP): RichText body images are not
// tap-interceptable on this SDK, so the entries are the reader toolbar
// 图片 button (all content images) and the article-list long-press
// 查看首图 item (first image) - recorded in the R3 checklist.
// Route param: JSON string { images: string[], index: number }.
import hilog from '@ohos.hilog';

interface ImagePageParam {
  images: string[];
  index: number;
}

@Component
export struct ShellPageImagepage18d3e5ad {
  @Consume('foundationPathStack') pathStack: NavPathStack | null = null;
  @State images: string[] = [];
  @State current: number = 0;
  @State overlayVisible: boolean = true;
  @State zoomScale: number = 1;
  @State imageReady: boolean = false;
  private pinchBase: number = 1;

  private close(): void {
    if (this.pathStack !== null) {
      this.pathStack.pop();
    }
  }

  build() {
    NavDestination() {
      Stack() {
        if (this.images.length > 0) {
          Swiper() {
            ForEach(this.images, (url: string, idx: number) => {
              Image(url)
                .objectFit(ImageFit.Contain)
                .width('100%')
                .height('100%')
                .scale({ x: this.zoomScale, y: this.zoomScale })
                .onComplete(() => {
                  this.imageReady = true;
                })
                .onClick(() => {
                  // Source parity: tap toggles the overlay chrome.
                  this.overlayVisible = !this.overlayVisible;
                })
                .gesture(
                  PinchGesture({ fingers: 2 })
                    .onActionStart(() => {
                      this.pinchBase = this.zoomScale;
                    })
                    .onActionUpdate((event: GestureEvent) => {
                      const next = this.pinchBase * event.scale;
                      this.zoomScale = Math.min(4, Math.max(1, next));
                    })
                )
            }, (url: string, idx: number) => idx + '_' + url)
          }
          .index(this.current)
          .loop(false)
          .indicator(false)
          .onChange((i: number) => {
            this.current = i;
            this.zoomScale = 1;
          })
          if (!this.imageReady) {
            LoadingProgress()
              .width(40)
              .height(40)
              .color('#ffffff')
          }
        } else {
          Text('无图片')
            .fontSize(16)
            .fontColor('#eceef2')
        }
        if (this.overlayVisible) {
          // Overlay chrome (source MediaScaffold parity): close button
          // top-right + page counter bottom-center. The overlay column is
          // hit-through (Transparent) so swiper gestures keep working.
          Column() {
            Row() {
              Blank()
              Text('✕')
                .fontSize(18)
                .fontColor('#ffffff')
                .textAlign(TextAlign.Center)
                .width(40)
                .height(40)
                .backgroundColor('#99000000')
                .borderRadius(20)
                .onClick(() => this.close())
            }
            .width('100%')
            .alignItems(VerticalAlign.Center)
            .padding({ left: 16, right: 16, top: 40 })

            Blank()

            Column() {
              Text((this.current + 1) + ' / ' + this.images.length)
                .fontSize(14)
                .fontColor('#ffffff')
                .backgroundColor('#99000000')
                .borderRadius(12)
                .padding({ left: 12, right: 12, top: 4, bottom: 4 })
            }
            .width('100%')
            .alignItems(HorizontalAlign.Center)
            .padding({ bottom: 32 })
          }
          .width('100%')
          .height('100%')
          .hitTestBehavior(HitTestMode.Transparent)
        }
      }
      .width('100%')
      .height('100%')
      .backgroundColor('#1a1a1a')
      .id('PAGE-IMAGEPAGE-18D3E5AD')
    }
    .hideTitleBar(true)
    .title('PAGE-IMAGEPAGE-18D3E5AD')
    .id('ShellPageImagepage18d3e5ad')
    .onReady((ctx: NavDestinationContext) => {
      const raw = ctx.pathInfo.param as string;
      if (typeof raw === 'string' && raw.length > 0) {
        try {
          const p = JSON.parse(raw) as ImagePageParam;
          if (p !== null && p.images !== undefined && p.images.length > 0) {
            this.images = p.images;
            this.current = p.index > 0 && p.index < p.images.length ? p.index : 0;
          }
        } catch (e) {
          hilog.warn(0x0000, 'P4Image', 'image page param parse failed: %{public}s', JSON.stringify(e));
        }
      }
    })
    .onBackPressed(() => {
      // Handled by the navigation stack pop; keep default pop behavior.
      return false;
    })
  }
}
