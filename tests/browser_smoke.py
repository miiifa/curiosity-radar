"""Optional browser smoke test: requires Playwright and a local Chromium executable.
Run: python tests/browser_smoke.py
No external requests; a temporary local server supplies public synthetic fixtures.
"""
import datetime as dt
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import threading
import sys

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
NOW = dt.datetime.now(dt.timezone.utc)
sys.path.insert(0,str(ROOT / 'scripts'))
from collect import deduplicate, related_headlines, validate_snapshot


def fixture():
    return {'mode': 'live', 'generated_at': NOW.isoformat(), 'errors': [], 'items': [
        {'id': 'security-fixture', 'category': 'security', 'title': '公開テスト用のお知らせ',
         'source': '公開テスト用の情報源', 'url': 'https://example.com/article', 'score': 50,
         'published': None, 'summary': '実ニュースではないテスト用データです。', 'tags': []}]}


class Handler(SimpleHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def do_GET(self):
        if self.path.split('?')[0] == '/data/news.json':
            status, payload = self.server.feed
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(payload.encode())
        else:
            super().do_GET()


def run():
    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(Handler, directory=str(ROOT)))
    server.feed = (200, json.dumps(fixture()))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{server.server_port}'
    screenshot_dir = Path('/tmp/curiosity-radar-pr01')
    screenshot_dir.mkdir(exist_ok=True)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH', '/usr/bin/chromium'), args=['--no-sandbox'])
            cases = [('live', fixture(), ['ライブデータ'])]
            partial_feed = fixture()
            partial_feed['errors'] = ['RSS Fixture: TimeoutError']
            partial_feed['generated_at'] = (NOW-dt.timedelta(hours=49)).isoformat()
            cases.append(('stale-partial', partial_feed, ['48時間以上未更新', '一部取得失敗']))
            dated = fixture()
            dated['items'][0]['published'] = '2026-10-24T12:00:00Z'
            dated['items'][0]['source'] = 'CISA KEV'
            cases.append(('dated-kev', dated, ['ライブデータ']))
            demo = fixture()
            demo['mode'] = 'demo'
            demo['items'][0]['demo'] = True
            cases.append(('demo', demo, ['プレビュー']))
            cases.extend([
                ('broken-json', '{bad', ['読み込みエラー']),
                ('invalid-mode', {**fixture(), 'mode': 'unknown'}, ['読み込みエラー']),
                ('invalid-date', {**fixture(), 'generated_at': 'invalid'}, ['読み込みエラー']),
                ('empty-feed', {**fixture(), 'items': []}, ['読み込みエラー']),
            ])
            for width in (400, 1440):
                for name, data, labels in cases:
                    server.feed = (200, data if isinstance(data, str) else json.dumps(data))
                    context = browser.new_context(viewport={'width': width, 'height': 900}, service_workers='block', locale='ja-JP', timezone_id='Asia/Tokyo')
                    page = context.new_page()
                    errors = []
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    page.goto(base)
                    page.wait_for_function("!document.querySelector('#sidebarStatus').textContent.includes('確認中')")
                    for label in labels:
                        assert label in page.locator('#sidebarStatus').inner_text(), (width, name, label)
                    if '読み込みエラー' in labels:
                        assert page.locator('.article').count() == 0
                        assert page.locator('#notice').is_visible()
                        assert not page.locator('#empty').is_visible()
                    else:
                        assert page.locator('.article').count() == 1
                        assert page.locator('.source').inner_text() == data['items'][0]['source']
                        if name == 'stale-partial':
                            notice = page.locator('#notice').inner_text()
                            assert '48時間以上' in notice and '取得エラー' in notice
                        if name == 'live':
                            assert not page.locator('#notice').is_visible()
                            assert '掲載日時不明' in page.locator('.card-time').inner_text()
                            page.locator('[data-save]').click()
                            page.reload();page.wait_for_selector('[data-save]')
                            assert page.locator('#metricSaved').inner_text() == '1'
                        if name == 'dated-kev':
                            assert page.locator('time').get_attribute('datetime') == '2026-10-24'  # Catalog calendar date, not an event timestamp.
                            assert 'KEV追加' in page.locator('time').inner_text()
                            assert '2026/10/24' in page.locator('time').inner_text()
                        if name == 'demo':
                            assert 'デモ作成日時' in page.locator('#updatedAt').inner_text()
                            assert 'デモデータ' in page.locator('#notice').inner_text()
                    assert not page.evaluate('document.documentElement.scrollWidth > innerWidth'), (width, name)
                    assert page.locator('#updatedAt').evaluate('(el) => el.scrollWidth <= el.clientWidth'), (width, name, 'timestamp clipped')
                    assert not errors, errors
                    if name == 'stale-partial':
                        page.screenshot(path=str(screenshot_dir / f'{name}-{width}.png'), full_page=True)
                    print(f'{width}px {name}: PASS', flush=True)
                    context.close()
            # Actual cards: recommendations mix GitHub pools; explicit sorting stays literal.
            github_feed = fixture()
            github_feed['items'] = []
            for name, group, stars, score, delta in [('small','small',120,60,0),('rising','rising',200,80,40),('large','established',20000,99,-3)]:
                github_feed['items'].append({**fixture()['items'][0], 'id': name, 'title':'fixture/'+name,
                    'category':'github', 'url':'https://github.com/fixture/'+name, 'source':'GitHub Search API',
                    'stars':stars, 'score':score, 'license':None, 'discovery_group':group,
                    'stars_observed_at':NOW.isoformat(), 'star_delta_since':(NOW-dt.timedelta(hours=48)).isoformat(),
                    'star_delta':delta, 'star_delta_per_day':delta/2, 'star_growth_percent_per_day':10})
            for width in (400,1440):
                server.feed = (200,json.dumps(github_feed))
                context = browser.new_context(viewport={'width':width,'height':900}, service_workers='block')
                page = context.new_page(); page.goto(base); page.wait_for_selector('.article')
                ids = page.locator('.article').evaluate_all('(els)=>els.map(el=>el.dataset.id)')
                assert ids == ['small','rising','large'], ids
                for panel in page.locator('.card-analysis>summary').all():panel.click()
                for text in ['小規模OSS候補','急上昇候補','定番候補','ライセンス未確認','スター差 0','スター差 -3','約48時間の観測差']:
                    assert text in page.locator('#feed').inner_text(), text
                assert not page.evaluate('document.documentElement.scrollWidth > innerWidth')
                context.grant_permissions(['clipboard-read','clipboard-write'])
                page.locator('[data-prompt]').first.click()
                prompt = page.evaluate('navigator.clipboard.readText()')
                assert 'https://github.com/fixture/small' in prompt
                assert '第三者コード・インストーラーを実行しない' in prompt
                assert '非信頼の公開メタデータ' in prompt
                page.locator('#sort').select_option('popular')
                assert page.locator('.article').first.get_attribute('data-id') == 'large'
                page.locator('#sort').select_option('recommended')
                assert page.locator('.article').first.get_attribute('data-id') == 'small'
                page.locator('#search').fill('fixture/rising')
                assert page.locator('.article').count() == 1
                page.locator('[data-save]').click();page.reload();page.wait_for_selector('.article')
                assert page.locator('#metricSaved').inner_text() == '1'
                page.screenshot(path=str(screenshot_dir / f'github-discovery-{width}.png'),full_page=True)
                context.close()
                print(f'{width}px GitHub pools / observation / explicit sorting / search / saved persistence: PASS',flush=True)
            # Old v1 feeds must not invent observation periods for legacy deltas.
            legacy = fixture()
            legacy['items'][0].update(category='github',stars=120,star_delta=99)
            server.feed = (200,json.dumps(legacy))
            context=browser.new_context(service_workers='block')
            page=context.new_page();page.goto(base);page.wait_for_selector('.article')
            page.locator('.card-analysis>summary').click()
            assert 'スター比較未確認' in page.locator('.repo-stats').inner_text()
            assert '+99' not in page.locator('.repo-stats').inner_text()
            context.close()
            print('Legacy star difference without observation period: PASS',flush=True)
            # End-to-end collector metadata -> category/search/ranking/saved/read UI.
            base_item={**fixture()['items'][0], 'id':'primary', 'category':'ai', 'score':90,
                'url':'https://example.com/article?utm_source=fixture', 'title':'ＡＩ Pythonの新しい公開モデルを確認する',
                'published':NOW.isoformat(), 'tags':['Python','</span><img src=x onerror=window.__newsInjected=true>']}
            raw=[base_item,{**base_item,'id':'legacy-saved','category':'security','score':70,'source':'別の掲載元','url':'https://example.com/article'},
                 {**base_item,'id':'similar','category':'travel','score':60,'source':'別の記事候補','url':'https://other.example/story'},
                 {**fixture()['items'][0],'id':'unread-security','score':0,'url':'https://example.com/security-unread'},
                 {**base_item,'id':'rank-ai','score':70,'title':'Rankcase AI','url':'https://example.com/rank-ai','tags':[]},
                 {**base_item,'id':'rank-travel','category':'travel','score':80,'title':'Rankcase Travel','url':'https://example.com/rank-travel','tags':[]}]
            raw += [{**base_item,'id':f'dominant-{n}','title':f'AI candidate {n}','score':99,'url':f'https://example.com/dominant/{n}','tags':[]} for n in range(8)]
            dedup_feed={**fixture(),'items':related_headlines(deduplicate(raw))}
            validate_snapshot(dedup_feed)
            for width in (360,390,430,1280):
                server.feed=(200,json.dumps(dedup_feed))
                context=browser.new_context(viewport={'width':width,'height':900},service_workers='block')
                context.add_init_script("""if(!localStorage.getItem('fixture-initialized')){
                  localStorage.setItem('radar:saved',JSON.stringify(['legacy-saved','expired']));
                  localStorage.setItem('radar:read',JSON.stringify(['legacy-saved']));
                  localStorage.setItem('radar:weights',JSON.stringify({ai:5,travel:1}));
                  localStorage.setItem('fixture-initialized','yes');} """)
                page=context.new_page();errors=[]
                page.on('pageerror',lambda error:errors.append(str(error)))
                page.goto(base);page.wait_for_selector('.article')
                assert page.locator('.article').count()==len(raw)-1
                assert page.evaluate("JSON.parse(localStorage.getItem('radar:saved'))")==['primary','expired']
                assert page.evaluate("JSON.parse(localStorage.getItem('radar:read'))")==['primary']
                assert page.locator('#metricSaved').inner_text()=='2'
                primary=page.locator('.article[data-id="primary"]')
                assert 'utm_source=fixture' in primary.locator('h3 a').get_attribute('href')
                assert primary.locator('.article-references').count()==2
                assert not page.evaluate('Boolean(window.__newsInjected)')
                assert page.locator('#feed img').count()==0
                first_ids=page.locator('.article').evaluate_all('(els)=>els.slice(0,6).map(el=>el.dataset.id)')
                categories={item['id']:item['category'] for item in dedup_feed['items']}
                assert len({categories[id] for id in first_ids})>=2
                mobile=page.locator('[data-chip="security"]')
                (mobile if mobile.is_visible() else page.locator('#desktopNav [data-category="security"]')).click()
                assert page.locator('.article').count()==2
                assert 'セキュリティ' in primary.locator('.category-pill').inner_text()
                page.locator('#unreadFilter').click()
                assert page.locator('.article').count()==1
                assert page.locator('.article').first.get_attribute('data-id')=='unread-security'
                page.locator('.article .card-analysis>summary').click()
                assert '0/100' in page.locator('.article .rank').inner_text()
                page.locator('#sort').select_option('popular')
                page.locator('#search').fill('ｐｙｔｈｏｎ')
                assert page.locator('#empty').is_visible()
                page.locator('#clearFilters').click()
                assert page.locator('#sort').input_value()=='popular'
                assert page.locator('#search').input_value()==''
                assert page.locator('#unreadFilter').get_attribute('aria-pressed')=='false'
                page.locator('#sort').select_option('recommended')
                page.locator('#search').fill('rankcase')
                assert page.locator('.article').first.get_attribute('data-id')=='rank-ai'
                page.locator('#settingsTop').click()
                page.locator('[data-weight="ai"]').press('Home')
                expect(page.locator('[data-weight="ai"]')).to_have_value('1')
                page.locator('[data-weight="travel"]').press('End')
                expect(page.locator('[data-weight="travel"]')).to_have_value('5')
                page.wait_for_function("JSON.parse(localStorage.getItem('radar:weights')).ai===1 && JSON.parse(localStorage.getItem('radar:weights')).travel===5")
                page.locator('#prefsDialog button[type="submit"]').click()
                expect(page.locator('.article').first).to_have_attribute('data-id','rank-travel')
                page.reload();page.wait_for_selector('.article');page.locator('#search').fill('rankcase')
                expect(page.locator('.article').first).to_have_attribute('data-id','rank-travel')
                page.locator('#search').fill('')
                mobile_saved=page.locator('[data-mobile-go="saved"]')
                (mobile_saved if mobile_saved.is_visible() else page.locator('#savedNav')).click()
                assert page.locator('.article').count()==1
                assert page.locator('.article').first.get_attribute('data-id')=='primary'
                assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
                assert not errors,errors
                page.screenshot(path=str(screenshot_dir/f'dedup-search-{width}.png'),full_page=True)
                context.close()
                print(f'{width}px canonical dedup / related / categories / saved-read migration / filters / weights / injection: PASS',flush=True)
            # Source status and catalog date semantics, with a negative UTC offset too.
            quality={**fixture(),'errors':['RSS Fixture: HTTP429'],'items':[
                {**fixture()['items'][0],'id':'kev','source':'CISA KEV','source_kind':'official_catalog',
                 'source_url':'https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json',
                 'published':'2026-10-24T00:00:00Z','security':{'cves':['CVE-2026-12345'],'exploitation_status':'listed_in_kev',
                    'user_impact':'not_assessed','kev_added_date':'2026-10-24','vendor':None,'product':None,
                    'required_action':'<img src=x onerror=window.__qualityInjected=true> Read the advisory.'}},
                {**fixture()['items'][0],'id':'travel','category':'travel','source':'関東発ドライブ','source_kind':'search_feed',
                 'source_url':'https://news.google.com/rss/search?q=travel','url':'https://example.com/travel',
                 'title':'沖縄の春旅、無料イベントの例','tags':['関東','ドライブ']}],
                 'source_health':[{'id':'rss-fixture','name':'公開テスト用の取得元','url':'https://example.com/feed',
                    'status':'failed','error':'HTTP429','count':0,'checked_at':NOW.isoformat(),'last_success_at':None,
                    'consecutive_failures':2,'history_available':True}]}
            validate_snapshot(quality)
            for width in (400,1440):
                for zone in ('Asia/Tokyo','America/Los_Angeles'):
                    server.feed=(200,json.dumps(quality))
                    context=browser.new_context(viewport={'width':width,'height':900},service_workers='block',timezone_id=zone)
                    page=context.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
                    page.goto(base);page.wait_for_selector('.article')
                    for panel in page.locator('.card-analysis>summary').all():panel.click()
                    kev=page.locator('[data-id="kev"]')
                    assert '2026/10/24' in kev.locator('time').inner_text(),zone
                    assert kev.locator('time').get_attribute('datetime')=='2026-10-24'
                    assert '攻撃日・公表日ではありません' in kev.inner_text()
                    assert 'この端末への影響は未確認' in kev.inner_text()
                    assert '製品未確認' in kev.inner_text()
                    assert 'CVE-2026-12345' in kev.inner_text()
                    travel=page.locator('[data-id="travel"]')
                    assert '検索結果のRSS' in travel.inner_text()
                    assert '検索条件:関東' in travel.inner_text()
                    assert '地域・見頃・料金・営業時間・営業状況は原典で確認' in travel.inner_text()
                    page.locator('#sourceHealth summary').click()
                    health=page.locator('#sourceHealthRows').inner_text()
                    assert '連続取得エラー 2回' in health
                    assert '最終成功 未確認' in health
                    assert '取得回数が制限されています' in health
                    assert not page.evaluate('Boolean(window.__qualityInjected)')
                    assert page.locator('#feed img').count()==0
                    assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
                    assert not errors,errors
                    page.screenshot(path=str(screenshot_dir/f'source-quality-{width}-{zone.replace("/","-")}.png'),full_page=True)
                    context.close()
                    print(f'{width}px {zone} source health / KEV calendar date / unknown impact / travel provenance: PASS',flush=True)
            # PR-05: preview selected public information and copy only on an explicit click.
            action_feed = fixture()
            action_feed['items'] = [
                {**fixture()['items'][0], 'id': category+'-action', 'category': category,
                 'title': category+'公開テスト </pre><img src=x onerror="window.__actionInjected=true">',
                 'summary': 'NONTRUSTED_'+category, 'url': 'https://example.com/'+category}
                for category in ('github','money','travel')]
            for width in (360,390,430,1280):
                for reject in (False,True):
                    server.feed = (200,json.dumps(action_feed))
                    context = browser.new_context(viewport={'width':width,'height':900}, service_workers='block')
                    context.add_init_script('''
                        window.__copies=[];
                        localStorage.setItem('radar:test-private','PRIVATE_STORAGE_MARKER');
                        Object.defineProperty(navigator,'clipboard',{value:{writeText:async text=>{
                            window.__copies.push(text);
                            if (REJECT_COPY) throw new Error('denied');
                        }}});
                    '''.replace('REJECT_COPY',str(reject).lower()))
                    page=context.new_page();errors=[];external=[]
                    page.on('pageerror',lambda error:errors.append(str(error)))
                    page.on('request',lambda request:external.append(request.url) if not request.url.startswith(base) else None)
                    page.goto(base);page.wait_for_selector('[data-prompt]')
                    assert page.evaluate('window.__copies.length')==0
                    page.locator('[data-id="money-action"] .card-analysis>summary').click()
                    assert '収益性未検証' in page.locator('[data-id="money-action"] .hypothesis-note').inner_text()
                    assert page.locator('[data-id="money-action"] .hypothesis-note a').get_attribute('href')=='https://example.com/money'
                    for category,label in [('github','30分で試す／作る'),('money','仮説を検証する'),('travel','旅行を計画する')]:
                        article=page.locator(f'[data-id="{category}-action"]')
                        preview=article.locator('.next-action')
                        assert label in preview.locator('summary').inner_text()
                        preview.locator('summary').click()
                        assert preview.locator('pre').is_visible()
                        expected=preview.locator('pre').inner_text()
                        assert 'NONTRUSTED_'+category in expected
                        for other in ('github','money','travel'):
                            if other!=category:assert 'NONTRUSTED_'+other not in expected
                        assert 'PRIVATE_STORAGE_MARKER' not in expected
                        assert page.evaluate('window.__copies.length')==('github','money','travel').index(category)
                        article.locator('[data-prompt]').click()
                        page.wait_for_function('document.querySelector("#toast").classList.contains("show")')
                        assert page.evaluate('window.__copies.at(-1)')==expected
                        message=page.locator('#toast').inner_text()
                        assert ('コピーできませんでした' if reject else '指示をコピーしました') in message
                        assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
                        preview.locator('summary').click()
                    assert not page.evaluate('Boolean(window.__actionInjected)')
                    assert page.locator('#feed img').count()==0
                    assert not errors,errors
                    assert not external,external
                    if not reject:
                        page.locator('[data-id="travel-action"] summary').click()
                        page.locator('[data-id="travel-action"]').screenshot(path=str(screenshot_dir/f'next-action-{width}.png'))
                    context.close()
                    print(f'{width}px next actions preview / selected data / copy {"denied" if reject else "success"}: PASS',flush=True)
            # Real service worker, real Cache Storage, real browser offline mode.
            server.feed = (200, json.dumps(partial_feed))
            context = browser.new_context(viewport={'width':400,'height':900})
            page = context.new_page()
            page.goto(base);page.wait_for_selector('.article')
            page.evaluate('navigator.serviceWorker.ready')
            page.wait_for_function('navigator.serviceWorker.controller !== null')
            page.reload();page.wait_for_selector('.article')
            timestamp = page.locator('#updatedAt').inner_text()
            context.set_offline(True)
            page.reload();page.wait_for_selector('.article')
            status = page.locator('#sidebarStatus').inner_text()
            for label in ['キャッシュ','オフライン','48時間以上未更新','一部取得失敗']:
                assert label in status, (label, status)
            assert page.locator('#updatedAt').inner_text() == timestamp
            context.set_offline(False)
            server.feed = (200, '{broken')
            page.reload();page.wait_for_function("document.querySelector('#sidebarStatus').textContent === '読み込みエラー'")
            context.set_offline(True)
            page.reload();page.wait_for_selector('.article')
            assert page.locator('#updatedAt').inner_text() == timestamp
            assert 'キャッシュ' in page.locator('#sidebarStatus').inner_text()
            context.close()
            print('Real service worker: offline/stale/partial + invalid JSON preserves good cache: PASS', flush=True)
            # HTTP error + no existing cache must be an error, not an empty successful feed.
            server.feed = (404, '{}')
            context = browser.new_context(service_workers='block')
            page = context.new_page();page.goto(base)
            page.wait_for_function("document.querySelector('#sidebarStatus').textContent === '読み込みエラー'")
            assert page.locator('.article').count() == 0
            context.close()
            print('HTTP 404 without cache: PASS', flush=True)
            browser.close()
    finally:
        server.shutdown()
        server.server_close()


if __name__ == '__main__':
    run()
