const {test}=require('node:test');
const assert=require('node:assert/strict');
const {spotlightLabel}=require('../feed-status.js');
const now=Date.parse('2026-10-25T15:01:00Z');
const meta={mode:'live',generated_at:'2026-10-25T15:00:00Z',errors:[]};
test('today spotlight means successfully selected on the current Japanese calendar day',()=>{
  assert.equal(spotlightLabel(meta,{now}),'今日の注目');
  assert.equal(spotlightLabel({...meta,generated_at:'2026-10-25T14:59:00Z'},{now}),'前回取得時の注目');
});
test('partial, offline and cached snapshots cannot claim today selection',()=>{
  for(const options of [{cached:true},{online:false}])assert.equal(spotlightLabel(meta,{now,...options}),'前回取得時の注目');
  assert.equal(spotlightLabel({...meta,errors:['HTTP429']},{now}),'前回取得時の注目');
});
test('missing, future and invalid timestamps never create freshness claims',()=>{
  for(const generated_at of [undefined,'bad','2026-10-25T16:00:00Z'])assert.equal(spotlightLabel({...meta,generated_at},{now}),'前回取得時の注目');
});
test('demo spotlight is visibly a demo',()=>assert.equal(spotlightLabel({...meta,mode:'demo'},{now}),'デモの注目'));
