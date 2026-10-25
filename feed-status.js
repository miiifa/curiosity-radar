'use strict';
// Shared by the page, service worker and dependency-free Node tests (v1 feed).
((root) => {
  const categories = new Set(['github','ai','money','security','travel','social','hobby']);
  function timestamp(value) {
    if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$/.test(value)) return false;
    const [year, month, day] = value.slice(0,10).split('-').map(Number);
    return month >= 1 && month <= 12 && day >= 1 && day <= new Date(Date.UTC(year,month,0)).getUTCDate() && Number.isFinite(Date.parse(value));
  }
  const sourceKinds={search_feed:'検索結果のRSS',official_feed:'提供元の公式フィード',research_feed:'発信元の研究ブログ',official_catalog:'公式カタログ',public_api:'公開APIのメタデータ',github_api:'GitHub APIのメタデータ'};
  function validURL(value){const url=new URL(value);return typeof value==='string' && /^https?:\/\//i.test(value) && !/[\s\x00-\x1f\x7f]/.test(value) && ['http:','https:'].includes(url.protocol) && !!url.hostname && !url.username && !url.password;}
  function validateHealth(rows){
    if(!Array.isArray(rows))throw Error('Invalid source health');
    const ids=new Set();
    for(const row of rows){
      if(!row || !['id','name','url'].every(k=>typeof row[k]==='string'&&row[k]) || ids.has(row.id) || !validURL(row.url) ||
          !['ok','partial','failed'].includes(row.status) || !['count','consecutive_failures'].every(k=>Number.isInteger(row[k])&&row[k]>=0) ||
          typeof row.history_available!=='boolean' || !timestamp(row.checked_at) || (row.last_success_at!==null&&!timestamp(row.last_success_at)) ||
          (row.error!==null&&(typeof row.error!=='string'||! /^[A-Za-z0-9_]{1,40}$/.test(row.error))))throw Error('Invalid source health record');
      ids.add(row.id);
    }
  }
  function validateSource(item){
    if('source_url' in item&&!validURL(item.source_url))throw Error('Invalid source URL');
    if('source_kind' in item&&!Object.hasOwn(sourceKinds,item.source_kind))throw Error('Invalid source kind');
    if(!('security' in item))return;
    const info=item.security;
    if(!info||info.user_impact!=='not_assessed'||!['not_assessed','listed_in_kev'].includes(info.exploitation_status)||
        !Array.isArray(info.cves)||!info.cves.every(c=>typeof c==='string'&&/^CVE-\d{4}-\d{4,}$/.test(c))||
        !['vendor','product','required_action'].every(k=>info[k]==null||typeof info[k]==='string'))throw Error('Invalid security assessment');
    if(info.exploitation_status==='listed_in_kev'&&(item.source!=='CISA KEV'||item.source_kind!=='official_catalog'||info.cves.length!==1||
        typeof info.kev_added_date!=='string'||!/^\d{4}-\d{2}-\d{2}$/.test(info.kev_added_date)||!timestamp(info.kev_added_date+'T00:00:00Z')||
        !item.published?.startsWith(info.kev_added_date+'T')))throw Error('Invalid KEV provenance/date');
  }
  function healthIssue(code){
    const labels={EmptyFeed:'有効な記事がありません',MissingDates:'掲載日時を確認できません',EmptyCatalog:'カタログが空です',InvalidCVEData:'一部のCVEデータが不正です',IncompleteResults:'結果が一部のみです',HTTP404:'取得先が見つかりません',HTTP401:'アクセスできません',HTTP403:'アクセスが拒否されました',HTTP429:'取得回数が制限されています',TimeoutError:'応答待ちが時間切れです',ParseError:'フィードの形式を読み取れません',ValueError:'データ形式が不正です'};
    return Object.hasOwn(labels,code)?labels[code]:'取得エラー';
  }

  function sourceInfo(item){
    const security=itemCategories(item).includes('security');
    const travel=itemCategories(item).includes('travel');
    return {kind:Object.hasOwn(sourceKinds,item.source_kind)?sourceKinds[item.source_kind]:'取得元の属性は未確認',
      note:item.source_kind==='search_feed'?'検索結果からの候補です。原典の発信元と内容をリンク先で確認してください。':
        ['official_feed','research_feed'].includes(item.source_kind)?'RSSの抜粋です。自動要約・独立した事実確認ではありません。':'',
      security:security?(item.security?.exploitation_status==='listed_in_kev'?'CISA KEVに悪用事例が登録された脆弱性です。':'記事中の注意喚起です。悪用状況は未確認です。')+' 利用製品・この端末への影響は未確認です。原典と提供元の対応情報を確認してください。':'',
      travel:travel?'地域・見頃・料金・営業時間・営業状況は原典で確認してください。検索条件を現地の確認済み情報として扱わないでください。':''};
  }
  function articleDate(item){
    if(item.source==='CISA KEV'&&item.published){
      const date=item.security?.kev_added_date||item.published.slice(0,10);
      return {label:'KEV追加日',text:date.replaceAll('-','/'),datetime:date,title:'KEVカタログへの追加日です。攻撃日・脆弱性の公表日ではありません。'};
    }
    return {label:item.category==='github'?'更新':'掲載',text:item.published?new Date(item.published).toLocaleDateString('ja-JP'):'掲載日時不明',
      datetime:item.published,title:item.published?new Date(item.published).toLocaleString('ja-JP'):'掲載日時不明'};
  }
  function validate(data) {
    if (!data || !['demo','live'].includes(data.mode) || !timestamp(data.generated_at) ||
        !Array.isArray(data.items) || !data.items.length || !Array.isArray(data.errors) ||
        !data.errors.every(e => typeof e === 'string')) throw Error('Invalid feed');
    if('source_health' in data)validateHealth(data.source_health);
    const ids = new Set();
    for (const item of data.items) {
      if (!item || !['id','title','source'].every(k => typeof item[k] === 'string' && item[k].trim()) ||
          !categories.has(item.category) || ids.has(item.id) ||
          typeof item.score !== 'number' || !Number.isFinite(item.score) || item.score < 0 || item.score > 100 ||
          !('published' in item) || (item.published !== null && !timestamp(item.published)) ||
          ('tags' in item && (!Array.isArray(item.tags) || !item.tags.every(t => typeof t === 'string'))) ||
          ('demo' in item && typeof item.demo !== 'boolean') ||
          (data.mode === 'demo' ? item.demo !== true : item.demo === true)) throw Error('Invalid item');
      if (typeof item.url !== 'string' || /[\s\x00-\x1f\x7f]/.test(item.url) || !/^https?:\/\//i.test(item.url)) throw Error('Invalid URL');
      const url = new URL(item.url);
      if (!['https:','http:'].includes(url.protocol) || !url.hostname || url.username || url.password) throw Error('Invalid URL');
      validateSource(item);
      if ('aliases' in item && (!Array.isArray(item.aliases) || !item.aliases.every(id => typeof id === 'string' && id && id !== item.id))) throw Error('Invalid aliases');
      if ('categories' in item && (!Array.isArray(item.categories) || !item.categories.includes(item.category) || !item.categories.every(c => ['ai','security','travel','social','hobby'].includes(c)))) throw Error('Invalid categories');
      for (const key of ['duplicates','related']) if (key in item) {
        if (!Array.isArray(item[key])) throw Error('Invalid references');
        for (const ref of item[key]) {
          if (!ref || !['id','title','source','url','category'].every(k => typeof ref[k] === 'string' && ref[k].trim()) || !categories.has(ref.category) ||
              !('published' in ref) || (ref.published !== null && !timestamp(ref.published))) throw Error('Invalid reference');
          validateSource(ref);
          const target = new URL(ref.url);
          if (!/^https?:\/\//i.test(ref.url) || /[\s\x00-\x1f\x7f]/.test(ref.url) || !['http:','https:'].includes(target.protocol) || !target.hostname || target.username || target.password) throw Error('Invalid reference URL');
        }
      }
      if (item.category === 'github') {
        for (const key of ['stars','star_delta']) if (item[key] != null && (!Number.isInteger(item[key]) || (key === 'stars' && item[key] < 0))) throw Error('Invalid stars');
        for (const key of ['stars_observed_at','star_delta_since']) if (item[key] != null && !timestamp(item[key])) throw Error('Invalid observation timestamp');
        for (const key of ['star_delta_per_day','star_growth_percent_per_day']) if (item[key] != null && (typeof item[key] !== 'number' || !Number.isFinite(item[key]))) throw Error('Invalid rate');
        if (item.discovery_group != null && !['small','rising','established'].includes(item.discovery_group)) throw Error('Invalid discovery group');
      }
      ids.add(item.id);
    }
    const owners = new Map();
    for (const item of data.items) for (const alias of item.aliases || []) {
      if (ids.has(alias) || (owners.has(alias) && owners.get(alias) !== item.id)) throw Error('Conflicting alias');
      owners.set(alias,item.id);
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
  const repoGroups = {small:'小規模OSS候補', rising:'急上昇候補（観測値）', established:'定番候補（人気度）'};
  function repoMeta(item) {
    const observed = timestamp(item.stars_observed_at) ? Date.parse(item.stars_observed_at) : NaN;
    const since = timestamp(item.star_delta_since) ? Date.parse(item.star_delta_since) : NaN;
    const comparable = Number.isInteger(item.star_delta) && Number.isFinite(observed) && Number.isFinite(since) && observed > since;
    const date = iso => new Date(iso).toLocaleString('ja-JP');
    const elapsed = (observed-since)/3600000;
    const seconds = elapsed*3600;
    const duration = seconds < 60 ? `${Number(seconds.toFixed(1))}秒` : elapsed < 1 ? `${Number((seconds/60).toFixed(1))}分` : `${Number(elapsed.toFixed(1))}時間`;
    return {
      group: repoGroups[item.discovery_group] || '',
      observed: Number.isFinite(observed) ? `スター観測 ${date(item.stars_observed_at)}` : 'スター観測日時未確認',
      delta: comparable ? `スター差 ${item.star_delta > 0 ? '+' : ''}${item.star_delta} / 約${duration}の観測差（${date(item.star_delta_since)} → ${date(item.stars_observed_at)}）` : 'スター比較未確認',
      caution: item.discovery_group === 'rising' ? '観測期間から判定した候補。品質・安全性やスターの真正性は未検証。' : ''
    };
  }
  function mixRepos(items) {
    const groups = {small:[],rising:[],established:[],other:[]};
    for (const item of items) if (item.category === 'github') {
      const group = Object.hasOwn(repoGroups,item.discovery_group) ? item.discovery_group : 'other';
      groups[group].push(item);
    }
    const ordered = [];
    while (Object.values(groups).some(g => g.length)) for (const g of Object.values(groups)) if(g.length)ordered.push(g.shift());
    let index=0;
    return items.map(item => item.category === 'github' ? ordered[index++] : item);
  }
  const DEFAULT_WEIGHTS = Object.freeze({github:5,ai:5,money:5,security:4,travel:4,social:3,hobby:4});
  function normalizeWeights(values = {}) {
    return Object.fromEntries(Object.entries(DEFAULT_WEIGHTS).map(([key,fallback]) => {
      const value=Number(values?.[key]);
      return [key,Number.isInteger(value) && value >= 1 && value <= 5 ? value : fallback];
    }));
  }
  function itemCategories(item) { return item.categories || [item.category]; }
  function remapIds(ids, items) {
    const map=new Map(items.map(item => [item.id,item.id]));
    for (const item of items) for (const alias of item.aliases || []) if (!map.has(alias)) map.set(alias,item.id);
    return [...new Set((Array.isArray(ids)?ids:[]).filter(id => typeof id === 'string' && id).map(id => map.get(id) || id))];
  }
  function query(items, options = {}) {
    const {category='all',savedView=false,search='',sort='recommended',unreadOnly=false,bookmarks=[],read=[]}=options;
    const weights=normalizeWeights(options.weights);
    const saved=new Set(Array.isArray(bookmarks)?bookmarks:[]), seen=new Set(Array.isArray(read)?read:[]);
    const tokens=String(search).normalize('NFKC').toLocaleLowerCase('ja-JP').trim().split(/\s+/).filter(Boolean);
    const date=item => Number.isFinite(Date.parse(item.published)) ? Date.parse(item.published) : -Infinity;
    const score=item => item.score*(0.50+0.17*Math.max(...itemCategories(item).map(c=>weights[c] || 3)));
    const compareId=(a,b)=>a.id < b.id ? -1 : a.id > b.id ? 1 : 0;
    const recommended=(a,b)=>score(b)-score(a) || date(b)-date(a) || compareId(a,b);
    let result=items.filter(item => {
      if (savedView ? !saved.has(item.id) : category !== 'all' && !itemCategories(item).includes(category)) return false;
      if (unreadOnly && seen.has(item.id)) return false;
      const text=[item.title,item.summary,item.source,item.reason,...(item.tags || []),...(item.duplicates || []).map(ref=>ref.source+' '+ref.title)].join(' ').normalize('NFKC').toLocaleLowerCase('ja-JP');
      return tokens.every(token=>text.includes(token));
    });
    const popularity=item=>item.category === 'github' && typeof item.stars === 'number' ? item.stars : item.score;
    if (sort === 'latest') result.sort((a,b)=>date(b)-date(a) || recommended(a,b));
    else if (sort === 'popular') result.sort((a,b)=>popularity(b)-popularity(a) || recommended(a,b));
    else result.sort(recommended);
    if (sort !== 'recommended' || tokens.length || savedView) return result;
    result=mixRepos(result);
    if (category !== 'all') return result;
    const groups=new Map();
    for (const item of result) { if(!groups.has(item.category))groups.set(item.category,[]);groups.get(item.category).push(item); }
    const ordered=[];
    while (ordered.length < result.length) {
      const available=[...groups.values()].filter(group=>group.length);
      const last=ordered.at(-1)?.category;
      const repeated=ordered.length >= 2 && ordered.at(-2).category === last;
      const alternatives=available.filter(group=>group[0].category !== last);
      const eligible=repeated && alternatives.length ? alternatives : available;
      eligible.sort((a,b)=>recommended(a[0],b[0]));
      ordered.push(eligible[0].shift());
    }
    return ordered;
  }
  root.RadarFeed = {validate, describe, timestamp, repoMeta, mixRepos, DEFAULT_WEIGHTS, normalizeWeights, itemCategories, remapIds, query, validateHealth, sourceInfo, articleDate, healthIssue};
  if (typeof module !== 'undefined') module.exports = root.RadarFeed;
})(globalThis);
