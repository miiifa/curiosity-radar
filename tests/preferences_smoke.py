"""Local JSON download/upload, preview, merge, cancellation and storage faults."""
import json
import os
import threading
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import sync_playwright, expect
from browser_smoke import Handler, ROOT, fixture


def run():
    weights=dict(github=1,ai=5,money=5,security=4,travel=5,social=3,hobby=4)
    initial={'format':'curiosity-radar-preferences','version':1,'weights':weights,'bookmarks':['existing-id']}
    hostile='<img/src=x/onerror=window.__importInjected=true>'
    incoming={**initial,'weights':{**weights,'github':5,'travel':1},'bookmarks':['legacy-incoming','unknown-id',hostile]}
    data=fixture()
    data['items']=[{**data['items'][0],'id':id,'category':category,'title':'Public fixture '+id,
                    'url':'https://example.com/'+id,**({'aliases':['legacy-incoming']} if category=='travel' else {})}
                   for id,category in [('existing-id','github'),('incoming-known','travel')]]
    server=ThreadingHTTPServer(('127.0.0.1',0),partial(Handler,directory=str(ROOT)))
    server.feed=(200,json.dumps(data));threading.Thread(target=server.serve_forever,daemon=True).start()
    base=f'http://127.0.0.1:{server.server_port}'
    screenshots=Path('/tmp/curiosity-radar-pr08a');screenshots.mkdir(exist_ok=True)
    def upload(value):
        return {'name':'private-test-name.json','mimeType':'application/json','buffer':(value if isinstance(value,str) else json.dumps(value)).encode()}
    def stored(page):
        return page.evaluate('({weights:localStorage.getItem("radar:weights"),saved:localStorage.getItem("radar:saved"),read:localStorage.getItem("radar:read")})')
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH','/usr/bin/chromium'),args=['--no-sandbox'])
            for width in (360,390,430,1280):
                context=browser.new_context(viewport={'width':width,'height':900},service_workers='block')
                context.add_init_script('''if(!localStorage.getItem('initialized')){
                    localStorage.setItem('radar:weights',JSON.stringify(WEIGHTS));
                    localStorage.setItem('radar:saved','["existing-id"]');localStorage.setItem('radar:read','["existing-id"]');
                    localStorage.setItem('radar:unrelated','PRIVATE_LOCAL_MARKER');localStorage.setItem('initialized','yes');
                }'''.replace('WEIGHTS',json.dumps(weights)))
                page=context.new_page();errors=[];external=[]
                page.on('pageerror',lambda error:errors.append(str(error)))
                page.on('request',lambda request:external.append(request.url) if not request.url.startswith(base) and not request.url.startswith('blob:') else None)
                page.goto(base);page.wait_for_selector('.article');page.locator('#settingsTop').click()
                before=stored(page)
                with page.expect_download() as downloaded:page.locator('#exportPrefs').click()
                download=downloaded.value
                assert download.suggested_filename=='curiosity-radar-settings-v1.json'
                text=Path(download.path()).read_text();assert json.loads(text)==initial
                assert 'PRIVATE_LOCAL_MARKER' not in text and 'Public fixture' not in text and 'radar:read' not in text
                with page.expect_file_chooser() as selected:page.locator('#importPrefs').click()
                selected.value.set_files(upload(incoming))
                expect(page.locator('#importPreview')).to_be_visible()
                assert '保存ID 3件（現在の記事に一致 1件）' in page.locator('#importSummary').inner_text()
                assert stored(page)==before
                page.locator('#cancelImport').click();expect(page.locator('#importPrefs')).to_be_focused()
                assert stored(page)==before
                # Same file can be selected again, but nothing changes until Apply.
                page.locator('#prefsFile').set_input_files(upload(incoming));expect(page.locator('#importPreview')).to_be_visible()
                expect(page.locator('#applyPrefs')).to_be_focused();page.keyboard.press('Enter')
                expect(page.locator('#importPreview')).to_be_hidden();expect(page.locator('#importPrefs')).to_be_focused()
                after=stored(page)
                assert json.loads(after['weights'])==incoming['weights']
                assert json.loads(after['saved'])==['existing-id','incoming-known','unknown-id',hostile]
                assert after['read']==before['read']
                assert page.locator('#metricSaved').inner_text()=='4'
                assert page.locator('img').count()==0 and not page.evaluate('Boolean(window.__importInjected)')
                assert 'private-test-name' not in page.locator('body').inner_text()
                page.keyboard.press('Escape');page.reload();page.wait_for_selector('.article');page.locator('#settingsTop').click()
                expect(page.locator('[data-weight="github"]')).to_have_value('5')
                expect(page.locator('[data-save="existing-id"]')).to_have_attribute('aria-pressed','true')
                expect(page.locator('[data-save="incoming-known"]')).to_have_attribute('aria-pressed','true')
                assert stored(page)==after
                invalids=['{broken', {**initial,'version':2}, {**initial,'token':'PRIVATE_FILE_MARKER'},
                          {**initial,'weights':{**weights,'github':'5'}},'x'*(1024*1024+1),
                          {**initial,'bookmarks':['id']*5001}]
                for value in invalids:
                    page.locator('#prefsFile').set_input_files(upload(value))
                    expect(page.locator('#transferStatus')).to_contain_text('読み込めませんでした')
                    expect(page.locator('#importPreview')).to_be_hidden();assert stored(page)==after
                    assert 'PRIVATE_FILE_MARKER' not in page.locator('body').inner_text()
                # Closing while a file read is pending must invalidate that read.
                page.evaluate('''window.__originalText=File.prototype.text;File.prototype.text=function(){return new Promise(resolve=>{window.__releaseFile=()=>resolve(PAYLOAD);});};true;'''.replace('PAYLOAD',json.dumps(json.dumps(initial))))
                page.locator('#prefsFile').set_input_files(upload(initial));page.wait_for_function('typeof window.__releaseFile==="function"')
                page.keyboard.press('Escape');page.locator('#settingsTop').click()
                page.evaluate('async()=>{window.__releaseFile();await new Promise(requestAnimationFrame);File.prototype.text=window.__originalText;}')
                expect(page.locator('#importPreview')).to_be_hidden();assert stored(page)==after
                # A quota error on the second write rolls the first one back.
                page.evaluate('''window.__originalSet=Storage.prototype.setItem;window.__rejectOnce=true;
                    Storage.prototype.setItem=function(key,value){if(key==='radar:saved'&&window.__rejectOnce){window.__rejectOnce=false;throw new Error('quota');}return window.__originalSet.call(this,key,value);};true;''')
                page.locator('#prefsFile').set_input_files(upload(initial));expect(page.locator('#importPreview')).to_be_visible()
                page.locator('#applyPrefs').click();expect(page.locator('#transferStatus')).to_contain_text('保存できませんでした')
                assert stored(page)==after;expect(page.locator('[data-weight="github"]')).to_have_value('5')
                page.locator('#applyPrefs').click();expect(page.locator('#transferStatus')).to_contain_text('適用しました')
                assert json.loads(stored(page)['weights'])==weights
                assert stored(page)['saved']==after['saved'] and stored(page)['read']==after['read']
                page.locator('#prefsFile').set_input_files(upload(incoming));expect(page.locator('#importPreview')).to_be_visible()
                assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
                assert page.locator('#prefsDialog').evaluate('el=>el.scrollWidth<=el.clientWidth')
                page.locator('#importPreview').screenshot(path=str(screenshots/f'preview-{width}.png'))
                # If rollback itself is blocked, expose the partial-failure state.
                page.evaluate('''window.__writes=0;Storage.prototype.setItem=function(key,value){if(++window.__writes>1)throw new Error('blocked');return window.__originalSet.call(this,key,value);};true;''')
                page.locator('#applyPrefs').click();expect(page.locator('#transferStatus')).to_contain_text('一部の設定が変わった可能性')
                expect(page.locator('[data-weight="github"]')).to_have_value('5')
                assert stored(page)['saved']==after['saved'] and stored(page)['read']==after['read']
                assert not errors,errors
                assert not external,external
                context.close()
                print(f'{width}px local export / import preview / merge / cancel / invalid files / stale read / quota rollback / partial failure: PASS',flush=True)
            browser.close()
    finally:
        server.shutdown();server.server_close()


if __name__=='__main__':
    run()
