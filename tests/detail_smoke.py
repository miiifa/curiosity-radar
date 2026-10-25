import datetime as dt,json,os,threading
from functools import partial
from http.server import ThreadingHTTPServer
from playwright.sync_api import sync_playwright,expect
from browser_smoke import ROOT,Handler,fixture,NOW
def run():
 data=fixture();data['items']=[{**data['items'][0],'id':f'item-{i}','category':['travel','github','security','money'][i%4],
  'title':f'公開テストの物語 {i}','url':f'https://example.com/{i}','published':(NOW-dt.timedelta(hours=i)).isoformat(),
  'summary':'<img src=x onerror=window.__detailInjected=true> 原典の説明。','tags':['原典','旅'],'reason':'公開情報からの検討候補（ルールベース）。'} for i in range(24)]
 data['items'][8]['aliases']=['legacy-item-8']
 data['items'][3].update(source='着想元: fixture/repo',summary='OSS導入支援というアプリの収益化仮説')
 data['items'][2].update(source='CISA KEV',source_kind='official_catalog',published='2026-10-25T00:00:00Z',source_url='https://example.com/catalog',security={'cves':['CVE-2026-12345'],'exploitation_status':'listed_in_kev','user_impact':'not_assessed','kev_added_date':'2026-10-25','vendor':None,'product':None,'required_action':'原典の対応案内を確認'})
 server=ThreadingHTTPServer(('127.0.0.1',0),partial(Handler,directory=str(ROOT)));server.feed=(200,json.dumps(data));threading.Thread(target=server.serve_forever,daemon=True).start();base=f'http://127.0.0.1:{server.server_port}'
 try:
  with sync_playwright() as p:
   browser=p.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH','/usr/bin/chromium'),args=['--no-sandbox'])
   for width in (375,430,1280):
    context=browser.new_context(viewport={'width':width,'height':900},service_workers='block');page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(base);page.wait_for_selector('.article');page.locator('#search').fill('公開テスト');page.locator('#sort').select_option('latest')
    link=page.locator('[data-detail="item-8"]');link.scroll_into_view_if_needed();before=page.evaluate('window.scrollY');link.click()
    expect(page.locator('#detailTitle')).to_have_text('公開テストの物語 8');expect(page.locator('#feedSection')).to_be_hidden()
    assert 'RSS' not in page.locator('.overview-label').inner_text() # No invented acquisition type.
    assert '独自要約ではありません' in page.locator('.overview-label').inner_text()
    save=page.locator('#articleDetail [data-save]');save.click();expect(save).to_have_attribute('aria-pressed','true');expect(save).to_be_focused()
    page.get_by_text('5軸のおすすめ評価',exact=True).click();assert page.locator('.assessment-list dt').count()==5
    assert page.locator('.assessment-list dd').evaluate_all('(nodes)=>nodes.every(el=>el.textContent.includes("未評価"))')
    assert page.locator('#articleDetail img').count()==0 and not page.evaluate('Boolean(window.__detailInjected)')
    page.locator('[data-return]').click();expect(page.locator('#feedSection')).to_be_visible();expect(link).to_be_focused()
    expect(page.locator('#search')).to_have_value('公開テスト');expect(page.locator('#sort')).to_have_value('latest')
    page.wait_for_function('(before)=>Math.abs(window.scrollY-before)<5',arg=before)
    expect(page.locator('[data-save="item-8"]')).to_have_attribute('aria-pressed','true')
    assert page.evaluate('JSON.parse(localStorage.getItem("radar:read")).includes("item-8")')
    page.go_forward();expect(page.locator('#detailTitle')).to_have_text('公開テストの物語 8')
    page.go_back();expect(page.locator('#feedSection')).to_be_visible()
    page.goto(base+'/#article/item-2');expect(page.locator('#detailTitle')).to_have_text('公開テストの物語 2')
    assert '影響' in page.locator('#articleDetail').inner_text()
    assert 'CVE-2026-12345' in page.locator('#articleDetail').inner_text()
    assert '攻撃日・公表日ではありません' in page.locator('#articleDetail').inner_text()
    page.goto(base+'/#article/legacy-item-8');expect(page.locator('#detailTitle')).to_have_text('公開テストの物語 8')
    page.locator('#settingsTop').click();page.keyboard.press('Escape');expect(page.locator('#detailTitle')).to_have_text('公開テストの物語 8')
    page.goto(base+'/#article/item-3');expect(page.locator('.overview-label')).to_contain_text('アプリがルールベース');assert '作者の発言ではなく' in page.locator('#articleDetail').inner_text()
    page.goto(base+'/#article/%3Cimg%3E');expect(page.locator('#detailTitle')).to_have_text('記事が見つかりません');page.locator('[data-return]').click();expect(page.locator('#feedSection')).to_be_visible()
    assert not page.evaluate('document.documentElement.scrollWidth>innerWidth');assert not errors,errors
    page.goto(base+'/#article/item-8');page.wait_for_selector('#detailTitle');page.screenshot(path=f'/tmp/detail-{width}.png',full_page=True)
    context.close();print(f'{width}px detail / five axes / unknowns / injection / save / return filters and scroll / direct links: PASS',flush=True)
   browser.close()
 finally:server.shutdown();server.server_close()
if __name__=='__main__':run()
