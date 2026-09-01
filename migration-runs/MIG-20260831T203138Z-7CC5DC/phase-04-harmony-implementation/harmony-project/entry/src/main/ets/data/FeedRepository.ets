// FeedRepository - FEAT-ADD-FEED + FEAT-FEED-REFRESH data layer
// (impl-lead.capy-01). Implements Phase 3 data-contract interfaces:
//   feeds (room_table parity -> RelationalStore#feeds)
//   articles (-> RelationalStore#articles, read/starred columns)
//   article_statuses (read/starred view over articles)
//   last_refreshed_at (account prefs epoch seconds)
// feedfinder parity: malformed/unfetchable URL -> FEED_NOT_FOUND /
// CONNECTION_ERROR (BC-0005, no DB write); rssparser parity via
// RssParser (@ohos.xml) + @ohos.net.http.
// Probe providers are synchronous callbacks: they read a semantic cache
// refreshed after every DB mutation + at startup (never fabricated).
import relationalStore from '@ohos.data.relationalStore';
import http from '@ohos.net.http';
import hilog from '@ohos.hilog';
import preferences from '@ohos.data.preferences';
import fs from '@ohos.file.fs';
import util from '@ohos.util';
import { RssParser, RssFeed } from './RssParser';
import { AccountRepository } from './AccountRepository';
import { registerProbe } from '../probe/SemanticProbeRegistry';

const TAG = 'CapyFeedRepo';
const PREF_DEFAULT = 'capy_default_prefs';

export enum AddFeedResultCode {
  SUCCESS = 0,
  FEED_NOT_FOUND = 1,
  CONNECTION_ERROR = 2,
  SAVE_FAILURE = 3
}

export class FeedRow {
  id: string = '';
  url: string = '';
  title: string = '';
}

export class ArticleRow {
  id: string = '';
  feedId: string = '';
  title: string = '';
  url: string = '';
  summary: string = '';
  publishedAt: number = 0;
  read: number = 0;
  starred: number = 0;
  lastReadAt: number = 0;
}

const CREATE_FEEDS = 'CREATE TABLE IF NOT EXISTS feeds (' +
  'id TEXT PRIMARY KEY, url TEXT NOT NULL UNIQUE, title TEXT NOT NULL)';
const CREATE_ARTICLES = 'CREATE TABLE IF NOT EXISTS articles (' +
  'id TEXT PRIMARY KEY, feed_id TEXT NOT NULL, title TEXT NOT NULL, ' +
  'url TEXT, summary TEXT, published_at INTEGER, ' +
  'read INTEGER DEFAULT 0, starred INTEGER DEFAULT 0, last_read_at INTEGER DEFAULT 0)';

function decodeBody(buf: ArrayBuffer): string {
  const arr = new Uint8Array(buf);
  const decoder = util.TextDecoder.create('utf-8');
  return decoder.decodeToString(arr);
}

export class FeedRepository {
  private static rdb: relationalStore.RdbStore | null = null;
  private static cache: Record<string, Object> = {};
  private ctx: Context;

  private constructor(ctx: Context) {
    this.ctx = ctx;
  }

  public static async obtain(ctx: Context): Promise<FeedRepository> {
    if (FeedRepository.rdb === null) {
      const store = await relationalStore.getRdbStore(ctx, {
        name: 'capy_articles.db',
        securityLevel: relationalStore.SecurityLevel.S1
      } as relationalStore.StoreConfig);
      await store.executeSql(CREATE_FEEDS);
      await store.executeSql(CREATE_ARTICLES);
      FeedRepository.rdb = store;
    }
    return new FeedRepository(ctx);
  }

  public getCached(key: string): Object | null {
    const v = FeedRepository.cache[key];
    return v === undefined ? null : v;
  }

  public static getCache(): Record<string, Object> {
    return FeedRepository.cache;
  }

  private accountId(): string {
    return AccountRepository.obtain(this.ctx).getAccountId();
  }

  private accountPrefs(): preferences.Preferences {
    return preferences.getPreferencesSync(this.ctx,
      { name: 'account_' + this.accountId() } as preferences.Options);
  }

  // --- feedfinder parity (BC-0005) --------------------------------------

  private fetchUrl(url: string): Promise<string> {
    return new Promise<string>((resolve, reject) => {
      const req = http.createHttp();
      req.request(url, {
        connectTimeout: 15000,
        readTimeout: 20000,
        usingCache: false
      } as http.HttpRequestOptions).then((resp: http.HttpResponse) => {
        req.destroy();
        if (resp.responseCode < 200 || resp.responseCode >= 300) {
          reject(new Error('http status ' + resp.responseCode));
          return;
        }
        const body = resp.result;
        if (typeof body === 'string') {
          resolve(body);
        } else {
          resolve(decodeBody(body as ArrayBuffer));
        }
      }).catch((err: Error) => {
        req.destroy();
        reject(err);
      });
    });
  }

  // --- domain op add (BC-0004) ------------------------------------------

  public async addFeed(url: string): Promise<AddFeedResultCode> {
    if (!url.startsWith('http://') && !url.startsWith('https://')) {
      return AddFeedResultCode.FEED_NOT_FOUND;
    }
    let body = '';
    try {
      body = await this.fetchUrl(url);
    } catch (e) {
      hilog.warn(0x0000, TAG, 'fetch failed: %{public}s', JSON.stringify(e));
      return AddFeedResultCode.CONNECTION_ERROR;
    }
    const feed = RssParser.parse(body);
    if (feed === null || feed.items.length === 0) {
      return AddFeedResultCode.FEED_NOT_FOUND;
    }
    const code = await this.upsertFeedAndArticles(url, feed);
    await this.refreshCacheAndExport();
    return code;
  }

  private async upsertFeedAndArticles(url: string, feed: RssFeed): Promise<AddFeedResultCode> {
    const store = FeedRepository.rdb!;
    try {
      let feedId = '';
      const existed = await store.querySql(
        'SELECT id FROM feeds WHERE url = ?', [url]);
      if (existed.goToNextRow()) {
        feedId = existed.getString(existed.getColumnIndex('id'));
      }
      existed.close();
      if (feedId === '') {
        feedId = url;
        await store.executeSql(
          'INSERT INTO feeds (id, url, title) VALUES (?, ?, ?)',
          [feedId, url, feed.title]);
      } else {
        await store.executeSql('UPDATE feeds SET title = ? WHERE id = ?',
          [feed.title, feedId]);
      }
      for (let i = 0; i < feed.items.length; i++) {
        const item = feed.items[i];
        const articleId = feedId + '#' + (item.link !== '' ? item.link : 'idx' + i);
        const dup = await store.querySql(
          'SELECT id FROM articles WHERE id = ?', [articleId]);
        const has = dup.goToNextRow();
        dup.close();
        if (!has) {
          await store.executeSql(
            'INSERT INTO articles (id, feed_id, title, url, summary, published_at, read, starred) ' +
            'VALUES (?, ?, ?, ?, ?, ?, 0, 0)',
            [articleId, feedId, item.title, item.link, item.summary, item.publishedAt]);
        }
      }
      return AddFeedResultCode.SUCCESS;
    } catch (e) {
      hilog.error(0x0000, TAG, 'save failed: %{public}s', JSON.stringify(e));
      return AddFeedResultCode.SAVE_FAILURE;
    }
  }

  // --- domain op remove (BC-0007) ---------------------------------------

  public async removeFeed(feedId: string): Promise<void> {
    const store = FeedRepository.rdb!;
    await store.executeSql('DELETE FROM articles WHERE feed_id = ?', [feedId]);
    await store.executeSql('DELETE FROM feeds WHERE id = ?', [feedId]);
    await this.refreshCacheAndExport();
  }

  // --- domain op list -----------------------------------------------------

  public async listFeeds(): Promise<FeedRow[]> {
    const store = FeedRepository.rdb!;
    const rs = await store.querySql(
      'SELECT id, url, title FROM feeds ORDER BY title', []);
    const out: FeedRow[] = [];
    while (rs.goToNextRow()) {
      const row = new FeedRow();
      row.id = rs.getString(rs.getColumnIndex('id'));
      row.url = rs.getString(rs.getColumnIndex('url'));
      row.title = rs.getString(rs.getColumnIndex('title'));
      out.push(row);
    }
    rs.close();
    return out;
  }

  public async listArticles(feedId: string | null, status: string = 'all'): Promise<ArticleRow[]> {
    const store = FeedRepository.rdb!;
    let sql = 'SELECT id, feed_id, title, url, summary, published_at, read, starred, last_read_at FROM articles';
    const args: string[] = [];
    const conds: string[] = [];
    if (feedId !== null) {
      conds.push('feed_id = ?');
      args.push(feedId);
    }
    if (status === 'unread') {
      conds.push('read = 0');
    } else if (status === 'starred') {
      conds.push('starred = 1');
    }
    if (conds.length > 0) {
      sql += ' WHERE ' + conds.join(' AND ');
    }
    // BC-0020: sort direction is a persisted setting (prefs
    // article_list_sort_order; NEWEST_FIRST=DESC default, OLDEST_FIRST=ASC).
    const sortOrder = this.getSortOrderPref();
    sql += sortOrder === 'OLDEST_FIRST' ? ' ORDER BY published_at ASC' : ' ORDER BY published_at DESC';
    const rs = await store.querySql(sql, args);
    const out: ArticleRow[] = [];
    while (rs.goToNextRow()) {
      const row = new ArticleRow();
      row.id = rs.getString(rs.getColumnIndex('id'));
      row.feedId = rs.getString(rs.getColumnIndex('feed_id'));
      row.title = rs.getString(rs.getColumnIndex('title'));
      row.url = rs.getString(rs.getColumnIndex('url'));
      row.summary = rs.getString(rs.getColumnIndex('summary'));
      row.publishedAt = rs.getLong(rs.getColumnIndex('published_at'));
      row.read = rs.getLong(rs.getColumnIndex('read'));
      row.starred = rs.getLong(rs.getColumnIndex('starred'));
      row.lastReadAt = rs.getLong(rs.getColumnIndex('last_read_at'));
      out.push(row);
    }
    rs.close();
    return out;
  }

  // --- read/star status ops (BC-0011/0014/0015/0016) -----------------------

  public async getArticle(articleId: string): Promise<ArticleRow | null> {
    const store = FeedRepository.rdb!;
    const rs = await store.querySql(
      'SELECT id, feed_id, title, url, summary, published_at, read, starred, last_read_at FROM articles WHERE id = ?',
      [articleId]);
    let row: ArticleRow | null = null;
    if (rs.goToNextRow()) {
      row = new ArticleRow();
      row.id = rs.getString(rs.getColumnIndex('id'));
      row.feedId = rs.getString(rs.getColumnIndex('feed_id'));
      row.title = rs.getString(rs.getColumnIndex('title'));
      row.url = rs.getString(rs.getColumnIndex('url'));
      row.summary = rs.getString(rs.getColumnIndex('summary'));
      row.publishedAt = rs.getLong(rs.getColumnIndex('published_at'));
      row.read = rs.getLong(rs.getColumnIndex('read'));
      row.starred = rs.getLong(rs.getColumnIndex('starred'));
      row.lastReadAt = rs.getLong(rs.getColumnIndex('last_read_at'));
    }
    rs.close();
    return row;
  }

  public async markRead(articleId: string): Promise<void> {
    const store = FeedRepository.rdb!;
    await store.executeSql(
      'UPDATE articles SET read = 1, last_read_at = ? WHERE id = ?',
      [Math.floor(Date.now() / 1000), articleId]);
    await this.refreshCacheAndExport();
  }

  public async toggleRead(articleId: string): Promise<number> {
    const store = FeedRepository.rdb!;
    await store.executeSql(
      'UPDATE articles SET read = 1 - read, last_read_at = ? WHERE id = ?',
      [Math.floor(Date.now() / 1000), articleId]);
    await this.refreshCacheAndExport();
    const a = await this.getArticle(articleId);
    return a !== null ? a.read : 0;
  }

  public async toggleStar(articleId: string): Promise<number> {
    const store = FeedRepository.rdb!;
    await store.executeSql(
      'UPDATE articles SET starred = 1 - starred WHERE id = ?', [articleId]);
    await this.refreshCacheAndExport();
    const a = await this.getArticle(articleId);
    return a !== null ? a.starred : 0;
  }

  public async markAllRead(feedId: string | null, status: string): Promise<number> {
    const store = FeedRepository.rdb!;
    const epoch = Math.floor(Date.now() / 1000);
    if (feedId !== null) {
      await store.executeSql(
        'UPDATE articles SET read = 1, last_read_at = ? WHERE feed_id = ?',
        [epoch, feedId]);
    } else {
      await store.executeSql(
        'UPDATE articles SET read = 1, last_read_at = ?', [epoch]);
    }
    await this.refreshCacheAndExport();
    const arts = await this.listArticles(feedId, status);
    return arts.length;
  }

  // --- article filter persistence (BC-0009/0010) ----------------------------

  public getArticleFilter(): string {
    const p = preferences.getPreferencesSync(this.ctx,
      { name: PREF_DEFAULT } as preferences.Options);
    return p.getSync('article_filter', 'status=ALL') as string;
  }

  // BC-0020: persisted list sort order ('NEWEST_FIRST' | 'OLDEST_FIRST')
  public getSortOrderPref(): string {
    const p = preferences.getPreferencesSync(this.ctx,
      { name: PREF_DEFAULT } as preferences.Options);
    return p.getSync('article_list_sort_order', 'NEWEST_FIRST') as string;
  }

  public setArticleFilter(value: string): void {
    const p = preferences.getPreferencesSync(this.ctx,
      { name: PREF_DEFAULT } as preferences.Options);
    p.putSync('article_filter', value);
    p.flushSync();
    this.refreshCacheAndExport();
  }

  // --- domain op refresh (BC-0008) ---------------------------------------

  public async refreshAll(): Promise<number> {
    const feeds = await this.listFeeds();
    let updated = 0;
    for (const feed of feeds) {
      try {
        const body = await this.fetchUrl(feed.url);
        const parsed = RssParser.parse(body);
        if (parsed !== null && parsed.items.length > 0) {
          await this.upsertFeedAndArticles(feed.url, parsed);
          updated += 1;
        }
      } catch (e) {
        hilog.warn(0x0000, TAG, 'refresh feed failed: %{public}s', feed.url);
      }
    }
    const p = this.accountPrefs();
    p.putSync('last_refreshed_at', Math.floor(Date.now() / 1000));
    p.flushSync();
    await this.refreshCacheAndExport();
    return updated;
  }

  public getLastRefreshedAt(): number {
    const p = this.accountPrefs();
    return p.getSync('last_refreshed_at', 0) as number;
  }

  // --- semantic cache + exports -------------------------------------------

  public async refreshCache(): Promise<void> {
    const feeds = await this.listFeeds();
    const articles = await this.listArticles(null);
    const feedList: Record<string, Object>[] = [];
    for (const f of feeds) {
      const m: Record<string, Object> = {};
      m['id'] = f.id;
      m['url'] = f.url;
      m['title'] = f.title;
      feedList.push(m);
    }
    const artList: Record<string, Object>[] = [];
    let readCount = 0;
    let starredCount = 0;
    for (const a of articles) {
      const m: Record<string, Object> = {};
      m['id'] = a.id;
      m['feed_id'] = a.feedId;
      m['title'] = a.title;
      m['read'] = a.read;
      m['starred'] = a.starred;
      artList.push(m);
      readCount += a.read;
      starredCount += a.starred;
    }
    const statusItems: Record<string, Object>[] = [];
    for (const a of articles) {
      const m2: Record<string, Object> = {};
      m2['id'] = a.id;
      m2['read'] = a.read;
      m2['starred'] = a.starred;
      statusItems.push(m2);
    }
    const statuses: Record<string, Object> = {};
    statuses['read_count'] = readCount;
    statuses['starred_count'] = starredCount;
    statuses['count'] = artList.length;
    statuses['items'] = JSON.stringify(statusItems);
    const cache: Record<string, Object> = {};
    cache['feeds'] = JSON.stringify(feedList);
    cache['articles'] = JSON.stringify(artList);
    cache['article_statuses'] = JSON.stringify(statuses);
    cache['last_refreshed_at'] = this.getLastRefreshedAt();
    cache['feed_count'] = feeds.length;
    cache['article_count'] = articles.length;
    FeedRepository.cache = cache;
  }

  public async refreshCacheAndExport(): Promise<void> {
    await this.refreshCache();
    AccountRepository.obtain(this.ctx).exportReplayData();
    try {
      const json = JSON.stringify(FeedRepository.cache);
      const target = this.ctx.filesDir + '/feed-snapshot.json';
      const exists = fs.accessSync(target);
      const file = fs.openSync(target,
        fs.OpenMode.READ_WRITE | fs.OpenMode.CREATE | (exists ? fs.OpenMode.TRUNC : 0));
      fs.writeSync(file.fd, json);
      fs.closeSync(file);
    } catch (e) {
      hilog.warn(0x0000, TAG, 'snapshot export failed: %{public}s', JSON.stringify(e));
    }
  }
}

// --- probe providers (synchronous cache reads over the live store) --------
let feedProvidersRegistered = false;

export async function registerFeedProbeProviders(ctx: Context): Promise<void> {
  if (feedProvidersRegistered) {
    return;
  }
  feedProvidersRegistered = true;
  const repo = await FeedRepository.obtain(ctx);
  await repo.refreshCache();
  registerProbe('feeds', (): object | null => {
    return repo.getCached('feeds');
  });
  registerProbe('articles', (): object | null => {
    return repo.getCached('articles');
  });
  registerProbe('article_statuses', (): object | null => {
    return repo.getCached('article_statuses');
  });
  registerProbe('last_refreshed_at', (): object | null => {
    return repo.getCached('last_refreshed_at');
  });
  registerProbe('article_filter', (): object | null => {
    // BC-0009 data anchor: prefs article_filter, e.g. "status=UNREAD"
    return repo.getArticleFilter() as Object;
  });
  hilog.info(0x0000, TAG, 'feed probe providers registered');
}
