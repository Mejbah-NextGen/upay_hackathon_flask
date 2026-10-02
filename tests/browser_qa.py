"""Headless QA of an isolated demo database; never touches the user's browser/data.

Run: python -m tests.browser_qa (requires Chrome or Playwright Chromium).
Screenshots and machine-readable results are written to tmp/browser-qa.
"""
import json
import logging
from pathlib import Path
from threading import Thread
from io import BytesIO

from PIL import Image
import zxingcpp
from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server

from app import create_app
from tests.helpers import TestConfig


def run():
    logging.getLogger('werkzeug').setLevel(logging.ERROR)
    app = create_app(TestConfig)
    server = make_server('127.0.0.1', 0, app, threaded=True)
    thread = Thread(target=server.serve_forever, daemon=True); thread.start()
    origin = f'http://127.0.0.1:{server.server_port}'
    output = Path('tmp/browser-qa'); output.mkdir(parents=True, exist_ok=True)
    pages = ('/', '/payments', '/wallet/send-money', '/wallet/cash-out', '/wallet/cash-out?channel=ATM',
             '/wallet/transfer-money', '/wallet/transfer-money?channel=VISA', '/payments/pay-bill?category=gas',
             '/payments/savings', '/payments/pay-later', '/wallet/report?days=120', '/profile/', '/notifications', '/schedules')
    results, errors = [], []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel='chrome', headless=True)
            context = browser.new_context(viewport={'width':1440,'height':960}, color_scheme='light')
            page = context.new_page(); page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(origin+'/auth/login'); page.locator('[name=mobile]').fill('01329097775')
            page.locator('.auth-card button[type=submit]').click()
            page.locator('[name=otp]').fill('123456'); page.locator('.auth-card button[type=submit]').click()
            page.wait_for_url(origin+'/')
            for language in ('en','bn'):
                context.request.post(origin+'/preferences/display',form={'language':language,'theme':'light'})
                for width in (320,375,768,1024,1440):
                    page.set_viewport_size({'width':width,'height':900})
                    for path in pages:
                        response=page.goto(origin+path,wait_until='load')
                        page.evaluate('() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))')
                        metrics=page.evaluate('''() => ({width:innerWidth,scroll:document.documentElement.scrollWidth,
                          overflow:Array.from(document.querySelectorAll('.topbar,.page-heading,.stats-grid,.section-card,.profile-chip,.hero-banner'))
                            .filter(e=>e.getBoundingClientRect().right>innerWidth+1).map(e=>e.className)})''')
                        result={'language':language,'viewport':width,'page':path,'status':response.status,**metrics}
                        results.append(result)
                        if response.status!=200 or metrics['scroll']>width+1 or metrics['overflow']:
                            errors.append(json.dumps(result))
                        if path in ('/','/wallet/report?days=120') and width in (320,768,1440):
                            if path=='/':
                                page.screenshot(path=str(output/f'{language}-{width}-dashboard.png'),full_page=True)
                            else:
                                page.locator('.report-analysis').screenshot(path=str(output/f'{language}-{width}-report.png'))
                print(f'{language}: checked {len(pages)*5} viewport/page combinations',flush=True)
            # Theme controls and system preference are actually applied.
            context.request.post(origin+'/preferences/display',form={'language':'en','theme':'dark'})
            page.goto(origin+'/'); assert page.locator('html').get_attribute('data-theme')=='dark'
            assert page.evaluate("getComputedStyle(document.body).backgroundColor")=='rgb(16, 23, 36)'
            page.screenshot(path=str(output/'dark-dashboard.png'),full_page=True)
            context.request.post(origin+'/preferences/display',form={'theme':'system'})
            page.emulate_media(color_scheme='dark'); page.reload()
            assert page.evaluate("getComputedStyle(document.body).backgroundColor")=='rgb(16, 23, 36)'
            # Opening an individual alert opens its receipt and lowers the badge.
            context.request.post(origin+'/notifications/read')
            context.request.post(origin+'/wallet/add-money',form={'source':'Bank Account','amount':'10'})
            context.request.post(origin+'/wallet/add-money',form={'source':'Bank Account','amount':'20'})
            page.goto(origin+'/'); page.locator('#notificationDropdown summary').click()
            before=page.locator('.notification-count').text_content()
            page.locator('.notification-panel .notification-item').first.click()
            page.wait_for_url('**/wallet/transaction/*')
            after=page.locator('.notification-count').text_content()
            assert int(after)==int(before)-1
            # QR generated by the actual SVG renderer is decodable and fills a form.
            page.goto(origin+'/payments/pay-bill?category=gas')
            page.locator('[name=provider]').select_option('Titas Gas')
            page.locator('[name=account_no]').fill('DEMO-GAS-1001'); page.locator('[name=amount]').fill('20.50')
            page.locator('[data-operation-qr] summary').click()
            page.locator('[data-qr-image]').wait_for(state='visible')
            page.locator('[data-qr-image]').evaluate('(e)=>e.decode()')
            image=page.locator('[data-qr-image]').screenshot()
            barcode=zxingcpp.read_barcode(Image.open(BytesIO(image)).convert('RGB'))
            assert barcode and barcode.text.startswith('UPAYX:')
            page.locator('[name=amount]').fill('30')
            page.locator('[data-qr-text]').fill(barcode.text); page.locator('[data-qr-read]').click()
            page.wait_for_function("document.querySelector('[name=amount]').value === '20.50'")
            # Assistant history persists; clear resets both UI and server context.
            page.locator('#assistantToggle').click()
            page.locator('#assistantQuestion').fill('What is my balance?'); page.locator('#assistantSend').click()
            page.wait_for_function("document.querySelectorAll('.assistant-message').length >= 3")
            assert 'Open Report' not in page.locator('#assistantMessages').inner_text()
            page.locator('#assistantClear').click()
            page.wait_for_function("document.querySelectorAll('.assistant-message').length === 1")
            assert context.request.get(origin+'/assistant/history').json()['messages']==[]
            browser.close()
    finally:
        server.shutdown()
    (output/'results.json').write_text(json.dumps({'checks':results,'errors':errors},ensure_ascii=False,indent=2),encoding='utf-8')
    if errors:
        raise AssertionError('\n'.join(errors))
    print(f'Passed {len(results)} responsive checks, themes, notification, QR, assistant flows.',flush=True)


if __name__=='__main__':
    run()
