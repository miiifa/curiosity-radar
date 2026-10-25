const {test}=require('node:test');
const assert=require('node:assert/strict');
const {DEFAULT_WEIGHTS,MAX_PREFERENCES_BYTES,validatePreferences,decodePreferences,portablePreferences,mergePreferences,writePreferences}=require('../feed-status.js');
const profile=(extra={})=>({format:'curiosity-radar-preferences',version:1,weights:{...DEFAULT_WEIGHTS},bookmarks:['public-id'],...extra});
const memory=()=>{const values=new Map([['radar:weights','original-weights'],['radar:saved','original-saved'],['radar:read','read-marker']]);return {values,getItem:key=>values.get(key)??null,setItem:(key,value)=>values.set(key,value),removeItem:key=>values.delete(key)};};

test('export/import round trip carries only normalized weights and unique saved IDs',()=>{
  const value=portablePreferences({weights:{ai:1,github:2},bookmarks:['id','id','unknown-id'],read:['PRIVATE_READ'],token:'PRIVATE_TOKEN',items:[{title:'PRIVATE_TITLE'}]});
  const text=JSON.stringify(value),decoded=decodePreferences(text);
  assert.deepEqual(Object.keys(value),['format','version','weights','bookmarks']);
  assert.deepEqual(decoded.bookmarks,['id','unknown-id']);assert.equal(decoded.weights.ai,1);assert.equal(decoded.weights.travel,4);
  assert.ok(!text.includes('PRIVATE_'));
  decoded.weights.ai=5;assert.equal(value.weights.ai,1);
});
test('wrong formats, versions, extra fields, prototypes and invalid roots are rejected',()=>{
  for(const value of [null,[],{},profile({format:'other-app'}),profile({version:2}),profile({read:['secret']}),profile({token:'secret'}),{...profile(),__extra:true}])assert.throws(()=>validatePreferences(value));
  assert.throws(()=>decodePreferences(JSON.stringify(profile()).replace('"version":1','"__proto__":{},"version":1')));
  assert.throws(()=>decodePreferences('{broken'));
});
test('weights require all known categories and integers from one to five',()=>{
  for(const value of [null,[],{}, {...DEFAULT_WEIGHTS,ai:'5'}, {...DEFAULT_WEIGHTS,ai:0}, {...DEFAULT_WEIGHTS,ai:6}, {...DEFAULT_WEIGHTS,ai:1.5}, {...DEFAULT_WEIGHTS,ai:true}, {...DEFAULT_WEIGHTS,unknown:3}])assert.throws(()=>validatePreferences(profile({weights:value})));
  const poisoned=JSON.parse(JSON.stringify(DEFAULT_WEIGHTS));Object.defineProperty(poisoned,'__proto__',{value:3,enumerable:true});
  assert.throws(()=>validatePreferences(profile({weights:poisoned})));
});
test('saved IDs are bounded strings; duplicates dedupe and HTML remains inert data',()=>{
  for(const value of [null,{},[1],[''],['line\nbreak'],[' a'],['a'.repeat(201)],Array(5001).fill('id')])assert.throws(()=>validatePreferences(profile({bookmarks:value})));
  const hostile='<img/src=x/onerror=alert(1)>';
  assert.deepEqual(validatePreferences(profile({bookmarks:[hostile,hostile]})).bookmarks,[hostile]);
  assert.equal(validatePreferences(profile({bookmarks:Array.from({length:5000},(_,i)=>'id-'+i)})).bookmarks.length,5000);
});
test('file size caps bytes as well as character count',()=>{
  assert.throws(()=>decodePreferences(' '.repeat(MAX_PREFERENCES_BYTES+1)));
  const text=JSON.stringify(profile());
  assert.deepEqual(decodePreferences(text+' '.repeat(MAX_PREFERENCES_BYTES-text.length)),profile());
  const unicode=JSON.stringify(profile({bookmarks:Array.from({length:3000},(_,i)=>'あ'.repeat(190)+i)}));
  assert.ok(unicode.length<MAX_PREFERENCES_BYTES);assert.throws(()=>decodePreferences(unicode));
});
test('import merges existing saves, remaps aliases, keeps unknown IDs and leaves read untouched',()=>{
  const state={weights:{...DEFAULT_WEIGHTS},bookmarks:['existing','old-id'],read:['seen']};
  const incoming=profile({weights:{...DEFAULT_WEIGHTS,ai:1},bookmarks:['old-id','new-id','expired-id']});
  const merged=mergePreferences(state,incoming,[{id:'canonical',aliases:['old-id']}]);
  assert.deepEqual(merged.bookmarks,['existing','canonical','new-id','expired-id']);assert.equal(merged.weights.ai,1);
  assert.deepEqual(state.bookmarks,['existing','old-id']);assert.deepEqual(state.read,['seen']);
  assert.throws(()=>mergePreferences({...state,bookmarks:Array.from({length:5000},(_,i)=>'existing-'+i)},incoming,[]));
});
test('storage success writes only preference keys, never read history',()=>{
  const storage=memory();assert.deepEqual(writePreferences(storage,profile()),{ok:true,restored:true});
  assert.deepEqual(JSON.parse(storage.values.get('radar:weights')),DEFAULT_WEIGHTS);
  assert.deepEqual(JSON.parse(storage.values.get('radar:saved')),['public-id']);assert.equal(storage.values.get('radar:read'),'read-marker');
});
test('failure before writes leaves storage alone and a second-write failure rolls back first',()=>{
  const storage=memory(),original=new Map(storage.values);let calls=0;
  storage.setItem=(key,value)=>{calls++;if(calls===2)throw Error('quota');storage.values.set(key,value);};
  assert.deepEqual(writePreferences(storage,profile()),{ok:false,restored:true});assert.deepEqual(storage.values,original);
  const blocked=memory();blocked.getItem=()=>{throw Error('denied');};blocked.setItem=()=>assert.fail('must not write');
  assert.deepEqual(writePreferences(blocked,profile()),{ok:false,restored:true});
});
test('rollback removes a newly introduced key; rollback failure is reported without false success',()=>{
  const storage=memory();storage.values.delete('radar:weights');let calls=0;
  storage.setItem=(key,value)=>{if(++calls===2)throw Error('quota');storage.values.set(key,value);};
  assert.deepEqual(writePreferences(storage,profile()),{ok:false,restored:true});assert.ok(!storage.values.has('radar:weights'));
  const broken=memory();let writes=0;broken.setItem=(key,value)=>{if(++writes>1)throw Error('blocked');broken.values.set(key,value);};
  assert.deepEqual(writePreferences(broken,profile()),{ok:false,restored:false});assert.equal(broken.values.get('radar:saved'),'original-saved');assert.equal(broken.values.get('radar:read'),'read-marker');
});
test('invalid profiles never touch storage',()=>{
  assert.throws(()=>writePreferences({getItem:()=>assert.fail('must not read')},profile({version:3})));
});
