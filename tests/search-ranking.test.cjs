const {test}=require('node:test');
const assert=require('node:assert/strict');
const {query,remapIds,normalizeWeights,validate}=require('../feed-status.js');
const item=(id,category='ai',score=50,extra={})=>({id,category,score,title:'Public fixture',summary:'',source:'Fixture',url:'https://example.com/'+id,published:'2026-10-25T00:00:00Z',tags:[],...extra});
const ids=items=>items.map(x=>x.id);
test('full width/case/whitespace normalize, search terms are AND and tags are literal data',()=>{
 const items=[item('a','ai',50,{title:'ＡＩ model',tags:['Python','<img src=x onerror=alert(1)>']}),item('b','ai',99,{title:'AI only'})];
 assert.deepEqual(ids(query(items,{search:' ai　PYTHON '})),['a']);
 assert.deepEqual(ids(query(items,{search:'<img'})),['a']);
 assert.deepEqual(ids(query(items,{search:'[.*'})),[]);
});
test('category including merged news, saved and unread intersections stay explicit',()=>{
 const items=[item('a','ai',50,{categories:['ai','security']}),item('b','security'),item('c','travel')];
 assert.deepEqual(ids(query(items,{category:'security',sort:'latest'})),['a','b']);
 assert.deepEqual(ids(query(items,{category:'security',unreadOnly:true,read:['a']})),['b']);
 assert.deepEqual(ids(query(items,{savedView:true,bookmarks:['a','c'],unreadOnly:true,read:['c']})),['a']);
});
test('aliases migrate bookmarks/read once, unknown IDs and empty/corrupt stores are safe',()=>{
 const items=[item('current','ai',50,{aliases:['old','earliest']})];
 assert.deepEqual(remapIds(['old','current','earliest','expired'],items),['current','expired']);
 assert.deepEqual(remapIds(null,items),[]);
 assert.deepEqual(remapIds('invalid',items),[]);
 assert.deepEqual(ids(query(items,{unreadOnly:true,read:remapIds(['old'],items)})),[]);
});
test('explicit latest/popular sorts keep zero values and missing dates last with deterministic ties',()=>{
 const items=[item('b','github',99,{stars:0,published:null}),item('a','ai',0),item('c','ai',10,{published:'2026-10-24T00:00:00Z'})];
 assert.deepEqual(ids(query(items,{sort:'latest'})),['a','c','b']);
 assert.deepEqual(ids(query(items,{sort:'popular'})),['c','b','a']);
 assert.deepEqual(ids(query([item('b'),item('a')],{sort:'latest'})),['a','b']);
});
test('weights reorder recommendations, dates dominate explicit latest order and invalid settings reset',()=>{
 const items=[item('ai','ai',70),item('travel','travel',80,{published:'2026-10-24T00:00:00Z'})];
 assert.equal(query(items,{weights:{ai:5,travel:1},search:'fixture'})[0].id,'ai');
 assert.equal(query(items,{weights:{ai:1,travel:5},search:'fixture'})[0].id,'travel');
 assert.deepEqual(ids(query(items,{sort:'latest',weights:{ai:1,travel:5}})),['ai','travel']);
 assert.equal(normalizeWeights({ai:'<script>',travel:99,security:0}).ai,5);
 assert.equal(normalizeWeights({ai:'<script>',travel:99,security:0}).travel,4);
});
test('all recommended has no three consecutive categories while alternatives exist',()=>{
 const items=[...Array.from({length:12},(_,n)=>item('ai'+n,'ai',99)),item('travel','travel',10),item('security','security',10)];
 const result=query(items);
 assert.ok(result.slice(0,3).some(x=>x.category!=='ai'));
 assert.ok(new Set(result.slice(0,6).map(x=>x.category)).size===3);
 assert.deepEqual(ids(query(items,{sort:'popular'})).slice(0,3),['ai0','ai1','ai10']);
 assert.ok(query(items,{category:'ai'}).every(x=>x.category==='ai'));
});
test('query does not mutate inputs and saved/search lists skip forced pool mixing',()=>{
 const items=[item('large','github',99,{stars:20000,discovery_group:'established'}),item('small','github',40,{stars:120,discovery_group:'small'})];
 assert.deepEqual(ids(query(items)),['small','large']);
 assert.deepEqual(ids(query(items,{search:'fixture'})),['large','small']);
 assert.deepEqual(ids(query(items,{savedView:true,bookmarks:['large','small']})),['large','small']);
 assert.deepEqual(ids(items),['large','small']);
});
test('extended provenance is validated before rendering untrusted links',()=>{
 const base={mode:'live',generated_at:'2026-10-25T00:00:00Z',errors:[],items:[item('a')]};
 assert.throws(()=>validate({...base,items:[item('a','ai',50,{aliases:['b']}),item('b')]}));
 validate({...base,items:[item('a','ai',50,{url:'HTTPS://EXAMPLE.COM/article'})]});
 for(const fields of [{aliases:'old'},{categories:['all']},{duplicates:[item('b','ai',50,{url:'javascript:alert(1)'})]},{related:[item('b','ai',50,{published:'invalid'})]}]){
  assert.throws(()=>validate({...base,items:[{...base.items[0],...fields}]}));
 }
});
