'use strict';
(() => {
  const CATEGORIES = {
    all: ['すべて', 'おすすめの記事', '気になる発見を、次の一手へ。'],
    technology: ['技術・AI', '技術・GitHub・AI', '公開プロジェクトと開発の発見。GitHub・AIで絞り込めます。'],
    deals: ['お得情報', 'お得情報', 'このジャンルの収集元は未接続です。条件や期限を確認できる原典の接続は今後の対応です。'],
    trends: ['流行・話題', '流行・話題', '公開の話題と趣味の発見。Xの自動収集は未対応です。'],
    github: ['GitHub 発掘', 'コードの宝探し', '使ってみたいOSS、組み合わせたい技術、成長中のプロジェクト。'],
    ai: ['AI & 開発', 'AIの最前線', '話題性だけでなく、使い道まで考える。'],
    money: ['収益化アイデア', 'アイデアの種', '収益保証ではありません。元ネタと検証するべき仮説を紹介します。'],
    security: ['セキュリティ', '知っておきたいリスク', 'JVN・IPA・JPCERT/CC・CISAなど信頼できる発信元を優先。'],
    travel: ['旅行・イベント', '次の休日はどこへ？', '関東発のドライブ、離島、温泉、絶景を優先。'],
    social: ['ネットの話題', 'いま、何が話題？', 'Hacker Newsなど公開情報を使用。Xポスト自体のランキングではありません。'],
    hobby: ['ゲーム・趣味', '好きなことを深掘り', 'ポケモン、ボードゲーム、クルマ、ガジェットなど。']
  };
  const DEFAULT_WEIGHTS = RadarFeed.DEFAULT_WEIGHTS;
  const ICONS = {technology:'⌘',deals:'◉',trends:'◎',github:'⌘',ai:'✧',money:'◐',security:'⬡',travel:'↗',social:'◎',hobby:'♧'};
  const readStore = (k, fallback) => {try { const value = JSON.parse(localStorage.getItem(k)); return value ?? fallback; } catch {return fallback;} };
  const state = {items:[], category:'all', savedView:false, weights:RadarFeed.normalizeWeights(readStore('radar:weights',{})), bookmarks:RadarFeed.remapIds(readStore('radar:saved',[]),[]), read:RadarFeed.remapIds(readStore('radar:read',[]),[]), search:'',sort:'recommended',unreadOnly:false, meta:{}};
  const $ = (s) => document.querySelector(s);
  const $$ = (s) => Array.from(document.querySelectorAll(s));
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const safeUrl = (u) => {try {const parsed = new URL(u);return ['https:','http:'].includes(parsed.protocol)?parsed.href:'#';}catch{return '#';}};
  const store = (key,value) => {try{localStorage.setItem(key,JSON.stringify(value));}catch{/* best effort */}};
  const relative = (iso) => {const ts=Date.parse(iso||'');if(!Number.isFinite(ts))return '参考情報';const delta=Math.max(0,Date.now()-ts);if(delta<3600000)return `${Math.max(1,Math.floor(delta/60000))}分前`;if(delta<86400000)return `${Math.floor(delta/3600000)}時間前`;if(delta<604800000)return `${Math.floor(delta/86400000)}日前`;return new Date(ts).toLocaleDateString('ja-JP',{month:'numeric',day:'numeric'});};
  const viewed = (id) => state.read.includes(id);
  const saved = (id) => state.bookmarks.includes(id);
  const prettyCount = (n) => Number(n)>=10000?`${(n/10000).toFixed(1)}万`:Number(n).toLocaleString('ja-JP');
  let toastTimer;
  function toast(s){const node=$('#toast');node.textContent=s;node.classList.add('show');clearTimeout(toastTimer);toastTimer=setTimeout(()=>node.classList.remove('show'),2700);}
  function categoryNav(cat, saveView=false){if(detailId()!==null){history.pushState(null,'',location.pathname+location.search);}state.category=cat;state.savedView=saveView;state.search='';state.unreadOnly=false;$('#search').value='';$('#unreadFilter').classList.remove('active');$('#unreadFilter').setAttribute('aria-pressed','false');render();window.scrollTo({top:0,behavior:'smooth'});}
  function filtered(){return RadarFeed.query(state.items,state);}
  function renderCard(item,feature=false){const id=esc(item.id);const isSaved=saved(item.id);const url=safeUrl(item.url);const isRepo=item.category==='github';const isIdea=item.category==='money';const action=RadarFeed.nextAction(item);
    const category=state.category!=='all'&&!state.savedView&&RadarFeed.itemCategories(item).includes(state.category)?state.category:item.category;
    const observation=isRepo?RadarFeed.repoMeta(item):null;
    const origin=RadarFeed.sourceInfo(item),date=RadarFeed.articleDate(item);
    const sourceInfo=`<div class="provenance"><span>${esc(origin.kind)}</span>${item.source_url&&item.source_url!==item.url?` · <a href="${esc(safeUrl(item.source_url))}" target="_blank" rel="noopener noreferrer">取得元のデータ ↗</a>`:''}${origin.note?`<p>${esc(origin.note)}</p>`:''}${origin.security?`<p class="security-note">${esc(origin.security)}</p>`:''}${origin.travel?`<p class="travel-note">${esc(origin.travel)}</p>`:''}${item.security?.cves.length?`<p>記事中のCVE表記: ${item.security.cves.map(esc).join(' / ')}</p>`:''}${item.security?.exploitation_status==='listed_in_kev'?`<p>対象: ${esc(item.security.vendor||'提供元未確認')} / ${esc(item.security.product||'製品未確認')}</p><p>KEV追加日は攻撃日・公表日ではありません。</p><p>CISAの対応案内: ${esc(item.security.required_action||'未確認。取得元のカタログを確認してください。')}</p>`:''}</div>`;
    const meta=isRepo?`<div class="repo-stats">${typeof item.stars==='number'?`<span>★ <b>${prettyCount(item.stars)}</b></span>`:'<span>スター数未確認</span>'}${item.language?`<span>● ${esc(item.language)}</span>`:'<span>言語未確認</span>'}${item.license?`<span>License: ${esc(item.license)}</span>`:'<span>ライセンス未確認</span>'}${observation.group?`<span class="repo-group">${esc(observation.group)}</span>`:''}<span>${esc(observation.observed)}</span><span class="star-comparison">${esc(observation.delta)}</span>${observation.caution?`<span>${esc(observation.caution)}</span>`:''}</div>`:'';
    const reason=item.reason?`<p class="why"><strong>注目する理由 · </strong>${esc(item.reason)}</p>`:'';
    const tags=(item.tags||[]).slice(0,4).map(t=>item.source==='関東発ドライブ'&&t==='関東'?'検索条件:関東':t).map(t=>`<span class="tag">#${esc(t)}</span>`).join('')+RadarFeed.itemCategories(item).filter(c=>c!==category).map(c=>`<span class="tag">${esc(CATEGORIES[c][0])}</span>`).join('');
    const references=(label,rows,duplicate=false)=>rows?.length?`<details class="article-references"><summary>${label}（${rows.length}件）</summary><ul>${rows.map(ref=>`<li><a href="${esc(safeUrl(ref.url))}" target="_blank" rel="noopener noreferrer" data-open="${duplicate?id:esc(ref.id)}">${esc(ref.title)} — ${esc(ref.source)}</a></li>`).join('')}</ul></details>`:'';
    const related=references('URL比較でまとめた掲載元・元リンク',item.duplicates,true)+references('似た見出し（同じ記事とは未確認）',item.related);
    return `<article class="article ${feature?'feature':''} ${item.demo?'demo-card':''}" data-id="${id}">
      ${feature?`<div class="feature-label">${esc(RadarFeed.spotlightLabel(state.meta,{cached:feedCached,online:navigator.onLine}))}</div>`:''}
      <div class="card-top"><span class="category-pill ${esc(category)}">${ICONS[category]} ${esc(CATEGORIES[category][0])}</span><span class="card-time">${item.demo?'プレビュー':item.published?`<time datetime="${esc(date.datetime)}" title="${esc(date.title)}">${esc(date.label)} ${esc(date.text)}</time>`:'掲載日時不明'}</span><button class="save-btn ${isSaved?'saved':''}" aria-label="あとで読むに保存" data-save="${id}" aria-pressed="${isSaved}">${isSaved?'♥':'♡'}</button></div>
      <h3><a href="#article/${esc(encodeURIComponent(item.id))}" data-detail="${id}">${esc(item.title)} →</a></h3><p class="summary">${esc(item.summary)}</p>
      <div class="card-source"><span class="source">${esc(item.source||'公開ソース')}</span>${isIdea?'<span class="hypothesis-label">収益性未検証</span>':''}</div>${reason}
      <div class="card-footer">${action?`<button class="action" data-prompt="${id}" aria-label="${esc(action.label)}指示をコピー">${item.category==='travel'?'計画をコピー':isRepo?'30分で試す指示':'検証案をコピー'}</button>`:''}<a class="external" href="${esc(url)}" target="_blank" rel="noopener noreferrer" data-open="${id}">元記事 →</a></div>
      ${action?`<details class="next-action"><summary>${esc(action.label)} · 指示を確認</summary><p>選んだ記事の公開情報だけをコピーします。外部ツールへの送信や実行は行いません。貼り付け前に内容を確認してください。</p><pre tabindex="0" role="region" aria-label="${esc(action.label)}指示の全文">${esc(action.prompt)}</pre></details>`:''}
      <details class="card-analysis"><summary>出典・参考情報</summary>${meta}${sourceInfo}${isIdea?`<p class="hypothesis-note">収益性未検証 · 元ネタ: <a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(item.source||'取得元')} ↗</a>。顧客需要・費用・ライセンスは要確認。</p>`:''}${related}<div class="tags">${tags}</div><span class="rank">独自スコア（参考値） ${Math.round(item.score)}/100${viewed(item.id)?' · 既読':''}</span></details>
    </article>`;
  }
  function render(){
    const focused=document.activeElement;
    const focusKey=['data-save','data-chip'].find(key=>focused?.hasAttribute(key));
    const focusValue=focusKey?focused.getAttribute(focusKey):null;
    const focusContainer=focused.closest('#sourceFilters')?'#sourceFilters':focusKey==='data-chip'?'#mobileChips':null;
    const [kicker,title,desc]=state.savedView?['SAVED DISCOVERIES','保存した記事','あとで読みたい発見だけを集めました。']:CATEGORIES[state.category];$('#sectionKicker').textContent=kicker.toUpperCase();$('#sectionTitle').innerHTML=`${esc(title)} <span class="h2-spark">✳</span>`;$('#sectionDesc').textContent=desc+' '+(state.sort==='latest'?'新着順：原典日時の新しい順（日時不明は最後）。':state.sort==='popular'?'注目度順：GitHubはスター数、他は独自スコアの順。':'おすすめ順：興味の重みと新しさを使い、検索・保存一覧以外では候補枠の偏りを抑えます（参考値）。');
    const selected=state.savedView?'saved':state.category;
    const selectedGenre=Object.keys(RadarFeed.GENRES).find(key=>RadarFeed.GENRES[key].includes(selected))||selected;
    const selectButton=(node,active)=>{node.classList.toggle('active',active);node.setAttribute('aria-pressed',String(active));};
    $$('.nav-item[data-category]').forEach(n=>selectButton(n,n.dataset.category===selectedGenre));selectButton($('#savedNav'),state.savedView);$$('[data-mobile-go]').forEach(n=>selectButton(n,n.dataset.mobileGo===selectedGenre));
    $('#mobileChips').innerHTML=['all',...Object.keys(RadarFeed.GENRES)].map(cat=>[cat,CATEGORIES[cat]]).map(([cat,label])=>`<button data-chip="${cat}" aria-pressed="${cat===selectedGenre}" class="${cat===selectedGenre&&!state.savedView?'active':''}">${esc(label[0])}</button>`).join('')+`<button data-chip="saved" aria-pressed="${state.savedView}" class="${state.savedView?'active':''}">♡ 保存</button>`;
    const sourceKeys=['technology','github','ai'].includes(selected)?['technology','github','ai']:['trends','social','hobby'].includes(selected)?['trends','social','hobby']:[];
    $('#sourceFilters').hidden=!sourceKeys.length;
    $('#sourceFilters').innerHTML=sourceKeys.map(cat=>`<button data-chip="${cat}" aria-pressed="${cat===selected}">${esc(CATEGORIES[cat][0])}</button>`).join('');
    const entries=filtered();$('#feed').innerHTML=entries.length?entries.map((x,index)=>renderCard(x,index===0&&!state.savedView&&!state.search&&state.sort==='recommended')).join(''):'';$('#empty').hidden=!!entries.length;$('#savedCount').textContent=state.bookmarks.length;$('#metricSaved').textContent=state.bookmarks.length;
    $('#metricTotal').textContent=state.items.length;$('#metricRepos').textContent=state.items.filter(x=>x.category==='github').length;$('#metricMoney').textContent=state.items.filter(x=>x.category==='money').length;
    for(const cat of Object.keys(CATEGORIES)){const node=$(`#count-${cat}`);if(node)node.textContent=cat==='all'?state.items.length:state.items.filter(i=>RadarFeed.inGenre(i,cat)).length;}
    $('#empty h3').textContent=state.category==='deals'?'お得情報は未収集です':'条件に合う情報がありません';
    $('#empty p').textContent=state.category==='deals'?'収集元は未接続です。ほかのジャンルをご覧ください。':'カテゴリ・検索・未読フィルターを変えてみてください。';
    $('#feedSummary').textContent=state.meta.mode?`${title}：${entries.length}件表示${state.unreadOnly?'（未読のみ）':''}。${entries.length?'':'条件をリセットできます。'}`:'記事を表示できません。取得状況を確認してください。';
    const detailScroll=detailId()!==null?window.scrollY:null;
    renderDetail();
    if(detailScroll!==null)window.scrollTo({top:detailScroll,behavior:'instant'});
    if(focusKey&&!focused.isConnected){
      const replacement=$$(focusContainer?`${focusContainer} [${focusKey}]`:`[${focusKey}]`).find(node=>node.getAttribute(focusKey)===focusValue&&node.getClientRects().length);
      (replacement||$('#sectionTitle')).focus({preventScroll:true});
    }
    if(focused.id==='clearFilters'&&entries.length)$('#sectionTitle').focus({preventScroll:true});
  }
  function bind(){document.addEventListener('click',async ev=>{const b=ev.target.closest('[data-save],[data-open],[data-prompt],[data-category],[data-chip],[data-mobile-go],[data-detail],[data-return],[data-discuss]');if(!b)return;
      if(b.dataset.discuss){const item=state.items.find(row=>row.id===b.dataset.discuss);if(item)await openDiscussion(item);return;}
      if(b.hasAttribute('data-return')){ev.preventDefault();returnToList();return;}
      if(b.dataset.detail){
        if(ev.metaKey||ev.ctrlKey||ev.shiftKey||ev.altKey||ev.button!==0)return;
        ev.preventDefault();const fromList=detailId()===null;
        if(fromList){listScroll=window.scrollY;listFocusId=b.dataset.detail;}
        history.pushState({radarDetailFromList:fromList},'','#article/'+encodeURIComponent(b.dataset.detail));routeChanged();return;
      }
      if(b.dataset.save){const id=b.dataset.save;state.bookmarks=saved(id)?state.bookmarks.filter(s=>s!==id):[...state.bookmarks,id];store('radar:saved',state.bookmarks);toast(saved(id)?'保存しました':'保存を解除しました');render();return;}
      if(b.dataset.open){const id=b.dataset.open;if(!viewed(id)){state.read.push(id);store('radar:read',state.read);}return;}
      if(b.dataset.prompt){const item=state.items.find(i=>i.id===b.dataset.prompt);if(!item)return;const action=RadarFeed.nextAction(item);if(!action)return;try{await navigator.clipboard.writeText(action.prompt);toast('選んだ記事の指示をコピーしました');}catch{toast('コピーできませんでした。ブラウザーの権限を確認してください。');}return;}
      if(b.dataset.category)categoryNav(b.dataset.category);
      if(b.dataset.chip)categoryNav(b.dataset.chip==='saved'?'all':b.dataset.chip,b.dataset.chip==='saved');
      if(b.dataset.mobileGo)categoryNav(b.dataset.mobileGo==='saved'?'all':b.dataset.mobileGo,b.dataset.mobileGo==='saved');
    });
    $('#savedNav').addEventListener('click',()=>categoryNav('all',true));$('#search').addEventListener('input',e=>{state.search=e.target.value;render();});$('#sort').addEventListener('change',e=>{state.sort=e.target.value;render();});$('#unreadFilter').addEventListener('click',()=>{state.unreadOnly=!state.unreadOnly;$('#unreadFilter').classList.toggle('active',state.unreadOnly);$('#unreadFilter').setAttribute('aria-pressed',String(state.unreadOnly));render();});$('#clearFilters').addEventListener('click',()=>categoryNav('all'));
    for(const id of ['settingsDesktop','settingsTop','settingsInline','settingsBottom'])$('#'+id).addEventListener('click',openSettings);
    $('#resetPrefs').addEventListener('click',()=>{state.weights={...DEFAULT_WEIGHTS};store('radar:weights',state.weights);drawPrefs();render();toast('優先度を初期設定に戻しました');});
    $('#prefsDialog').addEventListener('close',()=>{clearImport();render();});
    for(const id of ['prefsDialog','discussionDialog'])$('#'+id).addEventListener('keydown',trapDialogTab);
    $('#weightControls').addEventListener('input',e=>{if(!e.target.matches('input[type="range"]'))return;const cat=e.target.dataset.weight;state.weights[cat]=Number(e.target.value);e.target.closest('.weight-row').querySelector('strong').textContent=weightLabel(state.weights[cat]);e.target.setAttribute('aria-valuetext',`${state.weights[cat]}: ${weightLabel(state.weights[cat])}`);store('radar:weights',state.weights);});
  }
  function trapDialogTab(event){
      if(event.key!=='Tab')return;
      const controls=Array.from(event.currentTarget.querySelectorAll('button,input,select,textarea,a[href],[tabindex]'))
        .filter(node=>!node.disabled&&node.tabIndex>=0&&node.getClientRects().length);
      const first=controls[0],last=controls.at(-1);
      if(event.shiftKey&&document.activeElement===first){event.preventDefault();last?.focus();}
      else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus();}
  }
  function weightLabel(v){return ({1:'低め',2:'やや低め',3:'標準',4:'高め',5:'最優先'})[v]||'標準';}
  function drawPrefs(){$('#weightControls').innerHTML=Object.entries(DEFAULT_WEIGHTS).map(([cat])=>`<div class="weight-row"><header><label for="weight-${cat}">${ICONS[cat]} ${esc(CATEGORIES[cat][0])}</label><strong>${weightLabel(state.weights[cat])}</strong></header><input id="weight-${cat}" type="range" min="1" max="5" step="1" value="${state.weights[cat]}" data-weight="${cat}" aria-valuetext="${state.weights[cat]}: ${weightLabel(state.weights[cat])}" /></div>`).join('');}
  let listScroll=0,listFocusId=null;
  function detailId(){if(!location.hash.startsWith('#article/'))return null;try{return decodeURIComponent(location.hash.slice(9));}catch{return '';}}
  function renderDetail(){
    const requestedId=detailId(),detail=$('#articleDetail');
    $('#feedSection').hidden=requestedId!==null;$('#sourceHealth').hidden=requestedId!==null;detail.hidden=requestedId===null;
    if(requestedId===null){detail.replaceChildren();return;}
    const item=state.items.find(row=>row.id===requestedId||(row.aliases||[]).includes(requestedId));
    const back='<button type="button" class="secondary-button" data-return>← 一覧へ戻る</button>';
    if(!item){detail.innerHTML=back+'<h1 id="detailTitle" tabindex="-1">記事が見つかりません</h1><p>現在の公開データにない記事です。一覧から選び直してください。</p>';return;}
    const id=item.id;
    if(!viewed(id)){state.read.push(id);store('radar:read',state.read);}
    const view=RadarFeed.articleView(item),origin=RadarFeed.sourceInfo(item),date=RadarFeed.articleDate(item),url=safeUrl(item.url),action=RadarFeed.nextAction(item);
    detail.innerHTML=`${back}<article class="detail-article">
      <div class="detail-category"><span class="category-pill ${esc(item.category)}">${esc(CATEGORIES[item.category][0])}</span>${item.demo?'<span>デモ</span>':''}</div>
      <h1 id="detailTitle" tabindex="-1">${esc(item.title)}</h1>
      <p class="detail-source">${esc(item.source)} · ${item.published?`${esc(date.label)} ${esc(date.text)}`:'掲載日時不明'}</p>
      <p class="provenance">${esc(origin.kind)}。${esc(origin.note||'原典の主張を独立検証したものではありません。')}</p>
      <section class="detail-overview" aria-labelledby="overviewTitle"><h2 id="overviewTitle">30秒の概要</h2><p class="overview-label">${esc(view.overviewLabel)}</p><p>${esc(view.overview)}</p></section>
      <section class="detail-note" aria-labelledby="noteTitle"><h2 id="noteTitle">あなたへのひとこと</h2><p>${esc(view.note)}</p><small>ルールベースの推薦理由。個人への適合性や成果を保証する評価ではありません。</small></section>
      <div class="detail-actions"><button type="button" class="chatgpt-button" data-discuss="${esc(id)}">ChatGPTで考察</button><a class="primary-link" href="${esc(url)}" target="_blank" rel="noopener noreferrer" data-open="${esc(id)}">元記事を開く ↗</a><button class="save-btn ${saved(id)?'saved':''}" data-save="${esc(id)}" aria-label="あとで読むに保存" aria-pressed="${saved(id)}">${saved(id)?'♥':'♡'}</button></div>
      <details class="detail-points" open><summary>この記事のポイント</summary><h3>${esc(view.overviewHeading)}</h3><p>${esc(view.overview)}</p><p>${esc(view.attribution)}</p><h3>解釈・推薦理由</h3><p>${esc(view.note)}</p><h3>未確認・確認したいこと</h3><ul>${view.unknowns.map(text=>`<li>${esc(text)}</li>`).join('')}</ul></details>
      ${item.security?.cves.length?`<section class="detail-points"><h2>脆弱性の原典情報</h2><p>CVE: ${item.security.cves.map(esc).join(' / ')}</p>${item.security.exploitation_status==='listed_in_kev'?`<p>対象: ${esc(item.security.vendor||'提供元未確認')} / ${esc(item.security.product||'製品未確認')}</p><p>KEV追加日は攻撃日・公表日ではありません。</p><p>CISAの対応案内: ${esc(item.security.required_action||'未確認。原典を確認してください。')}</p>`:''}${item.source_url?`<a class="external" href="${esc(safeUrl(item.source_url))}" target="_blank" rel="noopener noreferrer">取得元のデータを確認 ↗</a>`:''}</section>`:''}
      <details class="detail-points"><summary>5軸のおすすめ評価</summary><p>情報源の確度・セキュリティ緊急性とは別の評価です。</p><dl class="assessment-list">${view.axes.map(name=>`<div><dt>${esc(name)}</dt><dd>未評価<span>採点に必要な根拠データがありません。</span></dd></div>`).join('')}</dl></details>
      <section class="detail-keywords" aria-labelledby="keywordsTitle"><h2 id="keywordsTitle">関連キーワード</h2><div class="tags">${view.keywords.length?view.keywords.map(word=>`<span class="tag">${esc(word)}</span>`).join(''):'<span>未確認</span>'}</div></section>
      ${origin.security?`<p class="security-note">${esc(origin.security)}</p>`:''}${origin.travel?`<p class="travel-note">${esc(origin.travel)}</p>`:''}
      ${action?`<details class="next-action"><summary>${esc(action.label)} · 指示を確認</summary><pre tabindex="0" role="region" aria-label="${esc(action.label)}指示の全文">${esc(action.prompt)}</pre><button class="action" data-prompt="${esc(id)}">指示をコピー</button></details>`:''}
    </article>`;
  }
  function routeChanged(){
    if($('#discussionDialog').open)$('#discussionDialog').close();
    render();
    if(detailId()!==null){window.scrollTo({top:0,behavior:'instant'});$('#detailTitle')?.focus({preventScroll:true});}
    else{window.scrollTo({top:listScroll,behavior:'instant'});const origin=$$('[data-detail]').find(node=>node.dataset.detail===listFocusId);(origin||$('#sectionTitle')).focus({preventScroll:true});}
  }
  function returnToList(){
    if(history.state?.radarDetailFromList){history.back();return;}
    history.replaceState(null,'',location.pathname+location.search);routeChanged();
  }
  let discussionAttempt=0;
  async function copyDiscussion(){
    const attempt=++discussionAttempt,text=$('#discussionText').value;if(!text)return;
    $('#discussionStatus').textContent='コピーしています…';
    try{await navigator.clipboard.writeText(text);if(attempt===discussionAttempt&&$('#discussionDialog').open)$('#discussionStatus').textContent='コピーしました。ChatGPTを開いて貼り付けてください。';}
    catch{if(attempt!==discussionAttempt||!$('#discussionDialog').open)return;$('#discussionStatus').textContent='コピーできませんでした。文面を選択して手動でコピーしてください。';$('#discussionText').focus();$('#discussionText').select();}
  }
  async function openDiscussion(item){
    discussionAttempt++;$('#discussionStatus').textContent='';
    try{$('#discussionText').value=RadarFeed.discussionFor(item,{generatedAt:state.meta.generated_at,mode:state.meta.mode});$('#copyDiscussion').disabled=false;}
    catch{$('#discussionText').value='';$('#copyDiscussion').disabled=true;$('#discussionStatus').textContent='URLや文面が長すぎるため相談文を作れませんでした。元記事を確認し、必要な情報を手動で選んでください。';}
    $('#discussionDialog').showModal();if(!$('#copyDiscussion').disabled)await copyDiscussion();
  }
  let pendingPreferences=null,importAttempt=0;
  function transferMessage(message){$('#transferStatus').textContent=message;}
  function clearImport(){pendingPreferences=null;importAttempt++;$('#importPreview').hidden=true;$('#importSummary').textContent='';$('#importWeights').textContent='';}
  function bindTransfers(){
    $('#exportPrefs').addEventListener('click',()=>{
      let url,link;
      try{
        const text=JSON.stringify(RadarFeed.portablePreferences(state));
        RadarFeed.decodePreferences(text); // Enforce the same byte limit as the importer.
        url=URL.createObjectURL(new Blob([text],{type:'application/json;charset=utf-8'}));
        link=document.createElement('a');link.href=url;link.download='curiosity-radar-settings-v1.json';link.hidden=true;document.body.append(link);link.click();
        transferMessage('JSONのダウンロードを開始しました。公開せず、ご自身で保管してください。');
      }catch{transferMessage('書き出せませんでした。保存IDの形式・件数やブラウザーのダウンロード設定を確認してください。');}
      finally{link?.remove();if(url)setTimeout(()=>URL.revokeObjectURL(url),60000);}
    });
    $('#importPrefs').addEventListener('click',()=>$('#prefsFile').click());
    $('#cancelImport').addEventListener('click',()=>{clearImport();transferMessage('読み込みを取り消しました。設定は変更していません。');$('#importPrefs').focus();});
    $('#prefsFile').addEventListener('change',async event=>{
      const file=event.target.files[0];event.target.value='';clearImport();if(!file)return;
      const attempt=importAttempt;
      transferMessage('設定JSONを確認しています…');
      try{
        if(file.size>RadarFeed.MAX_PREFERENCES_BYTES)throw Error('File too large');
        const text=await file.text();if(attempt!==importAttempt)return;
        const value=RadarFeed.decodePreferences(text);
        pendingPreferences=value;
        const ids=RadarFeed.remapIds(value.bookmarks,state.items),known=new Set(state.items.map(item=>item.id));
        $('#importSummary').textContent=`保存ID ${ids.length}件（現在の記事に一致 ${ids.filter(id=>known.has(id)).length}件）。一致しないIDも保持します。`;
        $('#importWeights').textContent=Object.keys(DEFAULT_WEIGHTS).map(key=>`${CATEGORIES[key][0]} ${value.weights[key]}: ${weightLabel(value.weights[key])}`).join(' / ');
        $('#importPreview').hidden=false;transferMessage('内容を確認してから適用してください。まだ設定は変更していません。');$('#applyPrefs').focus();
      }catch{if(attempt===importAttempt)transferMessage('読み込めませんでした。形式v1の設定JSON（1 MiB以内・保存ID 5000件以内）を選んでください。設定は変更していません。');}
    });
    $('#applyPrefs').addEventListener('click',()=>{
      if(!pendingPreferences)return;
      let merged,result;
      try{merged=RadarFeed.mergePreferences(state,pendingPreferences,state.items);}
      catch{transferMessage('適用できませんでした。保存IDの形式と追加後の件数・容量（5000件・1 MiB以内）を確認してください。設定は変更していません。');return;}
      try{result=RadarFeed.writePreferences(localStorage,merged);}catch{result={ok:false,restored:true};}
      if(!result.ok){
        if(!result.restored){state.weights=RadarFeed.normalizeWeights(readStore('radar:weights',state.weights));state.bookmarks=RadarFeed.remapIds(readStore('radar:saved',state.bookmarks),state.items);drawPrefs();render();}
        transferMessage(result.restored?'保存できませんでした。読み込んだ設定は適用していません。':'保存と復元に失敗しました。一部の設定が変わった可能性があるため確認してください。');return;
      }
      state.weights=merged.weights;state.bookmarks=merged.bookmarks;drawPrefs();render();clearImport();transferMessage('重みと保存IDを適用しました。既存の保存・既読は保持しています。');$('#importPrefs').focus();
    });
  }
  function openSettings(){clearImport();transferMessage('');drawPrefs();const d=$('#prefsDialog');if(!d.open)d.showModal();}
  function renderSourceHealth(){
    const rows=state.meta.mode==='demo'?[]:state.meta.source_health;
    $('#sourceHealthRows').innerHTML=rows?.length?rows.map(row=>`<li><a href="${esc(safeUrl(row.url))}" target="_blank" rel="noopener noreferrer">${esc(row.name)}</a>：${esc({ok:'成功',partial:'一部取得',failed:'取得失敗'}[row.status])} · 取得候補 ${row.count}件${row.error?`（${esc(RadarFeed.healthIssue(row.error))}）`:''}<br>確認 ${esc(new Date(row.checked_at).toLocaleString('ja-JP'))} / 最終成功 ${row.last_success_at?esc(new Date(row.last_success_at).toLocaleString('ja-JP')):'未確認'}${row.consecutive_failures?`<br>保存履歴で連続取得エラー ${row.consecutive_failures}回${row.history_available?'':'（それ以前は未確認）'}`:''}</li>`).join(''):'<li>このデータの情報源ごとの取得状況は未確認です。</li>';
  }
  let feedCached = false;
  function updateFeedStatus(){
    const status=RadarFeed.describe(state.meta,{cached:feedCached,online:navigator.onLine});
    $('#sidebarStatus').textContent=status.label;
    $$('.feature-label').forEach(node=>node.textContent=RadarFeed.spotlightLabel(state.meta,{cached:feedCached,online:navigator.onLine}));
    $('#notice').hidden=!status.messages.length;
    $('#notice').textContent=status.messages.join(' ');
  }
  async function load(){try {
      const response=await fetch('data/news.json',{cache:'no-store'});
      if(!response.ok)throw Error('Feed HTTP error');
      const data=RadarFeed.validate(await response.json());
      state.items=data.items;state.meta=data;
      state.bookmarks=RadarFeed.remapIds(state.bookmarks,state.items);
      state.read=RadarFeed.remapIds(state.read,state.items);
      store('radar:saved',state.bookmarks);store('radar:read',state.read);
      feedCached=response.headers.get('X-Curiosity-Radar-Cache')==='fallback';
      $('#updatedAt').textContent=(data.mode==='demo'?'デモ作成日時 ':'データ更新日時 ')+new Date(data.generated_at).toLocaleString('ja-JP');
      renderSourceHealth();updateFeedStatus();render();
    }catch{
      state.items=[];state.meta={};renderSourceHealth();
      $('#updatedAt').textContent='更新日時を確認できません';
      $('#sidebarStatus').textContent=navigator.onLine?'読み込みエラー':'オフライン · データなし';
      showNotice('データを読み込めませんでした。通信または公開JSONに問題があります。接続を確認して再読み込みしてください。');
      render();$('#empty').hidden=true;
    }}
  for(const event of ['online','offline'])window.addEventListener(event,()=>{if(state.meta.mode)updateFeedStatus();else load();});
  setInterval(()=>{if(state.meta.mode)updateFeedStatus();},60000);
  function showNotice(m){$('#notice').hidden=false;$('#notice').textContent=m;}
  window.addEventListener('hashchange',event=>{if(new URL(event.oldURL).hash.startsWith('#article/')||new URL(event.newURL).hash.startsWith('#article/'))routeChanged();});
  $('#copyDiscussion').addEventListener('click',copyDiscussion);
  $('#discussionDialog').addEventListener('close',()=>{discussionAttempt++;});
  bind();bindTransfers();load();
  if('serviceWorker' in navigator){window.addEventListener('load',()=>navigator.serviceWorker.register('sw.js').catch(()=>{}));}
})();
