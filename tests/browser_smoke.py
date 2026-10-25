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

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
NOW = dt.datetime.now(dt.timezone.utc)


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
                            assert page.locator('time').get_attribute('datetime') == '2026-10-24T12:00:00Z'
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
