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
}

export class RssFeed {
  title: string = '';
  link: string = '';
  items: RssItem[] = [];
}

export class RssParser {
  public static parse(source: string): RssFeed | null {
    const feed = new RssFeed();
    let inItem = false;
    let inEntry = false;
    let currentTag = '';
    let currentText = '';
    let item: RssItem | null = null;
    let atomLinkHref = '';
    const textEncoder = new util.TextEncoder();
    const buffer = textEncoder.encodeInto(source).buffer as ArrayBuffer;
    let ok = false;
    const cb = (eventType: xml.EventType, info: xml.ParseInfo): boolean => {
      const name = info.getName() ? info.getName() : '';
      if (eventType === xml.EventType.START_TAG) {
        currentTag = name;
        currentText = '';
        if (name === 'item') {
          inItem = true;
          item = new RssItem();
        } else if (name === 'entry') {
          inEntry = true;
          item = new RssItem();
        } else if (name === 'link') {
          atomLinkHref = '';
        }
      } else if (eventType === xml.EventType.TEXT || eventType === xml.EventType.CDSECT) {
        // DC-1 fix (impl-lead.capy-01 R5): @ohos.xml emits CDATA sections as
        // their own EventType (CDSECT = 5), NOT as TEXT. Ars Technica and
        // many RSS feeds wrap description HTML in <![CDATA[...]]>; without
        // this branch currentText stays empty -> summary empty -> reader
        // shows "(no content)". Accumulate CDATA text identically to TEXT.
        currentText += info.getText() ? info.getText() : '';
      } else if (eventType === xml.EventType.END_TAG) {
        const text = currentText.trim();
        const it = item;
        if (name === 'item' && it !== null) {
          feed.items.push(it);
          item = null;
          inItem = false;
        } else if (name === 'entry' && it !== null) {
          if (it.link === '' && atomLinkHref !== '') {
            it.link = atomLinkHref;
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
            } else if (name === 'description' || name === 'summary' || name === 'content') {
              if (it.summary === '') {
                it.summary = RssParser.stripHtml(text).substring(0, 500);
              }
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
    return feed;
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
    let out = '';
    let depth = 0;
    for (let i = 0; i < text.length; i++) {
      const ch = text.charAt(i);
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
    out = out.trim();
    out = out.replace(/&nbsp;/g, ' ')
      .replace(/&amp;/g, '&')
      .replace(/&lt;/g, '<')
      .replace(/&gt;/g, '>')
      .replace(/&quot;/g, '"')
      .replace(/&#39;|&apos;/g, '\'')
      .replace(/&#8217;/g, '\'')
      .replace(/&#8216;/g, '\'')
      .replace(/&#8220;|&#8221;/g, '"')
      .replace(/&[a-zA-Z#0-9]+;/g, ' ');
    return out.trim();
  }
}

