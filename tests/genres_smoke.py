import json,os,threading
from functools import partial
from http.server import ThreadingHTTPServer
from playwright.sync_api import sync_playwright,expect
from browser_smoke import ROOT,Handler,fixture
def run():
 data=fixture();data['items']=[{**data['items'][0],'id':cat,'category':cat,'title':'公開テスト '+cat,'url':'https://example.com/'+cat} for cat in ('github','ai','travel','money','security','social','hobby')]
 server=ThreadingHTTPServer(('127.0.0.1',0),partial(Handler,directory=str(ROOT)));server.feed=(200,json.dumps(data));threading.Thread(target=server.serve_forever,daemon=True).start()
 try:
  with sync_playwright() as p:
   browser=p.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH','/usr/bin/chromium'),args=['--no-sandbox'])
   for width in (375,430,1280):
    context=browser.new_context(viewport={'width':width,'height':900},service_workers='block');page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(f'http://127.0.0.1:{server.server_port}');page.wait_for_selector('.article')
    def nav(key):
     (page.locator(f'#mobileChips [data-chip="{key}"]') if width<1000 else page.locator(f'#desktopNav [data-category="{key}"]')).click()
    for genre,count in [('travel',1),('technology',2),('security',1),('trends',2),('money',1),('deals',0)]:
     nav(genre);assert page.locator('.article').count()==count
    expect(page.locator('#empty')).to_contain_text('収集元は未接続')
    nav('technology');page.locator('#sourceFilters [data-chip="github"]').click();assert page.locator('.article').count()==1
    expect(page.locator('#mobileChips [data-chip="technology"]')).to_have_attribute('aria-pressed','true')
    parent=page.locator('#sourceFilters [data-chip="technology"]');parent.focus();page.keyboard.press('Enter');expect(parent).to_be_focused()
    nav('trends');page.locator('#sourceFilters [data-chip="hobby"]').click();assert page.locator('.article').first.get_attribute('data-id')=='hobby'
    page.locator('[data-save]').click();page.reload();page.wait_for_selector('.article');assert page.locator('#metricSaved').inner_text()=='1'
    assert not page.evaluate('document.documentElement.scrollWidth>innerWidth');assert not errors,errors
    context.close();print(f'{width}px six genres / unconnected deals / legacy subfilters / save reload: PASS',flush=True)
   browser.close()
 finally:server.shutdown();server.server_close()
if __name__=='__main__':run()
