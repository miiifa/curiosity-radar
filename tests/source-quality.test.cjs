const {test}=require('node:test');
const assert=require('node:assert/strict');
const {validate,sourceInfo,articleDate,healthIssue}=require('../feed-status.js');
const item=()=>({id:'security-fixture',category:'security',source:'CISA KEV',source_kind:'official_catalog',
 source_url:'https://www.cisa.gov/catalog.json',title:'KEV fixture',url:'https://nvd.nist.gov/vuln/detail/CVE-2026-12345',
 published:'2026-10-25T00:00:00Z',score:95,security:{cves:['CVE-2026-12345'],user_impact:'not_assessed',exploitation_status:'listed_in_kev',kev_added_date:'2026-10-25'}});
const feed=i=>({mode:'live',generated_at:'2026-10-25T00:00:00Z',items:[i],errors:[]});
const health=()=>({id:'rss-fixture',name:'Public source',url:'https://example.com/feed',status:'failed',count:0,error:'HTTP404',checked_at:'2026-10-25T00:00:00Z',last_success_at:null,consecutive_failures:2,history_available:true});
test('KEV date stays the catalog date in any client timezone, including legacy snapshots',()=>{
 const value=item();validate(feed(value));
 assert.equal(articleDate(value).text,'2026/10/25');
 assert.equal(articleDate(value).datetime,'2026-10-25');
 assert.ok(articleDate(value).title.includes('攻撃日'));
 const legacy={...value};delete legacy.security;delete legacy.source_kind;delete legacy.source_url;
 assert.equal(articleDate(legacy).text,'2026/10/25');
});
test('catalog exploitation does not assert personal impact; RSS mentions alone prove neither',()=>{
 assert.ok(sourceInfo(item()).security.includes('利用製品・この端末への影響は未確認'));
 const rss={...item(),source:'JVN',source_kind:'official_feed',security:{cves:['CVE-2026-12345'],user_impact:'not_assessed',exploitation_status:'not_assessed'}};
 assert.ok(sourceInfo(rss).security.includes('悪用状況は未確認'));
 assert.ok(sourceInfo(rss).note.includes('自動要約'));
});
test('search results and travel query terms do not establish actual region/season/hours',()=>{
 const travel={...item(),category:'travel',source:'関東発ドライブ',source_kind:'search_feed'};delete travel.security;
 const info=sourceInfo(travel);
 assert.equal(info.kind,'検索結果のRSS');
 assert.ok(info.travel.includes('原典で確認'));
 assert.ok(info.note.includes('原典の発信元'));
 const legacy={...travel};delete legacy.source_kind;
 assert.equal(sourceInfo(legacy).kind,'取得元の属性は未確認');
});
test('invalid impact, CVEs and contradictory catalog dates are rejected',()=>{
 for(const update of [{user_impact:'affected'},{cves:['CVE-2026-12']},{kev_added_date:'2026-02-30'},{kev_added_date:'2026-10-24'}]){
  const value=item();Object.assign(value.security,update);assert.throws(()=>validate(feed(value)));
 }
 const value=item();value.source='Unverified RSS';assert.throws(()=>validate(feed(value)));
});
test('source health accepts bounded safe metadata and translates errors without raw exception text',()=>{
 validate({...feed(item()),source_health:[health()]});
 assert.equal(healthIssue('HTTP404'),'取得先が見つかりません');
 assert.equal(healthIssue('arbitrary private exception'),'取得エラー');
 assert.equal(healthIssue('constructor'),'取得エラー');
 assert.equal(healthIssue('__proto__'),'取得エラー');
 for(const update of [{url:'javascript:alert(1)'},{count:-1},{consecutive_failures:true},{checked_at:'invalid'},{error:'secret-value with spaces'}]){
  assert.throws(()=>validate({...feed(item()),source_health:[{...health(),...update}]}));
 }
});
