const {test} = require('node:test');
const assert = require('node:assert/strict');
const {validate, describe} = require('../feed-status.js');
const now = Date.parse('2026-10-25T12:00:00Z');
const fixture = () => ({mode:'live', generated_at:new Date(now).toISOString(), errors:[],
  items:[{id:'ai-fixture',title:'Fixture',category:'ai',source:'Public fixture',url:'https://example.com/article',score:50,published:null}]});

test('v1 live and missing article date are valid; current snapshot validates', () => {
  validate(fixture());
  validate(require('../data/news.json'));
  assert.equal(describe(fixture(), {now}).label, 'ライブデータ');
  assert.deepEqual(describe(fixture(), {now}).messages, []);
});
test('48 hours boundary, partial failure and cached offline remain visible together', () => {
  const data=fixture(); data.generated_at=new Date(now-48*3600000).toISOString(); data.errors=['RSS Fixture: TimeoutError'];
  const status=describe(data,{now,cached:true,online:false});
  for (const label of ['48時間以上未更新','一部取得失敗','キャッシュ','オフライン']) assert.ok(status.label.includes(label));
  assert.equal(status.messages.length,4);
  assert.equal(data.generated_at,'2026-10-23T12:00:00.000Z');
  assert.ok(!describe(data,{now:now-1}).label.includes('48時間'));
});
test('demo stays a preview when cached or old', () => {
  const data=fixture();data.mode='demo';data.items[0].demo=true;
  data.generated_at='2020-01-01T00:00:00Z';validate(data);
  const status=describe(data,{now,cached:true,online:false});
  assert.ok(status.label.includes('プレビュー'));
  assert.ok(!status.label.includes('ライブ'));
  assert.ok(!status.label.includes('48時間'));
});
test('bad modes, timestamps, empty feeds and mixed demo/live fail validation', () => {
  for (const update of [{mode:'stale'}, {generated_at:null}, {generated_at:'2026-02-30T00:00:00Z'},
    {generated_at:'2026-10-25T12:00:00'}, {items:[]}, {errors:'private detail'}]) {
    assert.throws(()=>validate({...fixture(),...update}));
  }
  const data=fixture();data.items[0].demo=true;assert.throws(()=>validate(data));
  data.mode='demo';data.items[0].demo=false;assert.throws(()=>validate(data));
});
test('bad article fields, URLs and dates are not silently shown as live news', () => {
  for (const update of [{category:'all'}, {source:''}, {score:NaN}, {url:'javascript:alert(1)'},
    {url:'https://user:secret@example.com'}, {url:'https://'}, {url:'https://example.com/\n'},
    {published:'invalid'}, {tags:'not an array'}]) {
    const data=fixture();Object.assign(data.items[0],update);assert.throws(()=>validate(data));
  }
  const data=fixture();data.items.push({...data.items[0]});assert.throws(()=>validate(data));
});
