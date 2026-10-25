const {test}=require('node:test');const assert=require('node:assert/strict');
const {GENRES,inGenre,query}=require('../feed-status.js');
const items=['github','ai','travel','money','security','social','hobby'].map((category,i)=>({id:category,category,title:category,summary:'',tags:[],score:50+i}));
test('six display genres preserve all seven legacy categories without inventing deals',()=>{
 assert.equal(Object.keys(GENRES).length,6);
 for(const item of items)assert.equal(Object.keys(GENRES).filter(key=>inGenre(item,key)).length,1,item.category);
 assert.deepEqual(query(items,{category:'deals'}),[]);
});
test('technology and trends filters include both underlying categories, with legacy filters preserved',()=>{
 assert.deepEqual(new Set(query(items,{category:'technology'}).map(x=>x.id)),new Set(['github','ai']));
 assert.deepEqual(new Set(query(items,{category:'trends'}).map(x=>x.id)),new Set(['social','hobby']));
 assert.deepEqual(query(items,{category:'github'}).map(x=>x.id),['github']);
 assert.equal(query(items,{category:'__proto__'}).length,0);
});
test('multi-category membership, search, saved view and read filters keep their existing semantics',()=>{
 const rows=[{...items[0],categories:['github','security']},...items.slice(1)];
 assert.equal(query(rows,{category:'security'}).length,2);
 assert.deepEqual(query(rows,{category:'technology',search:'ai'}).map(x=>x.id),['ai']);
 assert.deepEqual(query(rows,{category:'technology',unreadOnly:true,read:['github']}).map(x=>x.id),['ai']);
 assert.deepEqual(query(rows,{category:'deals',savedView:true,bookmarks:['hobby']}).map(x=>x.id),['hobby']);
});
