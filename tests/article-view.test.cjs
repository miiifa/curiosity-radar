const {test}=require('node:test');const assert=require('node:assert/strict');const {articleView}=require('../feed-status.js');
const item={category:'travel',title:'公開テスト',summary:'原典の短い説明',tags:['旅','旅','原典'],source_kind:'search_feed'};
test('overview labels excerpts honestly and the five axes remain unscored',()=>{
 const view=articleView(item);assert.equal(view.overview,item.summary);assert.ok(view.overviewLabel.includes('RSSの抜粋'));assert.ok(view.overviewLabel.includes('独自要約ではありません'));
 assert.deepEqual(view.axes,['発見度','関連度','行動しやすさ','実利','考察の余地']);assert.deepEqual(view.keywords,['旅','原典']);assert.ok(!('score' in view));
});
test('security, travel and revenue retain uncertainty rather than a verified badge',()=>{
 for(const category of ['security','travel','money','github']){const view=articleView({...item,category});assert.ok(view.unknowns.length);assert.ok(view.unknowns.some(text=>/未確認|未検証|原典|要確認/.test(text)));}
});
test('missing overview and reason remain explicit; unrelated local fields do not enter the view',()=>{
 const view=articleView({...item,summary:'',reason:'',token:'PRIVATE_MARKER',read:['PRIVATE_MARKER']});assert.ok(view.overview.includes('ありません'));assert.ok(view.note.includes('未実施'));assert.ok(!JSON.stringify(view).includes('PRIVATE_MARKER'));
});
test('keyword lists are unique and capped without changing source text',()=>{
 const value={...item,tags:Array.from({length:20},(_,i)=>'語'+i),summary:'<script>untrusted</script>'};const view=articleView(value);assert.equal(view.keywords.length,7);assert.equal(view.overview,value.summary);assert.equal(value.tags.length,20);
});
test('generated business ideas belong to the app, never to the linked OSS author',()=>{
 const view=articleView({...item,category:'money',source:'着想元: fixture/repo',source_kind:undefined,summary:'OSSの導入・カスタマイズ支援の仮説'});
 assert.ok(view.overviewLabel.includes('アプリがルールベース'));assert.equal(view.overviewHeading,'アプリが作った仮説');assert.ok(view.attribution.includes('作者の発言ではなく'));assert.ok(view.attribution.includes('未検証'));
});
test('RSS revenue articles and unknown legacy ideas do not get a false attribution',()=>{
 const rss=articleView({...item,category:'money',source:'個人開発・事業化'});assert.ok(rss.overviewLabel.includes('RSS'));
 const unknown=articleView({...item,category:'money',source:'不明な出所',source_kind:undefined});assert.ok(unknown.overviewLabel.includes('出所未確認'));assert.ok(unknown.attribution.includes('断定しません'));
});
