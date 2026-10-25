import json,os,threading
from functools import partial
from http.server import ThreadingHTTPServer
from playwright.sync_api import sync_playwright,expect
from browser_smoke import ROOT,Handler,fixture
def run():
 data=fixture();data['items']=[{**data['items'][0],'id':'selected','category':'travel','title':'公開の旅記事','summary':'<img src=x onerror=window.__handoffInjected=true> 取得元の説明','tags':['旅行']},
  {**data['items'][0],'id':'other','title':'OTHER_ARTICLE_MARKER','summary':'OTHER_ARTICLE_MARKER'}]
 server=ThreadingHTTPServer(('127.0.0.1',0),partial(Handler,directory=str(ROOT)));server.feed=(200,json.dumps(data));threading.Thread(target=server.serve_forever,daemon=True).start();base=f'http://127.0.0.1:{server.server_port}'
 try:
  with sync_playwright() as p:
   browser=p.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH','/usr/bin/chromium'),args=['--no-sandbox'])
   for width in (375,430,1280):
    for mode in ('success','denied','deferred'):
     context=browser.new_context(viewport={'width':width,'height':900},service_workers='block')
     context.add_init_script('''window.__mode=MODE;window.__copies=[];localStorage.setItem('radar:private','PRIVATE_MARKER');Object.defineProperty(navigator,'clipboard',{value:{writeText:async text=>{window.__copies.push(text);if(window.__mode==='denied')throw Error('PRIVATE_ERROR_MARKER');if(window.__mode==='deferred')await new Promise(resolve=>window.__releaseCopy=resolve);}}});'''.replace('MODE',json.dumps(mode)))
     opened=[]
     context.route('https://chatgpt.com/**',lambda route:(opened.append((route.request.url,route.request.method,route.request.post_data)),route.fulfill(content_type='text/html',body='<title>ChatGPT destination fixture</title>'))[-1])
     page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
     page.goto(base+'/#article/selected');page.wait_for_selector('#detailTitle');page.locator('[data-discuss]').click()
     expect(page.locator('#discussionDialog')).to_be_visible();text=page.locator('#discussionText').input_value();assert len(text)<=2000
     assert 'PRIVATE_MARKER' not in text and 'OTHER_ARTICLE_MARKER' not in text
     assert page.evaluate('window.__copies.at(-1)')==text
     assert len(context.pages)==1 and not opened
     if mode=='denied':
      expect(page.locator('#discussionStatus')).to_contain_text('手動でコピー');expect(page.locator('#discussionText')).to_be_focused()
      assert page.locator('#discussionText').evaluate('el=>el.selectionStart===0&&el.selectionEnd===el.value.length')
      assert 'PRIVATE_ERROR_MARKER' not in page.locator('#discussionStatus').inner_text()
      page.evaluate('window.__mode="success"');page.locator('#copyDiscussion').click()
     elif mode=='deferred':
      assert 'コピーしました' not in page.locator('#discussionStatus').inner_text()
      page.keyboard.press('Escape');page.evaluate('window.__releaseCopy()');expect(page.locator('#discussionDialog')).to_be_hidden()
      assert 'コピーしました' not in page.locator('#discussionStatus').inner_text()
      page.evaluate('window.__mode="success"');page.locator('[data-discuss]').click()
     expect(page.locator('#discussionStatus')).to_contain_text('コピーしました')
     if mode=='success':page.screenshot(path=f'/tmp/chatgpt-context-{width}.png')
     with page.expect_popup() as popup:page.locator('.chatgpt-link').click()
     destination=popup.value;destination.wait_for_load_state();assert destination.url=='https://chatgpt.com/';destination.close()
     assert opened==[('https://chatgpt.com/','GET',None)],opened
     page.locator('.chatgpt-link').focus();page.keyboard.press('Tab');assert page.evaluate('document.activeElement.closest("#discussionDialog")!==null')
     page.keyboard.press('Escape');expect(page.locator('[data-discuss]')).to_be_focused()
     if mode=='success':page.screenshot(path=f'/tmp/detail-handoff-{width}.png',full_page=True)
     assert page.locator('#articleDetail img').count()==0 and not page.evaluate('Boolean(window.__handoffInjected)')
     assert not page.evaluate('document.documentElement.scrollWidth>innerWidth');assert not errors,errors
     context.close();print(f'{width}px {mode} handoff / selected public data / confirmed copy / manual fallback / explicit open / focus: PASS',flush=True)
   longdata={**data,'items':[{**data['items'][0],'url':'https://example.com/'+'x'*4000}]};server.feed=(200,json.dumps(longdata))
   context=browser.new_context(service_workers='block');page=context.new_page();page.goto(base+'/#article/selected');page.wait_for_selector('[data-discuss]');page.locator('[data-discuss]').click()
   expect(page.locator('#copyDiscussion')).to_be_disabled();assert page.locator('#discussionText').input_value()=='';expect(page.locator('#discussionStatus')).to_contain_text('長すぎる')
   context.close();print('Oversized citation keeps original link and disables incomplete context copy: PASS',flush=True)
   server.feed=(200,json.dumps({**data,'mode':'demo','items':[{**data['items'][0],'demo':True}]}))
   context=browser.new_context(service_workers='block');context.add_init_script("Object.defineProperty(navigator,'clipboard',{value:{writeText:async()=>{}}});")
   page=context.new_page();page.goto(base+'/#article/selected');page.wait_for_selector('[data-discuss]');page.locator('[data-discuss]').click()
   expect(page.locator('#discussionStatus')).to_contain_text('コピーしました');assert 'これはデモデータです' in page.locator('#discussionText').input_value()
   context.close();print('Demo handoff retains fictional-data warning in the actual copied view: PASS',flush=True)
   browser.close()
 finally:server.shutdown();server.server_close()
if __name__=='__main__':run()
