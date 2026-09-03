// RssParser - rssparser/feedfinder parity (FEAT-ADD-FEED, impl-lead.capy-01).
// Minimal RSS 2.0 / Atom parser on the native @ohos.xml pull parser.
// Extracts feed title + items (title/link/published/summary) with
// structural parity to the Android rssparser module (semantic level:
// no binding to specific titles/dates).
import xml from '@ohos.xml';
import util from '@ohos.util';

export class RssItem {
  title: string = '';
  link: string = '';
  publishedAt: number = 0;
  summary: string = '';
  content: string = '';
  thumbnail: string = '';
}

export class RssFeed {
  title: string = '';
  link: string = '';
  items: RssItem[] = [];
}

export class RssParser {
  public static parse(source: string): RssFeed | null {
    // sspai and similar feeds escape inline HTML as &lt;a&gt; inside
    // <description>/<content>. The @ohos.xml parser decodes these to real
    // <a> tags, emitting START/END_TAG events that corrupt content
    // structure. Double-escape &lt;/&gt; to &amp;lt;/&amp;gt; so the XML
    // parser emits them as literal text "&lt;"/"&gt;" instead of tags.
    const safeSource = source.replace(/&lt;/g, '&amp;lt;').replace(/&gt;/g, '&amp;gt;');
    const feed = new RssFeed();
    let inItem = false;
    let inEntry = false;
    let currentTag = '';
    let currentText = '';
    // inContent: captures the full body HTML of content/content:encoded,
    // accumulated into contentBuffer so nested tags inside it never
    // clobber the accumulator (currentText is reset on every START_TAG).
    // Note: getName() strips the namespace prefix, so <media:content>
    // reports as 'content' too; keep-first-wins (below) ensures the real
    // body (content:encoded -> 'encoded', appears first in RSS items) is
    // never overwritten by the media block.
    let inContent = false;
    let contentBuffer = '';
    // descBuffer: accumulate description/summary text ACROSS nested tags.
    // Feeds like sspai escape <a> inside <description> as &lt;a&gt;, which
    // the XML parser emits as real START/END_TAG events; currentText is
    // reset on every START_TAG so text before <a> would be lost. Accumulate
    // in a sibling buffer that is only cleared at the element boundary.
    let inDesc = false;
    let descBuffer = '';
    let item: RssItem | null = null;
    let atomLinkHref = '';
    const textEncoder = new util.TextEncoder();
    const buffer = textEncoder.encodeInto(safeSource).buffer as ArrayBuffer;
    let ok = false;
    const cb = (eventType: xml.EventType, info: xml.ParseInfo): boolean => {
      const name = info.getName() ? info.getName() : '';
      if (eventType === xml.EventType.START_TAG) {
        currentTag = name;
        currentText = '';
        if (name === 'description' || name === 'summary') {
          inDesc = true;
          descBuffer = '';
        }
        if (name === 'content' || name === 'content:encoded' || name === 'encoded') {
          inContent = true;
          contentBuffer = '';
        }
        if (name === 'item') {
          inItem = true;
          item = new RssItem();
        } else if (name === 'entry') {
          inEntry = true;
          item = new RssItem();
        } else if (name === 'link') {
          atomLinkHref = '';
        } else if (name === 'enclosure' || name === 'media:thumbnail' || name === 'media:content') {
          // ParseInfo in callback mode has no getAttributes() method;
          // thumbnail URLs are extracted post-parse via regex from source.
        }
      } else if (eventType === xml.EventType.TEXT || eventType === xml.EventType.CDSECT) {
        currentText += info.getText() ? info.getText() : '';
        if (inContent) {
          contentBuffer += info.getText() ? info.getText() : '';
        }
        if (inDesc) {
          descBuffer += info.getText() ? info.getText() : '';
        }
      } else if (eventType === xml.EventType.ENTITY_REFERENCE || eventType === xml.EventType.WHITESPACE) {
        const evtText = info.getText() ? info.getText() : '';
        currentText += evtText;
        if (inContent) {
          contentBuffer += evtText;
        }
        if (inDesc) {
          descBuffer += evtText;
        }
      } else if (eventType === xml.EventType.END_TAG) {
        const text = currentText.trim();
        const it = item;
        if (name === 'item' && it !== null) {
          if (it.thumbnail === '' && it.content.length > 0) {
            it.thumbnail = RssParser.extractFirstImage(it.content);
          }
          if (it.thumbnail === '' && it.summary.length > 0) {
            it.thumbnail = RssParser.extractFirstImage(it.summary);
          }
          feed.items.push(it);
          item = null;
          inItem = false;
        } else if (name === 'entry' && it !== null) {
          if (it.link === '' && atomLinkHref !== '') {
            it.link = atomLinkHref;
          }
          if (it.thumbnail === '' && it.content.length > 0) {
            it.thumbnail = RssParser.extractFirstImage(it.content);
          }
          if (it.thumbnail === '' && it.summary.length > 0) {
            it.thumbnail = RssParser.extractFirstImage(it.summary);
          }
          feed.items.push(it);
          item = null;
          inEntry = false;
        } else if (inItem || inEntry) {
          if (it !== null) {
            if (name === 'title') {
              it.title = text;
            } else if (name === 'link') {
              it.link = it.link === '' ? (atomLinkHref !== '' ? atomLinkHref : text) : it.link;
            } else if (name === 'pubDate' || name === 'published' || name === 'updated') {
              it.publishedAt = RssParser.parseDate(text);
            } else if (name === 'description' || name === 'summary') {
              if (it.summary === '') {
                it.summary = RssParser.stripHtml(descBuffer).substring(0, 500);
              }
              inDesc = false;
              descBuffer = '';
            } else if (name === 'content' || name === 'content:encoded' || name === 'encoded') {
              // keep-first-wins: the real body (content:encoded -> 'encoded',
              // first in RSS items) must survive; <media:content> (also
              // 'content' after prefix strip) must not overwrite it.
              if (it.content === '') {
                const raw = contentBuffer.length > 0 ? contentBuffer : text;
                it.content = raw;
                if (it.summary === '') {
                  it.summary = RssParser.stripHtml(raw).substring(0, 500);
                }
              }
              inContent = false;
              contentBuffer = '';
            }
          }
        } else {
          if (name === 'title') {
            feed.title = text;
            ok = true;
          } else if (name === 'link') {
            feed.link = text;
          } else if (name === 'atom10:link' || name === 'atom:link') {
            // href attribute handled via link text fallback
          }
          if (name === 'description' || name === 'summary') {
            inDesc = false;
            descBuffer = '';
          }
        }
        currentTag = '';
        currentText = '';
      }
      return true;
    };
    try {
      const parser = new xml.XmlPullParser(buffer);
      const options: xml.ParseOptions = {
        tokenValueCallbackFunction: cb
      };
      parser.parse(options);
    } catch (e) {
      return null;
    }
    if (!ok && feed.items.length === 0) {
      return null;
    }
    if (feed.title === '') {
      feed.title = 'Untitled feed';
    }
    // Some HarmonyOS XML parser versions split escaped markup inside
    // <description> into synthetic nested tag events and only leave the
    // final anchor text in the callback buffer. Recover item bodies from
    // the original XML blocks so feeds such as sspai do not collapse to
    // only "查看全文". This is also Android parity: local RSS items use the
    // description as article content when content:encoded is absent.
    RssParser.hydrateBodiesFromSource(source, feed.items);
    RssParser.extractThumbnails(source, feed.items);
    return feed;
  }

  private static hydrateBodiesFromSource(source: string, items: RssItem[]): void {
    const itemRe = /<item\b[^>]*>([\s\S]*?)<\/item>/gi;
    let match = itemRe.exec(source);
    let index = 0;
    while (match !== null && index < items.length) {
      const block = match[1];
      const encoded = /<content:encoded\b[^>]*>([\s\S]*?)<\/content:encoded>/i.exec(block);
      const content = encoded !== null
        ? encoded
        : /<content\b[^>]*>([\s\S]*?)<\/content>/i.exec(block);
      const description = /<description\b[^>]*>([\s\S]*?)<\/description>/i.exec(block);
      const summary = description !== null
        ? description
        : /<summary\b[^>]*>([\s\S]*?)<\/summary>/i.exec(block);
      const item = items[index];
      if (content !== null) {
        item.content = RssParser.decodeEmbeddedMarkup(RssParser.unwrapCdata(content[1]));
      }
      if (summary !== null) {
        const rawDescription = RssParser.decodeEmbeddedMarkup(RssParser.unwrapCdata(summary[1]));
        const parsedSummary = RssParser.stripHtml(rawDescription).substring(0, 500);
        if (parsedSummary.length > item.summary.length) {
          item.summary = parsedSummary;
        }
        if (item.content === '') {
          item.content = rawDescription;
        }
      }
      index++;
      match = itemRe.exec(source);
    }
  }

  private static unwrapCdata(value: string): string {
    const text = value.trim();
    if (text.startsWith('<![CDATA[') && text.endsWith(']]>')) {
      return text.substring(9, text.length - 3);
    }
    return text;
  }

  private static decodeEmbeddedMarkup(value: string): string {
    return value.replace(/&amp;lt;/g, '&lt;')
      .replace(/&amp;gt;/g, '&gt;')
      .replace(/&lt;/g, '<')
      .replace(/&gt;/g, '>')
      .replace(/&#34;|&quot;/g, '"')
      .replace(/&#39;|&apos;/g, '\'')
      .replace(/&amp;/g, '&');
  }

  // Extract thumbnail URLs from enclosure/media:thumbnail/media:content
  // tags in the raw source, matching them to items by proximity (each
  // URL is assigned to the next item that doesn't yet have a thumbnail).
  // This replaces the callback-based attribute extraction which is not
  // supported by ParseInfo in tokenValueCallbackFunction mode.
  private static extractThumbnails(source: string, items: RssItem[]): void {
    if (items.length === 0) {
      return;
    }
    const re = /<(?:enclosure|media:thumbnail|media:content)[^>]*\surl=["']([^"']+)["']/gi;
    let m = re.exec(source);
    let itemIdx = 0;
    while (m !== null && itemIdx < items.length) {
      const url = m[1];
      if (url.startsWith('http')) {
        while (itemIdx < items.length && items[itemIdx].thumbnail !== '') {
          itemIdx++;
        }
        if (itemIdx < items.length) {
          items[itemIdx].thumbnail = url;
          itemIdx++;
        }
      }
      m = re.exec(source);
    }
  }

  // Atom <link href="..."/> attribute value comes through TEXT only when
  // the element has text; href attributes are captured by the caller from
  // the raw source with a tolerant fallback regex-free scan.
  public static extractAtomLinks(source: string): string[] {
    const links: string[] = [];
    let idx = 0;
    const marker = 'href="';
    while (true) {
      const pos = source.indexOf(marker, idx);
      if (pos < 0) {
        break;
      }
      const end = source.indexOf('"', pos + marker.length);
      if (end < 0) {
        break;
      }
      const value = source.substring(pos + marker.length, end);
      if (value.startsWith('http')) {
        links.push(value);
      }
      idx = end;
    }
    return links;
  }

  public static parseDate(text: string): number {
    if (text.length === 0) {
      return 0;
    }
    const parsed = Date.parse(text);
    if (!isNaN(parsed)) {
      return Math.floor(parsed / 1000);
    }
    // RFC822 weekday-prefixed forms: try trimming the leading weekday token
    const parts = text.split(' ');
    if (parts.length > 1) {
      const retry = Date.parse(parts.slice(1).join(' '));
      if (!isNaN(retry)) {
        return Math.floor(retry / 1000);
      }
    }
    return 0;
  }

  public static stripHtml(text: string): string {
    // DC-1 companion: char-scan (inherently multi-line safe, no regex /s
    // flag needed); inserts a space at block-tag boundaries so
    // "<p>a</p><p>b</p>" reads "a b" instead of "ab", then decodes the
    // common HTML entities.
    // Ordered FIX: XML parsers do NOT decode numeric/extra entities inside
    // element text (e.g. &#34; from sspai escaped markup stays literal and
    // &lt;a&gt; survives as text). Decode < > " first so tag stripping can
    // see them, else the trailing catch-all replaces every remaining
    // entity with a space and drops real summary words.
    // sspai fix: double-escaped &amp;lt;/&amp;gt; (from parse() pre-processing)
    // are decoded by the XML parser to &lt;/&gt; literal text. Decode them
    // here to < > so tag stripping can see them.
    let t = text;
    t = t.replace(/&amp;lt;/g, '<').replace(/&amp;gt;/g, '>');
    t = t.replace(/&#34;/g, '"')
      .replace(/&#39;|&apos;/g, '\'')
      .replace(/&#8217;/g, '\'')
      .replace(/&#8216;/g, '\'')
      .replace(/&#8220;|&#8221;/g, '"')
      .replace(/&quot;/g, '"')
      .replace(/&nbsp;/g, ' ')
      .replace(/&lt;/g, '<')
      .replace(/&gt;/g, '>')
      .replace(/&amp;/g, '&');
    let out = '';
    let depth = 0;
    for (let i = 0; i < t.length; i++) {
      const ch = t.charAt(i);
      if (ch === '<') {
        if (depth === 0 && out.length > 0 && out.charAt(out.length - 1) !== ' ') {
          out += ' ';
        }
        depth++;
      } else if (ch === '>') {
        if (depth > 0) {
          depth--;
        }
      } else if (depth === 0) {
        out += ch;
      }
    }
    out = out.replace(/\\n|\\r|\\t/g, ' ');
    out = out.replace(/\s+/g, ' ');
    out = out.trim();
    out = out.replace(/&[a-zA-Z#0-9]+;/g, ' ');
    return out.trim();
  }

  public static extractFirstImage(html: string): string {
    if (html.length === 0) {
      return '';
    }
    const imgIdx = html.indexOf('<img ');
    if (imgIdx < 0) {
      return '';
    }
    const srcIdx = html.indexOf('src="', imgIdx);
    if (srcIdx < 0) {
      return '';
    }
    const endQuote = html.indexOf('"', srcIdx + 5);
    if (endQuote < 0) {
      return '';
    }
    const url = html.substring(srcIdx + 5, endQuote);
    if (url.startsWith('http')) {
      return url;
    }
    return '';
  }
}
