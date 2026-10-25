'use strict';
// Shared by the page, service worker and dependency-free Node tests (v1 feed).
((root) => {
  const categories = new Set(['github','ai','money','security','travel','social','hobby']);
  function timestamp(value) {
    if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$/.test(value)) return false;
    const [year, month, day] = value.slice(0,10).split('-').map(Number);
    return month >= 1 && month <= 12 && day >= 1 && day <= new Date(Date.UTC(year,month,0)).getUTCDate() && Number.isFinite(Date.parse(value));
  }
  function validate(data) {
    if (!data || !['demo','live'].includes(data.mode) || !timestamp(data.generated_at) ||
        !Array.isArray(data.items) || !data.items.length || !Array.isArray(data.errors) ||
        !data.errors.every(e => typeof e === 'string')) throw Error('Invalid feed');
    const ids = new Set();
    for (const item of data.items) {
      if (!item || !['id','title','source'].every(k => typeof item[k] === 'string' && item[k].trim()) ||
          !categories.has(item.category) || ids.has(item.id) ||
          typeof item.score !== 'number' || !Number.isFinite(item.score) || item.score < 0 || item.score > 100 ||
          !('published' in item) || (item.published !== null && !timestamp(item.published)) ||
          ('tags' in item && (!Array.isArray(item.tags) || !item.tags.every(t => typeof t === 'string'))) ||
          ('demo' in item && typeof item.demo !== 'boolean') ||
          (data.mode === 'demo' ? item.demo !== true : item.demo === true)) throw Error('Invalid item');
      if (typeof item.url !== 'string' || /[\s\x00-\x1f\x7f]/.test(item.url) || !/^https?:\/\//.test(item.url)) throw Error('Invalid URL');
      const url = new URL(item.url);
      if (!['https:','http:'].includes(url.protocol) || !url.hostname || url.username || url.password) throw Error('Invalid URL');
      ids.add(item.id);
    }
    return data;
  }
  function describe(data, {cached = false, online = true, now = Date.now()} = {}) {
    const demo = data.mode === 'demo';
    const stale = !demo && now - Date.parse(data.generated_at) >= 48 * 3600000;
    const partial = data.errors.length > 0;
    const labels = [], messages = [];
    if (!online) { labels.push('オフライン'); messages.push('オフラインです。表示中の情報が最新かは確認できません。'); }
    if (cached) { labels.push('キャッシュ'); messages.push('保存済みデータを表示しています。今回の通信では最新データを取得できませんでした。'); }
    if (demo) { labels.push('プレビュー'); messages.push('これはデモデータです。サンプルを実際の最新ニュースとして扱わないでください。'); }
    if (stale) { labels.push('48時間以上未更新'); messages.push('最新の収集から48時間以上経過しています。古い情報の可能性があるため、原典を確認してください。'); }
    if (partial) { labels.push('一部取得失敗'); messages.push(`${data.errors.length}件の取得エラーがあります。前回から保持した記事を含む場合があります。ソース別の診断情報は公開JSONに記録されています。`); }
    if (!labels.length) labels.push('ライブデータ');
    return {label: labels.join(' · '), messages};
  }
  root.RadarFeed = {validate, describe, timestamp};
  if (typeof module !== 'undefined') module.exports = root.RadarFeed;
})(globalThis);
