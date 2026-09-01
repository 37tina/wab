// ArticleReaderPage - FEAT-ARTICLE-READ + FEAT-READ-UNREAD + FEAT-STAR
// (impl-lead.capy-01, batch 2). Real reading view on the live store:
// title + feed/time header + summary body (HTML stripped to text) and a
// bottom action bar with read/unread toggle (desc "Mark as read"),
// star toggle (desc "Star") and Open in Browser (system link open).
// Opening marks the article read (Android parity, BC-0011).
// Navigation: NavDestination on the shared NavPathStack (R2 respected).
import { FeedRepository, ArticleRow, FeedRow } from '../../data/FeedRepository';
import { AccountRepository, KEY_ARTICLE_FONT_SIZE, KEY_TITLE_ALIGNMENT } from '../../data/AccountRepository';
import hilog from '@ohos.hilog';
import { common } from '@kit.AbilityKit';

const TAG = 'P4Reader';

@Component
export struct ArticleReaderPage {
  @Consume('foundationPathStack') pathStack: NavPathStack | null = null;
  // FEAT-SETTINGS: immediate dark swap on the reader surface
  @StorageProp('uiDark') uiDark: boolean = false;
  @State article: ArticleRow | null = null;
  @State readState: number = 0;
  @State starredState: number = 0;
  @State feedTitle: string = '';
  // BC-0021 reader style (prefs article_font_size / title alignment)
  @State readerFontSize: number = 16;
  @State titleAlignStart: boolean = true;
  @State stylePanelOpen: boolean = false;
  private articleId: string = '';
  private repo: FeedRepository | null = null;

  aboutToAppear(): void {
    const ctx = getContext(this);
    const accountRepo = AccountRepository.obtain(ctx);
    const fontKey = accountRepo.getReaderStyle(KEY_ARTICLE_FONT_SIZE, 'MEDIUM');
    this.readerFontSize = fontKey === 'SMALL' ? 13 : (fontKey === 'LARGE' ? 19 : 16);
    this.titleAlignStart = accountRepo.getReaderStyle(KEY_TITLE_ALIGNMENT, 'START') === 'START';
  }

  private loadArticle(): void {
    const ctx = getContext(this);
    FeedRepository.obtain(ctx).then((repo: FeedRepository) => {
      this.repo = repo;
      return repo.getArticle(this.articleId);
    }).then((a: ArticleRow | null) => {
      this.article = a;
      if (a !== null) {
        this.readState = a.read;
        this.starredState = a.starred;
        // BC-0011: opening marks the article read
        if (a.read === 0 && this.repo !== null) {
          this.repo.markRead(a.id).then(() => {
            this.readState = 1;
          });
        }
        // feed source line (ArticleReader.kt parity: feed title header)
        if (this.repo !== null) {
          this.repo.listFeeds().then((fs: FeedRow[]) => {
            for (const f of fs) {
              if (f.id === a.feedId) {
                this.feedTitle = f.title;
                break;
              }
            }
          });
        }
      }
    });
  }

  private goBack(): void {
    if (this.pathStack !== null) {
      this.pathStack.pop();
    }
  }

  private toggleRead(): void {
    if (this.repo === null || this.article === null) {
      return;
    }
    const id = this.article.id;
    this.repo.toggleRead(id).then((v: number) => {
      this.readState = v;
      hilog.info(0x0000, TAG, 'read toggled to %{public}d', v);
    });
  }

  private toggleStar(): void {
    if (this.repo === null || this.article === null) {
      return;
    }
    const id = this.article.id;
    this.repo.toggleStar(id).then((v: number) => {
      this.starredState = v;
      hilog.info(0x0000, TAG, 'star toggled to %{public}d', v);
    });
  }

  private openInBrowser(): void {
    if (this.article === null || this.article.url.length === 0) {
      return;
    }
    try {
      const ctx = getContext(this) as common.UIAbilityContext;
      ctx.openLink(this.article.url);
    } catch (e) {
      hilog.warn(0x0000, TAG, 'openLink failed: %{public}s', JSON.stringify(e));
    }
  }

  private fmtDate(epoch: number): string {
    if (epoch <= 0) {
      return '';
    }
    const d = new Date(epoch * 1000);
    const m = d.getMonth() + 1;
    return d.getFullYear() + '-' + (m < 10 ? '0' + m : m) + '-' + d.getDate();
  }

  // --- BC-0021: article style picker (font size + title alignment) -------

  private applyFont(key: string, size: number): void {
    this.readerFontSize = size;
    this.stylePanelOpen = false;
    AccountRepository.obtain(getContext(this)).setReaderStyle(KEY_ARTICLE_FONT_SIZE, key);
  }

  private applyAlign(start: boolean): void {
    this.titleAlignStart = start;
    this.stylePanelOpen = false;
    AccountRepository.obtain(getContext(this))
      .setReaderStyle(KEY_TITLE_ALIGNMENT, start ? 'START' : 'CENTER');
  }

  build() {
    NavDestination() {
      Column() {
        // back bar (R6: NavPathStack.pop delegates the return gesture)
        Row({ space: 10 }) {
          Text('←')
            .fontSize(20)
            .padding(10)
            .fontColor(this.uiDark ? '#E3E2E6' : '#000000')
            .accessibilityText('Back')
            .onClick(() => this.goBack())
          Text('Reader')
            .fontSize(16)
            .fontWeight(FontWeight.Medium)
            .fontColor(this.uiDark ? '#E3E2E6' : '#000000')
            .layoutWeight(1)
            .maxLines(1)
            .textOverflow({ overflow: TextOverflow.Ellipsis })
          // BC-0021: article style entry (visible-text anchor 'Aa')
          Text('Aa')
            .fontSize(16)
            .fontWeight(FontWeight.Bold)
            .fontColor(this.uiDark ? '#C5C6D0' : '#44464F')
            .padding(10)
            .onClick(() => {
              this.stylePanelOpen = !this.stylePanelOpen;
            })
        }
        .width('100%')
        .alignItems(VerticalAlign.Center)
        .border({ width: { bottom: 1 }, color: this.uiDark ? '#22FFFFFF' : '#11000000' })
        if (this.stylePanelOpen) {
          // BC-0021 style picker: font size triple + title alignment pair
          Column({ space: 4 }) {
            Text('Article style')
              .fontSize(13)
              .fontWeight(FontWeight.Medium)
              .fontColor(this.uiDark ? '#C5C6D0' : '#666666')
              .width('100%')
            Row({ space: 16 }) {
              Text('Small')
                .fontSize(13)
                .fontColor(this.readerFontSize === 13 ? '#1B6EF3' : (this.uiDark ? '#E3E2E6' : '#1B1B1F'))
                .padding(6)
                .onClick(() => this.applyFont('SMALL', 13))
              Text('Medium')
                .fontSize(15)
                .fontColor(this.readerFontSize === 16 ? '#1B6EF3' : (this.uiDark ? '#E3E2E6' : '#1B1B1F'))
                .padding(6)
                .onClick(() => this.applyFont('MEDIUM', 16))
              Text('Large')
                .fontSize(17)
                .fontColor(this.readerFontSize === 19 ? '#1B6EF3' : (this.uiDark ? '#E3E2E6' : '#1B1B1F'))
                .padding(6)
                .onClick(() => this.applyFont('LARGE', 19))
            }
            .width('100%')
            .justifyContent(FlexAlign.Start)
            Row({ space: 16 }) {
              Text('Align left')
                .fontSize(13)
                .fontColor(this.titleAlignStart ? '#1B6EF3' : (this.uiDark ? '#C5C6D0' : '#666666'))
                .padding(6)
                .onClick(() => this.applyAlign(true))
              Text('Align center')
                .fontSize(13)
                .fontColor(!this.titleAlignStart ? '#1B6EF3' : (this.uiDark ? '#C5C6D0' : '#666666'))
                .padding(6)
                .onClick(() => this.applyAlign(false))
            }
            .width('100%')
            .justifyContent(FlexAlign.Start)
          }
          .width('100%')
          .padding({ left: 16, right: 16, top: 6, bottom: 6 })
          .alignItems(HorizontalAlign.Start)
        }
        Scroll() {
          Column({ space: 12 }) {
            Text(this.article !== null && this.article.title.length > 0
              ? this.article.title : '(untitled)')
              .fontSize(22)
              .fontWeight(FontWeight.Bold)
              .fontColor(this.uiDark ? '#E3E2E6' : '#000000')
              .width('100%')
              .textAlign(this.titleAlignStart ? TextAlign.Start : TextAlign.Center)
            if (this.feedTitle !== '') {
              Text(this.feedTitle)
                .fontSize(12)
                .fontColor('#7CACF8')
                .width('100%')
            }
            Text(this.fmtDate(this.article !== null ? this.article.publishedAt : 0))
              .fontSize(12)
              .fontColor(this.uiDark ? '#C5C6D0' : '#888888')
              .width('100%')
            Divider().color(this.uiDark ? '#22FFFFFF' : '#22000000')
            Text(this.article !== null && this.article.summary.length > 0
              ? this.article.summary : '(no content)')
              .fontSize(this.readerFontSize)
              .lineHeight(this.readerFontSize + 8)
              .fontColor(this.uiDark ? '#E3E2E6' : '#000000')
              .width('100%')
          }
          .padding(16)
          .alignItems(HorizontalAlign.Start)
        }
        .layoutWeight(1)
        .scrollBar(BarState.Off)
        Row({ space: 20 }) {
          // PD-1 (Android contract alignment): unread = solid dot, read =
          // hollow dot (was inverted before; matches the list rows too).
          Text((this.readState === 1 ? '○ ' : '● ') + 'Mark as read')
            .fontSize(14)
            .fontColor(this.uiDark ? '#E3E2E6' : '#000000')
            .padding(10)
            .onClick(() => this.toggleRead())
          Text((this.starredState === 1 ? '★ ' : '☆ ') + 'Star')
            .fontSize(14)
            .fontColor(this.uiDark ? '#E3E2E6' : '#000000')
            .padding(10)
            .onClick(() => this.toggleStar())
          Text('Open in Browser')
            .fontSize(14)
            .fontColor('#7CACF8')
            .padding(10)
            .onClick(() => this.openInBrowser())
        }
        .width('100%')
        .justifyContent(FlexAlign.Center)
        .padding({ top: 8, bottom: 12 })
        .border({ width: { top: 1 }, color: this.uiDark ? '#22FFFFFF' : '#11000000' })
      }
      .width('100%')
      .height('100%')
      .backgroundColor(this.uiDark ? '#1B1B1F' : '#FFFFFF')
    }
    .hideTitleBar(true)
    .id('PAGE-ARTICLEREADER-B2B865F0')
    .onReady((ctx: NavDestinationContext) => {
      const p = ctx.pathInfo.param as string;
      if (p !== undefined && p !== null && p.length > 0) {
        this.articleId = p;
        this.loadArticle();
      }
    })
  }
}
