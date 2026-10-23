'use strict';
(() => {
  const CATEGORIES = {
    all: ['すべて', '今日の発見', 'あなたの関心と、新しさから優先順位をつけています。'],
    github: ['GitHub 発掘', 'コードの宝探し', '使ってみたいOSS、組み合わせたい技術、成長中のプロジェクト。'],
    ai: ['AI & 開発', 'AIの最前線', '話題性だけでなく、使い道まで考える。'],
    money: ['収益化のヒント', 'アイデアの種', '収益保証ではありません。元ネタと検証するべき仮説を紹介します。'],
    security: ['セキュリティ', '知っておきたいリスク', 'JVN・IPA・JPCERT/CC・CISAなど信頼できる発信元を優先。'],
    travel: ['国内旅行', '次の休日はどこへ？', '関東発のドライブ、離島、温泉、絶景を優先。'],
    social: ['ネットの話題', 'いま、何が話題？', 'Hacker Newsなど公開情報を使用。Xポスト自体のランキングではありません。'],
    hobby: ['ゲーム・趣味', '好きなことを深掘り', 'ポケモン、ボードゲーム、クルマ、ガジェットなど。']
  };
  const DEFAULT_WEIGHTS = {github: 5, ai: 5, money: 5, security: 4, travel: 4, social: 3, hobby: 4};
  const ICONS = {github:'⌘',ai:'✧',money:'◐',security:'⬡',travel:'↗',social:'◎',hobby:'♧'};
  const readStore = (k, fallback) => {try { const value = JSON.parse(localStorage.getItem(k)); return value ?? fallback; } catch {return fallback;} };
  const state = {items:[], category:'all', savedView:false, weights:{...DEFAULT_WEIGHTS, ...readStore('radar:weights',{})}, bookmarks:readStore('radar:saved',[]), read:readStore('radar:read',[]), search:'',sort:'recommended',unreadOnly:false, meta:{}};
  const $ = (s) => document.querySelector(s);
  const $$ = (s) => Array.from(document.querySelectorAll(s));
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const safeUrl = (u) => {try {const parsed = new URL(u);return ['https:','http:'].includes(parsed.protocol)?parsed.href:'#';}catch{return '#';}};
  const store = (key,value) => {try{localStorage.setItem(key,JSON.stringify(value));}catch{/* best effort */}};
  const dateMs = (item) => {const d=Date.parse(item.published || '');return Number.isFinite(d)?d:0;};
  const relative = (iso) => {const ts=Date.parse(iso||'');if(!Number.isFinite(ts))return '参考情報';const delta=Math.max(0,Date.now()-ts);if(delta<3600000)return `${Math.max(1,Math.floor(delta/60000))}分前`;if(delta<86400000)return `${Math.floor(delta/3600000)}時間前`;if(delta<604800000)return `${Math.floor(delta/86400000)}日前`;return new Date(ts).toLocaleDateString('ja-JP',{month:'numeric',day:'numeric'});};
  const score = (i) => {const w=state.weights[i.category]||3;return (Number(i.score)||50)*(0.50+w*0.17);};
  const viewed = (id) => state.read.includes(id);
  const saved = (id) => state.bookmarks.includes(id);
  const prettyCount = (n) => Number(n)>=10000?`${(n/10000).toFixed(1)}万`:Number(n).toLocaleString('ja-JP');
  let toastTimer;
  function toast(s){const node=$('#toast');node.textContent=s;node.classList.add('show');clearTimeout(toastTimer);toastTimer=setTimeout(()=>node.classList.remove('show'),2700);}
  function categoryNav(cat, saveView=false){state.category=cat;state.savedView=saveView;state.search='';state.unreadOnly=false;$('#search').value='';$('#unreadFilter').classList.remove('active');$('#unreadFilter').setAttribute('aria-pressed','false');render();window.scrollTo({top:0,behavior:'smooth'});}
  function filtered(){let items=state.items.filter(i => CATEGORIES[i.category]);if(state.savedView)items=items.filter(i=>saved(i.id));else if(state.category!=='all')items=items.filter(i=>i.category===state.category);
    const q=state.search.trim().toLocaleLowerCase();if(q)items=items.filter(i=>[i.title,i.summary,i.source,i.reason,...(i.tags||[])].join(' ').toLocaleLowerCase().includes(q));if(state.unreadOnly)items=items.filter(i=>!viewed(i.id));
    if(state.sort==='latest')items.sort((a,b)=>dateMs(b)-dateMs(a) || score(b)-score(a));else if(state.sort==='popular')items.sort((a,b)=>(Number(b.stars)||Number(b.score)||0)-(Number(a.stars)||Number(a.score)||0));else items.sort((a,b)=>score(b)-score(a)||dateMs(b)-dateMs(a));return items;
  }
  function diversify(items){if(state.category!=='all'||state.savedView||state.search||state.sort!=='recommended')return items;
    const groups={};for(const item of items){(groups[item.category]??=[]).push(item);}const out=[];let loop=0;while(out.length<items.length&&loop++<items.length){let best=null,key=null;for(const [category,g] of Object.entries(groups)){if(!g.length)continue;const candidate=g[0];const last3=out.slice(-3).filter(i=>i.category===category).length;const penalty=last3*19;if(!best || score(candidate)-penalty>score(best)-out.slice(-3).filter(i=>i.category===key).length*19){best=candidate;key=category;}}if(!best)break;out.push(groups[key].shift());}return out;
  }
  function renderCard(item,feature=false){const id=esc(item.id);const isSaved=saved(item.id);const url=safeUrl(item.url);const isRepo=item.category==='github';const isIdea=item.category==='money';const meta=isRepo ? `<div class="repo-stats">${typeof item.stars === 'number'?`<span>★ <b>${prettyCount(item.stars)}</b></span>`:''}${item.language?`<span>● ${esc(item.language)}</span>`:''}${item.license?`<span>License: ${esc(item.license)}</span>`:'<span>ライセンス未確認</span>'}${item.star_delta?`<span>+${esc(item.star_delta)} stars / 前回比</span>`:''}</div>`:'';
    const reason=item.reason?`<p class="why"><strong>注目する理由 · </strong>${esc(item.reason)}</p>`:'';
    const tags=(item.tags||[]).slice(0,4).map(t=>`<span class="tag">#${esc(t)}</span>`).join('');
    return `<article class="article ${feature?'feature':''} ${item.demo?'demo-card':''}" data-id="${id}"><div class="card-top"><span class="category-pill ${esc(item.category)}">${ICONS[item.category]} ${esc(CATEGORIES[item.category][0])}</span><span class="card-time">${item.demo?'プレビュー':relative(item.published)}</span><button class="save-btn ${isSaved?'saved':''}" aria-label="${isSaved?'保存を解除':'あとで読むに保存'}" data-save="${id}">${isSaved?'♥':'♡'}</button></div><h3><a href="${esc(url)}" target="_blank" rel="noopener noreferrer" data-open="${id}">${esc(item.title)} ↗</a></h3><p class="summary">${esc(item.summary)}</p>${meta}${reason}<div class="tags">${tags}</div><div class="card-footer"><span class="source">${esc(item.source||'公開ソース')}</span><span class="rank">独自スコア ${Math.round(Number(item.score)||50)}/100${viewed(item.id)?' · 既読':''}</span><span class="card-spacer"></span>${isRepo||isIdea?`<button class="action" data-prompt="${id}">${isRepo?'Codexで試す ↗':'検証案をコピー ↗'}</button>`:''}<a class="external" href="${esc(url)}" target="_blank" rel="noopener noreferrer" data-open="${id}">元記事 →</a></div></article>`;
  }
  function render(){const [kicker,title,desc]=state.savedView?['SAVED DISCOVERIES','保存した記事','あとで読みたい発見だけを集めました。']:CATEGORIES[state.category];$('#sectionKicker').textContent=kicker.toUpperCase();$('#sectionTitle').innerHTML=`${esc(title)} <span class="h2-spark">✳</span>`;$('#sectionDesc').textContent=desc;
    $$('.nav-item[data-category]').forEach(n=>n.classList.toggle('active',!state.savedView&&n.dataset.category===state.category));$('#savedNav').classList.toggle('active',state.savedView);$$('[data-mobile-go]').forEach(n=>n.classList.toggle('active',n.dataset.mobileGo===(state.savedView?'saved':state.category)));
    $('#mobileChips').innerHTML=Object.entries(CATEGORIES).map(([cat,label])=>`<button data-chip="${cat}" class="${cat===state.category&&!state.savedView?'active':''}">${esc(label[0])}</button>`).join('')+`<button data-chip="saved" class="${state.savedView?'active':''}">♡ 保存</button>`;
    const entries=diversify(filtered());$('#feed').innerHTML=entries.length?entries.map((x,index)=>renderCard(x,index===0&&!state.savedView&&!state.search&&state.sort==='recommended')).join(''):'';$('#empty').hidden=!!entries.length;$('#savedCount').textContent=state.bookmarks.length;$('#metricSaved').textContent=state.bookmarks.length;
    $('#metricTotal').textContent=state.items.length;$('#metricRepos').textContent=state.items.filter(x=>x.category==='github').length;$('#metricMoney').textContent=state.items.filter(x=>x.category==='money').length;
    for(const cat of Object.keys(CATEGORIES)){`#count-${cat}` && ($(`#count-${cat}`).textContent=cat==='all'?state.items.length:state.items.filter(i=>i.category===cat).length);}
  }
  function promptFor(item){if(item.category==='github')return `以下のOSSを評価して、私が個人開発で実際に使う／改造する場合の提案をしてください。\n\nリポジトリ: ${item.url}\n概要: ${item.summary}\n\n1. README・ライセンス・セキュリティ・更新状況・依存関係の調査\n2. できること／できないことと実行コスト\n3. 30分で試せる最小の実験手順\n4. 私向けの応用アイデア3件と差別化\n5. 収益化する場合の顧客・課題・価格仮説（売上は保証しない）\n6. 最小MVPの実装、テスト、安全性検証\n不明点は推測と明記。規約違反や秘密情報の送信はしない。`;
    return `この収益化の仮説を検証してください。\nネタ: ${item.title}\n情報源: ${item.url}\n仮説: ${item.summary}\n\n顧客・課題・競合・解決策・課金方法・法規約・必要な費用・最小限の顧客検証方法を整理。データで裏付けられない売上予測を断定しない。`;}
  function bind(){document.addEventListener('click',async ev=>{const b=ev.target.closest('[data-save],[data-open],[data-prompt],[data-category],[data-chip],[data-mobile-go]');if(!b)return;
      if(b.dataset.save){const id=b.dataset.save;state.bookmarks=saved(id)?state.bookmarks.filter(s=>s!==id):[...state.bookmarks,id];store('radar:saved',state.bookmarks);toast(saved(id)?'保存しました':'保存を解除しました');render();return;}
      if(b.dataset.open){const id=b.dataset.open;if(!viewed(id)){state.read.push(id);store('radar:read',state.read);}return;}
      if(b.dataset.prompt){const item=state.items.find(i=>i.id===b.dataset.prompt);if(!item)return;try{await navigator.clipboard.writeText(promptFor(item));toast('Codexに貼り付ける指示をコピーしました');}catch{toast('コピーできませんでした。ブラウザーの権限を確認してください。');}return;}
      if(b.dataset.category)categoryNav(b.dataset.category);
      if(b.dataset.chip)categoryNav(b.dataset.chip==='saved'?'all':b.dataset.chip,b.dataset.chip==='saved');
      if(b.dataset.mobileGo)categoryNav(b.dataset.mobileGo==='saved'?'all':b.dataset.mobileGo,b.dataset.mobileGo==='saved');
    });
    $('#savedNav').addEventListener('click',()=>categoryNav('all',true));$('#search').addEventListener('input',e=>{state.search=e.target.value;render();});$('#sort').addEventListener('change',e=>{state.sort=e.target.value;render();});$('#unreadFilter').addEventListener('click',()=>{state.unreadOnly=!state.unreadOnly;$('#unreadFilter').classList.toggle('active',state.unreadOnly);$('#unreadFilter').setAttribute('aria-pressed',String(state.unreadOnly));render();});$('#clearFilters').addEventListener('click',()=>categoryNav('all'));
    for(const id of ['settingsDesktop','settingsTop','settingsInline','settingsBottom'])$('#'+id).addEventListener('click',openSettings);
    $('#resetPrefs').addEventListener('click',()=>{state.weights={...DEFAULT_WEIGHTS};store('radar:weights',state.weights);drawPrefs();render();toast('優先度を初期設定に戻しました');});
    $('#prefsDialog').addEventListener('close',()=>render());
    $('#weightControls').addEventListener('input',e=>{if(!e.target.matches('input[type="range"]'))return;const cat=e.target.dataset.weight;state.weights[cat]=Number(e.target.value);e.target.closest('.weight-row').querySelector('strong').textContent=weightLabel(state.weights[cat]);store('radar:weights',state.weights);});
  }
  function weightLabel(v){return ({1:'低め',2:'やや低め',3:'標準',4:'高め',5:'最優先'})[v]||'標準';}
  function drawPrefs(){$('#weightControls').innerHTML=Object.entries(DEFAULT_WEIGHTS).map(([cat])=>`<div class="weight-row"><header><label for="weight-${cat}">${ICONS[cat]} ${esc(CATEGORIES[cat][0])}</label><strong>${weightLabel(state.weights[cat])}</strong></header><input id="weight-${cat}" type="range" min="1" max="5" step="1" value="${state.weights[cat]}" data-weight="${cat}" /></div>`).join('');}
  function openSettings(){drawPrefs();const d=$('#prefsDialog');if(!d.open)d.showModal();}
  async function load(){try {const response=await fetch('data/news.json',{cache:'no-store'});if(!response.ok)throw Error(`HTTP ${response.status}`);const data=await response.json();if(!data||!Array.isArray(data.items))throw Error('Invalid data');const unique=new Set();state.items=data.items.filter(i=>i&&i.id&&i.url&&CATEGORIES[i.category]&&!unique.has(i.id)&&unique.add(i.id));state.meta=data;
      const d=data.generated_at ? new Date(data.generated_at):null;$('#updatedAt').textContent=d&&!Number.isNaN(d.getTime())?'最終更新 '+d.toLocaleString('ja-JP',{month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'}):'初期データ';$('#sidebarStatus').textContent=data.mode==='demo'?'プレビュー表示中':'フィード配信中';
      if(data.mode==='live' && d && Date.now()-d.getTime()>48*3600000){showNotice('最新の収集から48時間以上経過しています。古い情報の可能性があるため、原典を確認してください。');}
      if(data.mode==='demo'){showNotice('これは初回プレビューです。リポジトリのGitHub Actionsを実行すると、各情報源から取得した実際の記事に置き換わります。サンプルを最新ニュースとして扱わないでください。');}
      else if((data.errors||[]).length){showNotice(`${data.errors.length}件の情報源で取得エラーが発生。取得できた情報のみ表示しています。エラー詳細はdata/news.jsonに記録されています。`);}
      render();
    }catch(e){showNotice('データを読み込めませんでした。GitHub Pages、または python -m http.server で開いてください。');$('#sidebarStatus').textContent='読み込みエラー';$('#feed').innerHTML='';$('#empty').hidden=false;console.warn('Curiosity Radar:',e);}}
  function showNotice(m){$('#notice').hidden=false;$('#notice').textContent=m;}
  bind();load();
  if('serviceWorker' in navigator){window.addEventListener('load',()=>navigator.serviceWorker.register('sw.js').catch(()=>{}));}
})();
