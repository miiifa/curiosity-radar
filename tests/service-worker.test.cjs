const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const root = path.join(__dirname,'..');
const url = 'http://localhost/data/news.json';
const good = () => ({mode:'live',generated_at:'2026-10-25T00:00:00Z',errors:[],items:[
  {id:'ai-fixture',category:'ai',title:'Fixture',source:'Fixture',url:'https://example.com',published:null,score:50}]});
function worker() {
  const stores=new Map(), events={};
  const failWrites={enabled:false};
  const key=r=>typeof r==='string'?r:r.url;
  const caches={
    async open(name){if(!stores.has(name))stores.set(name,new Map());const store=stores.get(name);return {
      async match(req){return store.get(key(req))?.clone();},
      async put(req,res){if(failWrites.enabled)throw Error('QuotaExceededError');store.set(key(req),res.clone());}, async addAll(){}
    };},
    async keys(){return [...stores.keys()];},async delete(name){return stores.delete(name);},
    async match(req){for(const name of stores.keys()){const r=await (await this.open(name)).match(req);if(r)return r;}}
  };
  const context=vm.createContext({URL,Request,Response,Headers,caches,
    fetch:async()=>Response.json(good()),
    self:{location:{href:'http://localhost/sw.js',origin:'http://localhost'},
      addEventListener:(name,fn)=>events[name]=fn,clients:{claim:async()=>{}},skipWaiting:async()=>{}}
  });
  context.importScripts=()=>vm.runInContext(fs.readFileSync(path.join(root,'feed-status.js'),'utf8'),context);
  vm.runInContext(fs.readFileSync(path.join(root,'sw.js'),'utf8'),context);
  return {context,caches,stores,failWrites,
    async fetch(target=url){let promise;events.fetch({request:new Request(target),respondWith:p=>promise=p});return promise;},
    async activate(){let promise;events.activate({waitUntil:p=>promise=p});await promise;}
  };
}
test('network 200 cached; offline fallback is explicitly marked with original timestamp',async()=>{
  const w=worker();assert.equal((await w.fetch()).headers.get('X-Curiosity-Radar-Cache'),null);
  w.context.fetch=async()=>{throw Error('offline');};
  const response=await w.fetch();assert.equal(response.headers.get('X-Curiosity-Radar-Cache'),'fallback');
  assert.deepEqual(await response.json(),good());
});
test('cache quota failure preserves successful static responses, with or without older cache',async()=>{
  const w=worker(), asset='http://localhost/app.js';
  w.context.fetch=async()=>new Response('previous',{status:200});
  assert.equal(await (await w.fetch(asset)).text(),'previous');
  w.failWrites.enabled=true;
  w.context.fetch=async()=>new Response('latest',{status:200});
  const response=await w.fetch(asset);
  assert.equal(response.status,200);
  assert.equal(await response.text(),'latest');
  const uncached=await w.fetch('http://localhost/styles.css');
  assert.equal(uncached.status,200);
  assert.equal(await uncached.text(),'latest');
  w.context.fetch=async()=>{throw Error('offline');};
  assert.equal(await (await w.fetch(asset)).text(),'previous');
  assert.equal((await w.fetch('http://localhost/styles.css')).status,503);
});
test('HTTP errors use marked cache, not an apparent successful refresh',async()=>{
  const w=worker();await w.fetch();
  for(const status of [404,429,503]){
    w.context.fetch=async()=>new Response('',{status});
    const r=await w.fetch();assert.equal(r.status,200);assert.equal(r.headers.get('X-Curiosity-Radar-Cache'),'fallback');
  }
});
test('malformed JSON, invalid feed, empty feed and demo mixing do not replace good cache',async()=>{
  const w=worker();await w.fetch();
  for(const content of ['{bad',JSON.stringify({...good(),mode:'invalid'}),JSON.stringify({...good(),items:[]}),
    JSON.stringify({...good(),items:[{...good().items[0],demo:true}]})]){
    w.context.fetch=async()=>new Response(content,{headers:{'Content-Type':'application/json'}});
    assert.equal(await (await w.fetch()).text(),content);
    w.context.fetch=async()=>{throw Error('offline');};
    assert.deepEqual(await (await w.fetch()).json(),good());
  }
});
test('offline without valid cache fails instead of inventing a feed',async()=>{
  const w=worker();w.context.fetch=async()=>{throw Error('offline');};
  assert.equal((await w.fetch()).status,503);
  await (await w.caches.open('radar-static-v4')).put(url,new Response('{bad'));
  assert.equal((await w.fetch()).status,503);
});
test('upgrade preserves prior valid snapshot and other applications caches',async()=>{
  const w=worker();await (await w.caches.open('radar-static-v1')).put(url,Response.json(good()));
  await w.caches.open('another-application');await w.activate();
  assert.ok(w.stores.has('another-application'));assert.ok(!w.stores.has('radar-static-v1'));
  w.context.fetch=async()=>{throw Error('offline');};
  assert.deepEqual(await (await w.fetch()).json(),good());
});

test('quota failure during v2 upgrade retains readable backup and prefers current assets',async()=>{
  const w=worker(), asset='http://localhost/app.js';
  const old=await w.caches.open('radar-static-v2');
  await old.put(url,Response.json(good()));
  await old.put(asset,new Response('old bundle'));
  w.context.fetch=async()=>new Response('current bundle');
  await w.fetch(asset);
  w.failWrites.enabled=true;
  await w.activate();
  assert.ok(w.stores.has('radar-static-v2'));
  w.context.fetch=async()=>{throw Error('offline');};
  const fallback=await w.fetch();
  assert.equal(fallback.headers.get('X-Curiosity-Radar-Cache'),'fallback');
  assert.deepEqual(await fallback.json(),good());
  assert.equal(await (await w.fetch(asset)).text(),'current bundle');
});
