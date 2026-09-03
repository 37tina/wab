// ArticleReaderPage - FEAT-ARTICLE-READ + FEAT-READ-UNREAD + FEAT-STAR
// (impl-lead.capy-01 batch 2; Rev2 #29 defect-1/2 rework, SLICE-1 #30).
// Body: RichText rendering of the raw article HTML (articles.content,
// fed by RSS content:encoded / Atom entry>content, RssParser parity with
// the Android rssparser module); plain-text summary is the fallback and
// the "(no content)" placeholder is gone.
// Bottom bar 5 items, SymbolGlyph icon + label columns (defect-2):
//   Mark as read / Star / Open in Browser / Share / Tags
// Star entry carries the passthrough surface PAGE-TOGGLESTARMENUITEM-5F309692.
// Tags: bottom CustomDialog shell; tags persisted via AccountRepository
// getReaderStyle/setReaderStyle key 'tags_<articleId>' (CSV).
// Share: startAbility Want action 'ohos.want.action.sendData'.
// Opening marks the article read (Android parity, BC-0011).
// Navigation: NavDestination on the shared NavPathStack (R2 respected).
import { FeedRepository, ArticleRow, FeedRow } from '../../data/FeedRepository';
import { AccountRepository, KEY_ARTICLE_FONT_SIZE, KEY_TITLE_ALIGNMENT } from '../../data/AccountRepository';
import hilog from '@ohos.hilog';
import { common, Want } from '@kit.AbilityKit';

const TAG = 'P4Reader';

class ReaderTextSegment {
  text: string = '';
  url: string = '';
  key: string = '';

  constructor(text: string, url: string, key: string) {
    this.text = text;
    this.url = url;
    this.key = key;
  }
}

class ReaderParagraph {
  segments: ReaderTextSegment[] = [];
  key: string = '';

  constructor(segments: ReaderTextSegment[], key: string) {
    this.segments = segments;
    this.key = key;
  }
}


// Rev2 #27/#30: Tags dialog shell (tags persisted as CSV in default prefs).
@CustomDialog
struct TagsDialog {
  controller?: CustomDialogController;
  articleId: string = '';
  @StorageProp('uiDark') uiDark: boolean = false;
  @State tagInput: string = '';
  @State tags: string[] = [];
  private repo: AccountRepository | null = null;

  aboutToAppear(): void {
    this.repo = AccountRepository.obtain(getContext(this));
    this.tags = this.loadTags();
  }

  private loadTags(): string[] {
    if (this.repo === null || this.articleId.length === 0) {
      return [];
    }
    const raw = this.repo.getReaderStyle('tags_' + this.articleId, '');
    return raw.length > 0 ? raw.split(',').filter((t: string) => t.length > 0) : [];
  }

  private persist(): void {
    if (this.repo !== null) {
      this.repo.setReaderStyle('tags_' + this.articleId, this.tags.join(','));
    }
  }

  build() {
    Column({ space: 12 }) {
      Text('标签')
        .fontSize(18)
        .fontWeight(FontWeight.Bold)
        .fontColor(this.uiDark ? '#ffffff' : '#1a1a1a')
      if (this.tags.length === 0) {
        Text('暂无标签')
          .fontSize(14)
          .fontColor('#6f7682')
      } else {
        Flex({ wrap: FlexWrap.Wrap }) {
          ForEach(this.tags, (t: string) => {
            Text(t + '  ✕')
              .fontSize(13)
              .fontColor('#2b7cf6')
              .backgroundColor(this.uiDark ? '#262b33' : '#eef5fe')
              .borderRadius(12)
              .padding({ left: 10, right: 10, top: 4, bottom: 4 })
              .onClick(() => {
                this.tags = this.tags.filter((x: string) => x !== t);
                this.persist();
              })
          }, (t: string) => t)
        }
        .width('100%')
      }
      TextInput({ placeholder: '添加标签', text: this.tagInput })
        .height(44)
        .backgroundColor(this.uiDark ? '#262b33' : '#f5f6f8')
        .borderRadius(8)
        .onChange((v: string) => {
          this.tagInput = v;
        })
        .enterKeyType(EnterKeyType.Done)
        .onSubmit(() => {
          const t = this.tagInput.trim();
          if (t.length > 0 && this.tags.indexOf(t) < 0) {
            this.tags = this.tags.concat([t]);
            this.persist();
          }
          this.tagInput = '';
        })
      Button('完成')
        .fontSize(14)
        .fontColor('#ffffff')
        .backgroundColor('#2b7cf6')
        .width('100%')
        .onClick(() => {
          this.controller?.close();
        })
    }
    .padding(20)
    .width('100%')
    .backgroundColor(this.uiDark ? '#1a1a1a' : '#ffffff')
    .borderRadius({ topLeft: 16, topRight: 16 })
    .alignItems(HorizontalAlign.Start)
  }
}

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
  // R3-SLICE-9 PD-ARTICLESTYLEPICKER: style picker now opens as a bottom
  // sheet (Android ArticleStylePicker.kt ModalBottomSheet parity).
  @State styleSheetOpen: boolean = false;
  // R3-SLICE-9 PD-IMAGEPAGE: images extracted from the raw content HTML
  // (entry for the full-screen image page; RichText body <img> taps are
  // not interceptable on this SDK - honest toolbar entry instead).
  @State articleImages: string[] = [];
  @State bodyParagraphs: ReaderParagraph[] = [];
  private articleId: string = '';
  private repo: FeedRepository | null = null;
  private tagsDialog: CustomDialogController | null = null;

  aboutToAppear(): void {
    const ctx = getContext(this);
    const accountRepo = AccountRepository.obtain(ctx);
    const fontKey = accountRepo.getReaderStyle(KEY_ARTICLE_FONT_SIZE, 'MEDIUM');
    // FIX detail overflow: MEDIUM 16→14 (DESIGN.md body 14), SMALL 13→12, LARGE 19→18;安卓标题 18-20sp 单/双行省略
    this.readerFontSize = fontKey === 'SMALL' ? 12 : (fontKey === 'LARGE' ? 18 : 14);
    this.titleAlignStart = accountRepo.getReaderStyle(KEY_TITLE_ALIGNMENT, 'START') === 'START';
    this.tagsDialog = new CustomDialogController({
      builder: TagsDialog({ articleId: this.articleId }),
      autoCancel: true,
      alignment: DialogAlignment.Bottom,
      customStyle: true
    });
  }

  // Build a complete HTML document for the Web component from the article
  // content. Priority: raw content HTML -> plain-text summary wrapped in
  // <p> (HTML-escaped so markup can never leak) -> visible empty-state.
  private rebuildParagraphs(): void {
    if (this.article !== null && this.article.content.length > 0) {
      this.bodyParagraphs = ArticleReaderPage.normalizeContentParagraphs(this.article.content);
      hilog.info(0x0000, TAG, 'rebuildParagraphs from content: %{public}d paragraphs',
        this.bodyParagraphs.length);
    } else if (this.article !== null && this.article.summary.length > 0) {
      this.bodyParagraphs = ArticleReaderPage.normalizeContentParagraphs(this.article.summary);
      hilog.info(0x0000, TAG, 'rebuildParagraphs from summary: 1 paragraph');
    } else {
      this.bodyParagraphs = [new ReaderParagraph([
        new ReaderTextSegment('暂无内容。', '', 'empty-segment')
      ], 'empty-paragraph')];
      hilog.info(0x0000, TAG, 'rebuildParagraphs: no content, no summary');
    }
  }

  // Preserve anchor targets while converting feed HTML into native ArkUI
  // paragraphs. The Android reader renders the same anchors in its WebView;
  // native Spans keep the Harmony reader lightweight and make every textual
  // RSS hyperlink independently tappable.
  private static normalizeContentParagraphs(html: string): ReaderParagraph[] {
    let s = html;
    s = s.replace(/<style[^>]*>[\s\S]*?<\/style>/gi, '');
    s = s.replace(/<script[^>]*>[\s\S]*?<\/script>/gi, '');
    s = s.replace(/<!--[\s\S]*?-->/g, '');
    s = s.replace(/\\n|\\r|\\t/g, ' ');
    s = s.replace(/<\/(p|div|h1|h2|h3|h4|h5|h6|li|blockquote|figure|figcaption|section|article|tr|ul|ol|table|header|footer)>/gi, '\u0002');
    s = s.replace(/<(br|hr)[^>]*>/gi, '\u0002');
    const chunks = s.split('\u0002');
    const paragraphs: ReaderParagraph[] = [];
    let paragraphIndex = 0;
    for (const raw of chunks) {
      const segments: ReaderTextSegment[] = [];
      const anchor = /<a\b[^>]*href\s*=\s*(?:"([^"]*)"|'([^']*)')[^>]*>([\s\S]*?)<\/a>/gi;
      let cursor = 0;
      let segmentIndex = 0;
      let match = anchor.exec(raw);
      while (match !== null) {
        ArticleReaderPage.appendSegment(segments, raw.substring(cursor, match.index), '',
          paragraphIndex + '-' + segmentIndex++);
        const href = ArticleReaderPage.decodeEntities(match[1] !== undefined ? match[1] : match[2]);
        ArticleReaderPage.appendSegment(segments, match[3], href,
          paragraphIndex + '-' + segmentIndex++);
        cursor = match.index + match[0].length;
        match = anchor.exec(raw);
      }
      ArticleReaderPage.appendSegment(segments, raw.substring(cursor), '',
        paragraphIndex + '-' + segmentIndex);
      if (segments.length > 0) {
        segments[0].text = segments[0].text.replace(/^\s+/, '');
        const last = segments.length - 1;
        segments[last].text = segments[last].text.replace(/\s+$/, '');
        if (segments[0].text.length === 0 && segments.length > 1) {
          segments.shift();
        }
        if (segments.length > 0 && segments[segments.length - 1].text.length === 0 && segments.length > 1) {
          segments.pop();
        }
      }
      if (segments.length > 0 && segments.some((segment: ReaderTextSegment) => segment.text.length > 0)) {
        paragraphs.push(new ReaderParagraph(segments, 'paragraph-' + paragraphIndex));
        paragraphIndex++;
      }
    }
    return paragraphs;
  }

  private static appendSegment(segments: ReaderTextSegment[], html: string, url: string, key: string): void {
    let text = html.replace(/<[^>]+>/g, '').replace(/\s+/g, ' ');
    text = ArticleReaderPage.decodeEntities(text);
    if (text.length > 0) {
      segments.push(new ReaderTextSegment(text, url, key));
    }
  }

  private static decodeEntities(t: string): string {
    return t.replace(/&amp;/g, '&')
      .replace(/&lt;/g, '<')
      .replace(/&gt;/g, '>')
      .replace(/&quot;/g, '"')
      .replace(/&#34;/g, '"')
      .replace(/&#39;|&apos;/g, '\'')
      .replace(/&nbsp;/g, ' ');
  }

  private static escapeHtml(t: string): string {
    return t.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  private loadArticle(): void {
    const ctx = getContext(this);
    FeedRepository.obtain(ctx).then((repo: FeedRepository) => {
      this.repo = repo;
      return repo.getArticle(this.articleId);
    }).then((a: ArticleRow | null) => {
      this.article = a;
      if (a !== null) {
        hilog.info(0x0000, TAG, 'loadArticle content.len=%{public}d summary.len=%{public}d',
          a.content.length, a.summary.length);
        if (a.content.length > 0) {
          hilog.info(0x0000, TAG, 'content preview: %{public}s',
            a.content.substring(0, 200));
        }
        this.readState = a.read;
        this.starredState = a.starred;
        this.articleImages = ArticleReaderPage.extractImages(a.content);
        this.rebuildParagraphs();
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

  private openArticleLink(url: string): void {
    if (url.length === 0) {
      return;
    }
    const resolved = this.resolveArticleLink(url);
    if (resolved.length === 0) {
      return;
    }
    try {
      hilog.info(0x0000, TAG, 'opening article hyperlink: %{public}s', resolved);
      const ctx = getContext(this) as common.UIAbilityContext;
      ctx.openLink(resolved).catch((e: Object) => {
        hilog.warn(0x0000, TAG, 'article hyperlink failed: %{public}s', JSON.stringify(e));
      });
    } catch (e) {
      hilog.warn(0x0000, TAG, 'article hyperlink failed: %{public}s', JSON.stringify(e));
    }
  }

  private resolveArticleLink(url: string): string {
    const trimmed = url.trim();
    if (/^[a-z][a-z0-9+.-]*:/i.test(trimmed)) {
      return trimmed;
    }
    if (trimmed.startsWith('//')) {
      return 'https:' + trimmed;
    }
    if (this.article === null || this.article.url.length === 0) {
      return trimmed;
    }
    const base = this.article.url;
    const originMatch = /^(https?:\/\/[^/]+)/i.exec(base);
    if (trimmed.startsWith('/') && originMatch !== null) {
      return originMatch[1] + trimmed;
    }
    const slash = base.lastIndexOf('/');
    return slash >= 8 ? base.substring(0, slash + 1) + trimmed : trimmed;
  }

  // Rev2 #29/#30 defect-2: system share (Android context.shareArticle
  // parity) via startAbility ACTION_SEND_DATA.
  private shareArticle(): void {
    if (this.article === null || this.article.url.length === 0) {
      return;
    }
    try {
      const ctx = getContext(this) as common.UIAbilityContext;
      const want: Want = {
        action: 'ohos.want.action.sendData',
        uri: this.article.url,
        type: 'text/plain'
      } as Want;
      ctx.startAbility(want).catch((e: Object) => {
        hilog.warn(0x0000, TAG, 'share startAbility failed: %{public}s', JSON.stringify(e));
      });
    } catch (e) {
      hilog.warn(0x0000, TAG, 'share failed: %{public}s', JSON.stringify(e));
    }
  }

  // Rev2 #27/#30: Tags entry -> bottom dialog (add/remove, prefs-backed).
  // Rebuilt lazily so the dialog always sees the current articleId.
  private openTags(): void {
    this.tagsDialog = new CustomDialogController({
      builder: TagsDialog({ articleId: this.articleId }),
      autoCancel: true,
      alignment: DialogAlignment.Bottom,
      customStyle: true
    });
    this.tagsDialog.open();
  }

  private fmtDate(epoch: number): string {
    if (epoch <= 0) {
      return '';
    }
    const d = new Date(epoch * 1000);
    const m = d.getMonth() + 1;
    const day = d.getDate();
    return d.getFullYear() + '-' + (m < 10 ? '0' + m : m) + '-' + (day < 10 ? '0' + day : day);
  }

  // --- BC-0021: article style picker (font size + title alignment) -------

  // R3-SLICE-9: applied live while the style sheet stays open (source
  // ArticleStylePicker applies immediately without dismissing the sheet).
  private applyFont(key: string, size: number): void {
    this.readerFontSize = size;
    AccountRepository.obtain(getContext(this)).setReaderStyle(KEY_ARTICLE_FONT_SIZE, key);
    this.rebuildParagraphs();

  }

  private applyAlign(start: boolean): void {
    this.titleAlignStart = start;
    AccountRepository.obtain(getContext(this))
      .setReaderStyle(KEY_TITLE_ALIGNMENT, start ? 'START' : 'CENTER');
  }

  // R3-SLICE-9 PD-IMAGEPAGE: all <img src> URLs from the raw content HTML.
  private static extractImages(html: string): string[] {
    if (html.length === 0) {
      return [];
    }
    const re = /<img[^>]+src=["']([^"']+)["']/gi;
    const out: string[] = [];
    let m = re.exec(html);
    while (m !== null) {
      out.push(m[1]);
      m = re.exec(html);
    }
    return out;
  }

  private openImages(): void {
    if (this.articleImages.length === 0) {
      return;
    }
    if (this.pathStack !== null) {
      this.pathStack.pushPathByName('PAGE-IMAGEPAGE-18D3E5AD',
        JSON.stringify({ images: this.articleImages, index: 0 }));
    }
  }

  // R3-SLICE-9 PD-ARTICLESTYLEPICKER/ARTICLEFONTMENU: bottom-sheet style
  // picker (Android ArticleStylePicker.kt parity): font size triple +
  // title alignment pair with trailing ✓ marker + highlight; selections
  // apply immediately (BC-0021 prefs keys unchanged).
  @Builder
  styleSheetBuilder() {
    Column({ space: 6 }) {
      Text('文章样式')
        .fontSize(18)
        .fontWeight(FontWeight.Bold)
        .fontColor(this.uiDark ? '#ffffff' : '#1a1a1a')
        .width('100%')
      Text('字号')
        .fontSize(13)
        .fontColor(this.uiDark ? '#eceef2' : '#6f7682')
        .width('100%')
      this.styleOptionRow('小', this.readerFontSize === 12, () => this.applyFont('SMALL', 12))
      this.styleOptionRow('中', this.readerFontSize === 14, () => this.applyFont('MEDIUM', 14))
      this.styleOptionRow('大', this.readerFontSize === 18, () => this.applyFont('LARGE', 18))
      Text('标题对齐')
        .fontSize(13)
        .fontColor(this.uiDark ? '#eceef2' : '#6f7682')
        .width('100%')
        .margin({ top: 8 })
      this.styleOptionRow('左对齐', this.titleAlignStart, () => this.applyAlign(true))
      this.styleOptionRow('居中', !this.titleAlignStart, () => this.applyAlign(false))
      Button('完成')
        .fontSize(14)
        .height(40)
        .fontColor('#ffffff')
        .backgroundColor('#2b7cf6')
        .borderRadius(20)
        .width('100%')
        .margin({ top: 12 })
        .onClick(() => {
          this.styleSheetOpen = false;
        })
    }
    .padding(20)
    .width('100%')
    .backgroundColor(this.uiDark ? '#1a1a1a' : '#ffffff')
    .borderRadius({ topLeft: 16, topRight: 16 })
    .alignItems(HorizontalAlign.Start)
  }

  @Builder
  styleOptionRow(label: string, selected: boolean, onTap: () => void) {
    Row() {
      Text(label)
        .fontSize(16)
        .fontColor(selected ? '#2b7cf6' : (this.uiDark ? '#ffffff' : '#1a1a1a'))
        .layoutWeight(1)
      if (selected) {
        Text('✓')
          .fontSize(16)
          .fontWeight(FontWeight.Bold)
          .fontColor('#2b7cf6')
      }
    }
    .width('100%')
    .padding({ top: 12, bottom: 12, left: 16, right: 16 })
    .borderRadius(8)
    .backgroundColor(selected
      ? (this.uiDark ? '#262b7cf6' : '#0A2b7cf6')
      : Color.Transparent)
    .onClick(() => onTap())
  }

  build() {
    NavDestination() {
      Column() {
        // back bar (R6: NavPathStack.pop delegates the return gesture)
        Row({ space: 10 }) {
          Text('←')
            .fontSize(20)
            .padding(10)
            .fontColor(this.uiDark ? '#ffffff' : '#1a1a1a')
            .accessibilityText('返回')
            .onClick(() => this.goBack())
          Text('阅读')
            .fontSize(16)
            .fontWeight(FontWeight.Medium)
            .fontColor(this.uiDark ? '#ffffff' : '#1a1a1a')
            .layoutWeight(1)
            .maxLines(1)
            .textOverflow({ overflow: TextOverflow.Ellipsis })
          // R3-SLICE-9 PD-IMAGEPAGE: full-screen image entry (visible
          // only when the content HTML actually carries images).
          if (this.articleImages.length > 0) {
            Text('图片')
              .fontSize(14)
              .fontColor(this.uiDark ? '#6f7682' : '#262b33')
              .padding(10)
              .accessibilityText('查看图片')
              .onClick(() => this.openImages())
          }
          // BC-0021: article style entry (visible-text anchor 'Aa') now
          // opens the bottom-sheet style picker (R3-SLICE-9).
          Text('Aa')
            .fontSize(16)
            .fontWeight(FontWeight.Bold)
            .fontColor(this.uiDark ? '#6f7682' : '#262b33')
            .padding(10)
            .onClick(() => {
              this.styleSheetOpen = true;
            })
        }
        .width('100%')
        .alignItems(VerticalAlign.Center)
        .border({ width: { bottom: 1 }, color: this.uiDark ? '#22FFFFFF' : '#11000000' })

        // header block: title + feed source + date (secondary small text) — FIX 22→20 (DESIGN.md H1 20/600) + 2-line ellipsis to match Android single/double line, prevents 1320x2856 overflow
        Column({ space: 12 }) {
          Text(this.article !== null && this.article.title.length > 0
            ? this.article.title : '（无标题）')
            .fontSize(20)
            .fontWeight(FontWeight.Bold)
            .fontColor(this.uiDark ? '#ffffff' : '#1a1a1a')
            .width('100%')
            .maxLines(2)
            .textOverflow({ overflow: TextOverflow.Ellipsis })
            .textAlign(this.titleAlignStart ? TextAlign.Start : TextAlign.Center)
          Row({ space: 8 }) {
            if (this.feedTitle !== '') {
              Text(this.feedTitle)
                .fontSize(12)
                .fontColor('#2b7cf6')
                .maxLines(1)
            }
            Text(this.fmtDate(this.article !== null ? this.article.publishedAt : 0))
              .fontSize(12)
              .fontColor(this.uiDark ? '#eceef2' : '#6f7682')
              .maxLines(1)
          }
          .width('100%')
        }
        .padding({ left: 16, right: 16, top: 12 })
        .alignItems(HorizontalAlign.Start)
        .width('100%')
        // List anchors short article bodies at the top of the remaining reader
        // area. Scroll centers a child whose intrinsic height is smaller than
        // its viewport on this ArkUI runtime, leaving a large blank gap after
        // the metadata (unlike the Android reader).
        List({ space: 12 }) {
          ForEach(this.bodyParagraphs, (p: ReaderParagraph) => {
            ListItem() {
              Text() {
                ForEach(p.segments, (segment: ReaderTextSegment) => {
                  Span(segment.text)
                    .fontColor(segment.url.length > 0
                      ? '#2b7cf6'
                      : (this.uiDark ? '#e8e8e8' : '#1a1a1a'))
                    .decoration({
                      type: segment.url.length > 0 ? TextDecorationType.Underline : TextDecorationType.None,
                      color: '#2b7cf6'
                    })
                    .onClick(() => this.openArticleLink(segment.url))
                }, (segment: ReaderTextSegment) => segment.key)
              }
                .fontSize(this.readerFontSize)
                .fontColor(this.uiDark ? '#e8e8e8' : '#1a1a1a')
                .lineHeight(this.readerFontSize * 1.7)
                .width('100%')
                .textAlign(TextAlign.Start)
                .copyOption(CopyOptions.LocalDevice)
            }
          }, (p: ReaderParagraph) => p.key)
        }
        .width('100%')
        .layoutWeight(1)
        .padding({ left: 16, right: 16, top: 12, bottom: 16 })
        .scrollBar(BarState.Off)
        .backgroundColor(this.uiDark ? '#1a1a1a' : '#ffffff')
        // Rev2 defect-2: bottom bar 5 items (SymbolGlyph + label columns). FIX icons 22→20, labels 10→11 (DESIGN.md micro 11-12)
        Row({ space: 4 }) {
          Column({ space: 2 }) {
            // icon-fallback: ✓
            SymbolGlyph(this.readState === 1
              ? $r('sys.symbol.checkmark_circle') : $r('sys.symbol.checkmark_circle_fill'))
              .fontSize(20)
              .fontColor(this.uiDark ? ['#ffffff'] : ['#1a1a1a'])
            Text('标记已读')
              .fontSize(11)
              .fontColor(this.uiDark ? '#ffffff' : '#1a1a1a')
              .maxLines(1)
          }
          .padding({ left: 6, right: 6, top: 6, bottom: 4 })
          .onClick(() => this.toggleRead())
          // Rev2 #27: ToggleStarMenuItem passthrough surface carried by
          // this bottom-bar star entry (PAGE-TOGGLESTARMENUITEM-5F309692).
          Column({ space: 2 }) {
            // icon-fallback: ☆ / ★
            SymbolGlyph(this.starredState === 1
              ? $r('sys.symbol.star_fill') : $r('sys.symbol.star'))
              .fontSize(20)
              .fontColor(this.starredState === 1 ? ['#2b7cf6'] : (this.uiDark ? ['#ffffff'] : ['#1a1a1a']))
            Text('收藏')
              .fontSize(11)
              .fontColor(this.uiDark ? '#ffffff' : '#1a1a1a')
              .maxLines(1)
          }
          .padding({ left: 6, right: 6, top: 6, bottom: 4 })
          .id('PAGE-TOGGLESTARMENUITEM-5F309692')
          .onClick(() => this.toggleStar())
          Column({ space: 2 }) {
            // icon-fallback: ↗
            SymbolGlyph($r('sys.symbol.arrow_up_right'))
              .fontSize(20)
              .fontColor(this.uiDark ? ['#ffffff'] : ['#1a1a1a'])
            Text('在浏览器打开')
              .fontSize(11)
              .fontColor(this.uiDark ? '#ffffff' : '#1a1a1a')
              .maxLines(1)
          }
          .padding({ left: 6, right: 6, top: 6, bottom: 4 })
          .onClick(() => this.openInBrowser())
          Column({ space: 2 }) {
            // icon-fallback: ⤴
            SymbolGlyph($r('sys.symbol.share'))
              .fontSize(20)
              .fontColor(this.uiDark ? ['#ffffff'] : ['#1a1a1a'])
            Text('分享')
              .fontSize(11)
              .fontColor(this.uiDark ? '#ffffff' : '#1a1a1a')
              .maxLines(1)
          }
          .padding({ left: 6, right: 6, top: 6, bottom: 4 })
          .onClick(() => this.shareArticle())
          Column({ space: 2 }) {
            // icon-fallback: #
            SymbolGlyph($r('sys.symbol.hash'))
              .fontSize(20)
              .fontColor(this.uiDark ? ['#ffffff'] : ['#1a1a1a'])
            Text('标签')
              .fontSize(11)
              .fontColor(this.uiDark ? '#ffffff' : '#1a1a1a')
              .maxLines(1)
          }
          .padding({ left: 6, right: 6, top: 6, bottom: 4 })
          .onClick(() => this.openTags())
        }
        .width('100%')
        .justifyContent(FlexAlign.SpaceEvenly)
        .padding({ top: 8, bottom: 12 })
        .border({ width: { top: 1 }, color: this.uiDark ? '#22FFFFFF' : '#11000000' })
      }
      .width('100%')
      .height('100%')
      .backgroundColor(this.uiDark ? '#1a1a1a' : '#ffffff')
      .bindSheet($$this.styleSheetOpen, this.styleSheetBuilder(), {
        height: 420, dragBar: true, showClose: false
      })
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
