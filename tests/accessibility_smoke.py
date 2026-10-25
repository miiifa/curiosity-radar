"""Keyboard, touch targets, accessible state and contrast; no external requests."""
import json
import os
import re
import threading
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import sync_playwright, expect
from browser_smoke import Handler, ROOT, fixture


def contrast(foreground, background):
    def luminance(color):
        rgb = [float(value)/255 for value in re.findall(r'[\d.]+', color)[:3]]
        assert len(rgb) == 3, color
        return sum((v/12.92 if v <= .04045 else ((v+.055)/1.055)**2.4)*w
                   for v, w in zip(rgb, (.2126, .7152, .0722)))
    a, b = sorted((luminance(foreground), luminance(background)))
    return (b+.05)/(a+.05)


def run():
    data=fixture()
    data['items']=[{**data['items'][0], 'id':category, 'category':category,
                    'url':'https://example.com/'+category, 'title':'公開テスト '+category,
                    'summary':'公開テストの説明', 'score':50}
                   for category in ('github','travel','money','ai')]
    server=ThreadingHTTPServer(('127.0.0.1',0),partial(Handler,directory=str(ROOT)))
    server.feed=(200,json.dumps(data))
    threading.Thread(target=server.serve_forever,daemon=True).start()
    base=f'http://127.0.0.1:{server.server_port}'
    screenshots=Path('/tmp/curiosity-radar-pr06');screenshots.mkdir(exist_ok=True)
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH','/usr/bin/chromium'),args=['--no-sandbox'])
            for width in (360,390,430,1280):
                context=browser.new_context(viewport={'width':width,'height':900},service_workers='block',has_touch=width<1000)
                context.route('https://example.com/**',lambda route:route.fulfill(status=200,content_type='text/html',body='<title>Public source fixture</title>'))
                page=context.new_page();errors=[]
                page.on('pageerror',lambda error:errors.append(str(error)))
                page.goto(base);page.wait_for_selector('.article')
                # First tab skips navigation. Native fragment navigation must move focus.
                page.keyboard.press('Tab')
                expect(page.locator('.skip-link')).to_be_focused()
                page.keyboard.press('Enter')
                expect(page.locator('#feedSection')).to_be_focused()
                assert page.locator('#feedSection').get_attribute('aria-labelledby')=='sectionTitle'
                assert page.locator('#feed').get_attribute('aria-live') is None
                assert page.locator('#feedSummary').get_attribute('role')=='status'
                assert '4件表示' in page.locator('#feedSummary').inner_text()
                # Keyboard focus remains visible, including the formerly outline-free search.
                page.locator('#search').focus()
                assert page.locator('#search').evaluate('el=>getComputedStyle(el).outlineStyle')=='solid'
                assert page.locator('#search').evaluate('el=>parseFloat(getComputedStyle(el).outlineWidth)')>=2
                page.keyboard.type('no-such-public-fixture')
                expect(page.locator('#empty')).to_be_visible()
                assert '0件表示' in page.locator('#feedSummary').inner_text()
                page.locator('#clearFilters').focus();page.keyboard.press('Enter')
                assert page.locator('.article').count()==4
                expect(page.locator('#sectionTitle')).to_be_focused()
                # Save remains pressed and focused after replacing the card DOM.
                save=page.locator('[data-save="github"]');save.focus();page.keyboard.press('Enter')
                expect(save).to_be_focused();expect(save).to_have_attribute('aria-pressed','true')
                expect(save).to_have_accessible_name('あとで読むに保存')
                page.keyboard.press('Space')
                expect(save).to_be_focused();expect(save).to_have_attribute('aria-pressed','false')
                expect(save).to_have_accessible_name('あとで読むに保存')
                page.keyboard.press('Enter')
                with page.expect_popup() as opened:
                    page.locator('[data-id="github"] .external').click()
                popup=opened.value;popup.wait_for_load_state();popup.close()
                expect(save).to_have_attribute('aria-pressed','true')
                assert page.evaluate('JSON.parse(localStorage.getItem("radar:read")).includes("github")')
                (page.locator('[data-chip="technology"]') if width<1000 else page.locator('#desktopNav [data-category="technology"]')).click()
                navigation=page.locator('#sourceFilters [data-chip="github"]')
                navigation.focus();page.keyboard.press('Enter')
                expect(navigation).to_be_focused();expect(navigation).to_have_attribute('aria-pressed','true')
                assert page.locator('.article').count()==1
                assert '1件表示' in page.locator('#feedSummary').inner_text()
                page.locator('.next-action summary').focus();page.keyboard.press('Enter')
                page.keyboard.press('Tab')
                expect(page.locator('.next-action pre')).to_be_focused()
                assert page.locator('.next-action pre').get_attribute('role')=='region'
                page.keyboard.press('PageDown')
                page.wait_for_function('document.querySelector(".next-action pre").scrollTop>0')
                # Modal keyboard behavior, human-readable slider value, reload persistence.
                opener=page.locator('#settingsTop');opener.focus();page.keyboard.press('Enter')
                expect(page.locator('#prefsDialog')).to_be_visible()
                slider=page.locator('[data-weight="github"]');slider.focus();page.keyboard.press('End')
                expect(slider).to_have_value('5');expect(slider).to_have_attribute('aria-valuetext','5: 最優先')
                expect(slider).to_have_accessible_name(re.compile('GitHub'))
                assert round(slider.bounding_box()['height'],2)>=44
                # The modal wraps Tab at both ends and Escape restores the opener.
                complete=page.locator('#prefsDialog button[type="submit"]');complete.focus();page.keyboard.press('Tab')
                assert page.evaluate('document.activeElement.closest("#prefsDialog")!==null')
                page.keyboard.press('Shift+Tab');expect(complete).to_be_focused()
                page.keyboard.press('Escape');expect(opener).to_be_focused()
                page.reload();page.wait_for_selector('.article')
                expect(page.locator('[data-save="github"]')).to_have_attribute('aria-pressed','true')
                opener.click();expect(slider).to_have_value('5');page.keyboard.press('Escape')
                # Removing the final saved card has a predictable focus destination.
                saved_nav=page.locator('[data-mobile-go="saved"]') if width<1000 else page.locator('#savedNav')
                saved_nav.focus();page.keyboard.press('Enter')
                expect(saved_nav).to_have_attribute('aria-pressed','true')
                save.focus();page.keyboard.press('Enter')
                expect(page.locator('#sectionTitle')).to_be_focused()
                expect(page.locator('#empty')).to_be_visible()
                assert '0件表示' in page.locator('#feedSummary').inner_text()
                page.locator('#clearFilters').click()
                if width<1000:
                    save.tap();expect(save).to_have_attribute('aria-pressed','true')
                    page.locator('#unreadFilter').tap();expect(page.locator('#unreadFilter')).to_have_attribute('aria-pressed','true')
                    page.locator('#unreadFilter').tap();expect(page.locator('#unreadFilter')).to_have_attribute('aria-pressed','false')
                # Primary controls are at least 44px, including icon buttons and mobile chips.
                for selector in ('#settingsTop','.save-btn','.action','.external','#unreadFilter','#sort',
                                 '#settingsInline','.nav-item','.mobile-chips button','.bottom-nav button'):
                    for control in page.locator(selector).all():
                        if control.is_visible():
                            # Translated cards can expose 43.99997 for a 44px CSS box.
                            box=control.bounding_box();assert round(box['height'],2)>=44,(width,selector,box)
                            if selector in ('#settingsTop','.save-btn'):assert round(box['width'],2)>=44
                # Flat control backgrounds use their real computed color. Article text is
                # checked against a conservative lighter bound of its feature-card gradients.
                checks=[('#search','::placeholder','.searchbox'),('.select-wrap',None,'.select-wrap'),('#sort option',None,'#sort option')]
                for selector,pseudo,background in checks:
                    color=page.locator(selector).first.evaluate('(el,pseudo)=>getComputedStyle(el,pseudo).color',pseudo)
                    bg=page.locator(background).first.evaluate('el=>getComputedStyle(el).backgroundColor')
                    assert contrast(color,bg)>=4.5,(selector,color,bg)
                action=page.locator('.action').first
                action.hover()
                colors=action.evaluate('el=>({fg:getComputedStyle(el).color,bg:getComputedStyle(el).backgroundColor})')
                assert contrast(colors['fg'],colors['bg'])>=4.5,colors
                for selector in ('.card-time','.summary','.source','.rank','.provenance','.next-action summary','.hypothesis-note'):
                    color=page.locator(selector).first.evaluate('el=>getComputedStyle(el).color')
                    assert contrast(color,page.locator('html').evaluate('el=>getComputedStyle(el).getPropertyValue("--card-contrast-bg").trim()'))>=4.5,(selector,color)
                assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
                assert not errors,errors
                page.screenshot(path=str(screenshots/f'keyboard-mobile-{width}.png'),full_page=True)
                context.close()
                print(f'{width}px keyboard / focus / accessible state / 44px controls / contrast / preferences / saved: PASS',flush=True)
            browser.close()
    finally:
        server.shutdown();server.server_close()


if __name__=='__main__':
    run()
