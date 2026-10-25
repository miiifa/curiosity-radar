"""Reviewed light home hierarchy; first discovery must be above the fold."""
import json, os, threading
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
from browser_smoke import Handler,ROOT,fixture

def run():
    data=fixture();data['items']=[{**data['items'][0],'id':'travel','category':'travel','title':'週末に訪ねる春の小さな旅 — 長い見出しでも原典が分かる公開テスト','source':'公開テストの主催者','reason':'実在のイベントではない配置確認用のデータ。'}]
    server=ThreadingHTTPServer(('127.0.0.1',0),partial(Handler,directory=str(ROOT)));server.feed=(200,json.dumps(data));threading.Thread(target=server.serve_forever,daemon=True).start()
    images=Path('/tmp/curiosity-radar-ui01');images.mkdir(exist_ok=True)
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH','/usr/bin/chromium'),args=['--no-sandbox'])
            for width in (375,430,1280):
                context=browser.new_context(viewport={'width':width,'height':812},service_workers='block')
                page=context.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
                page.goto(f'http://127.0.0.1:{server.server_port}');page.wait_for_selector('.article')
                assert page.locator('html').evaluate('el=>getComputedStyle(el).colorScheme')=='light'
                assert page.locator('.welcome').is_hidden() and page.locator('.metrics').is_hidden()
                source=page.locator('.card-source').bounding_box();assert source['y']+source['height']<812-70,(width,source)
                page.context.set_offline(True)
                expect(page.locator('.feature-label')).to_have_text('前回取得時の注目')
                page.context.set_offline(False)
                page.locator('#search').fill('not-found');expect(page.locator('#empty')).to_be_visible();assert page.locator('.feature-label').count()==0
                page.locator('#clearFilters').click();page.evaluate('scrollTo(0,0)')
                assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
                assert not errors,errors
                page.screenshot(path=str(images/f'home-{width}.png'),full_page=True)
                context.close();print(f'{width}px light home / above-fold source / spotlight states / no images / empty: PASS',flush=True)
            browser.close()
    finally:server.shutdown();server.server_close()
if __name__=='__main__':run()
