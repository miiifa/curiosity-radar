const {test} = require('node:test');
const assert = require('node:assert/strict');
const {repoMeta,mixRepos,validate} = require('../feed-status.js');
const observed='2026-10-25T12:00:00Z';
const since='2026-10-23T12:00:00Z';
const repo=(id,group,score=50)=>({id,category:'github',discovery_group:group,score});

test('measured difference exposes exact interval, timestamps and heuristic caution',()=>{
  const view=repoMeta({...repo('r','rising'),star_delta:40,stars_observed_at:observed,star_delta_since:since});
  assert.ok(view.group.includes('急上昇候補'));
  assert.ok(view.delta.includes('+40'));
  assert.ok(view.delta.includes('48時間'));
  assert.ok(view.delta.includes('2026/10/23'));
  assert.ok(view.delta.includes('2026/10/25'));
  assert.ok(view.caution.includes('未検証'));
  assert.ok(!view.delta.includes('24時間増加'));
});
test('legacy, invalid, missing and future comparison timestamps never display an unproven difference',()=>{
  for(const data of [{star_delta:99}, {star_delta:99,stars_observed_at:observed},
    {star_delta:99,stars_observed_at:observed,star_delta_since:'invalid'},
    {star_delta:99,stars_observed_at:since,star_delta_since:observed}]){
    const view=repoMeta(data);assert.equal(view.delta,'スター比較未確認');assert.ok(!view.delta.includes('99'));
  }
  assert.equal(repoMeta({}).observed,'スター観測日時未確認');
});
test('zero, negative and short-interval actual differences are not hidden or relabeled as a day',()=>{
  for(const delta of [0,-5]){
    const view=repoMeta({star_delta:delta,stars_observed_at:observed,star_delta_since:since});
    assert.ok(view.delta.includes(`スター差 ${delta} / 約48時間`));
  }
  const view=repoMeta({star_delta:2,star_delta_since:'2026-10-25T11:54:00Z',stars_observed_at:observed});
  assert.ok(view.delta.includes('6分'));
  assert.ok(repoMeta({star_delta:1,star_delta_since:'2026-10-25T11:59:50Z',stars_observed_at:observed}).delta.includes('約10秒'));
});
test('recommendation mixing preserves non-GitHub positions and each pool internal ranking',()=>{
  const news={id:'news',category:'ai'};
  const items=[repo('big1','established',99),news,repo('big2','established',98),
    repo('rising','rising',80),repo('small','small',60),repo('legacy',undefined,90)];
  const mixed=mixRepos(items);
  assert.equal(mixed[1],news);
  assert.deepEqual(mixed.filter(x=>x.category==='github').map(x=>x.id),['small','rising','big1','legacy','big2']);
  assert.equal(new Set(mixed.map(x=>x.id)).size,items.length);
  assert.deepEqual(items.map(x=>x.id),['big1','news','big2','rising','small','legacy']);
});
test('optional observation metadata rejects bad types while old snapshots remain compatible',()=>{
  const base={mode:'live',generated_at:observed,errors:[],items:[{
    id:'g',category:'github',source:'Fixture',title:'Fixture',url:'https://github.com/fixture/tool',score:50,published:null}]};
  validate(base);
  for(const fields of [{stars:-1},{star_delta:true},{stars_observed_at:'invalid'},
    {star_delta_per_day:NaN},{star_growth_percent_per_day:'fast'},{discovery_group:'verified'}]){
    assert.throws(()=>validate({...base,items:[{...base.items[0],...fields}]}));
  }
});
