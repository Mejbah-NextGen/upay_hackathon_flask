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
from openpyxl import load_workbook
from pypdf import PdfReader
import zxingcpp
from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server

from app import create_app
from app.services.wallet_catalog import DEMO_BANKS
from tests.helpers import TestConfig


def run():
    logging.getLogger('werkzeug').setLevel(logging.ERROR)
    app = create_app(TestConfig)
    server = make_server('127.0.0.1', 0, app, threaded=True)
    thread = Thread(target=server.serve_forever, daemon=True); thread.start()
    origin = f'http://127.0.0.1:{server.server_port}'
    output = Path('tmp/browser-qa'); output.mkdir(parents=True, exist_ok=True)
    pages = ('/', '/payments', '/wallet/send-money', '/wallet/cash-out', '/wallet/cash-out?channel=ATM',
             '/wallet/transfer-money', '/wallet/transfer-money?channel=VISA', '/wallet/add-money', '/payments/recharge', '/payments/pay-bill?category=gas',
             '/payments/savings', '/payments/pay-later', '/wallet/report?days=120', '/profile/', '/notifications', '/schedules')
    results, errors = [], []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel='chrome', headless=True)
            context = browser.new_context(viewport={'width':1440,'height':960}, color_scheme='light', has_touch=True)
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
            funding={'source':'Bank Account','bank':DEMO_BANKS[0],'account_number':'1234567890','holder_name':'Demo Account Holder'}
            context.request.post(origin+'/wallet/add-money',form={**funding,'amount':'10'},max_redirects=0)
            context.request.post(origin+'/wallet/add-money',form={**funding,'amount':'20'},max_redirects=0)
            page.goto(origin+'/'); page.locator('#notificationDropdown summary').click()
            before=page.locator('.notification-count').text_content()
            page.locator('.notification-panel .notification-item').first.click()
            page.wait_for_url('**/wallet/transaction/*')
            after=page.locator('.notification-count').text_content()
            assert int(after)==int(before)-1
            # Browser Back restores cached markup; server read state must refresh it.
            page.go_back()
            page.wait_for_function("document.querySelector('.notification-count')?.textContent === '1'")
            assert page.locator('.notification-item.unread').count()==1
            if not page.locator('#notificationDropdown').evaluate('(e)=>e.open'):
                page.locator('#notificationDropdown summary').click()
            page.locator('.notification-panel .notification-item.unread').click()
            page.wait_for_url('**/wallet/transaction/*')
            assert page.locator('.notification-count').count()==0
            # Disabling navbar alerts retains the full notification page read action.
            context.request.post(origin+'/wallet/add-money',form={**funding,'amount':'5'},max_redirects=0)
            context.request.post(origin+'/profile/settings',form={})
            page.goto(origin+'/notifications')
            page.wait_for_function("document.querySelector('[data-notification-read-all]') && !document.querySelector('[data-notification-read-all]').hidden")
            assert page.locator('[data-notification-read-all]').is_visible()
            assert page.locator('.notification-count').count()==0
            context.request.post(origin+'/profile/settings',form={'notifications_enabled':'on'})
            # Welcome/date filters remain above the figures at mobile and desktop sizes.
            for width in (375,1440):
                page.set_viewport_size({'width':width,'height':900})
                page.goto(origin+'/?days=30')
                order=page.evaluate("() => ['.hero-banner','.period-filter','.stats-grid'].map(s=>document.querySelector(s).getBoundingClientRect().top)")
                assert order[0]<order[1]<order[2]
                page.locator('.quick-pay-grid a').filter(has_text='Education').click()
                assert page.locator('.page-back').get_attribute('href')=='/?days=30'
                assert page.locator('[name=category]').get_attribute('type')=='hidden'
                assert page.locator('[name=category]').input_value()=='education'
                page.locator('.page-back').click()
                page.wait_for_url(origin+'/?days=30')
            # Selected funding source asks for its details and hides unused fields.
            page.goto(origin+'/wallet/add-money')
            assert page.locator('[name=account_number]').is_visible()
            page.locator('[name=source]').select_option('Debit / Credit Card')
            assert page.locator('[name=card_number]').is_visible()
            assert page.locator('[name=account_number]').is_hidden()
            assert page.locator('[name=account_number]').is_disabled()
            # A mismatched operator is rejected before recharge submission.
            page.goto(origin+'/payments/recharge')
            page.locator('[name=operator]').select_option('Grameenphone')
            page.locator('[name=mobile]').fill('01612345678')
            assert not page.locator('[data-recharge-validation]').evaluate('(f)=>f.checkValidity()')
            assert 'Choose Airtel' in page.locator('[data-recharge-operator-status]').inner_text()
            page.locator('[name=operator]').select_option('Airtel')
            assert page.locator('[name=operator]').evaluate('(e)=>e.validity.valid')
            # Real taps/clicks on chart shapes open scoped details, with both exports.
            for width in (375,1440):
                page.set_viewport_size({'width':width,'height':900})
                page.goto(origin+'/wallet/report?days=120')
                bars=page.locator('#reportBarChart [data-chart-segment="daily"]')
                index=bars.evaluate_all('(items)=>items.findIndex(e=>Number(e.getAttribute("height"))>0)')
                bar=bars.nth(index)
                if width==375: bar.tap()
                else: bar.click()
                assert page.locator('#reportSegmentDialog').evaluate('(e)=>e.open')
                assert page.locator('#reportSegmentRows tr').count()>0
                assert page.locator('#reportSegmentFormat option').count()==2
                page.keyboard.press('Escape')
                assert not page.locator('#reportSegmentDialog').evaluate('(e)=>e.open')
                # Use the middle of the first donut arc, away from its empty center.
                page.locator('#reportPieChart').scroll_into_view_if_needed()
                point=page.evaluate('''() => {
                  const data=JSON.parse(document.getElementById('reportChartData').textContent);
                  const angle=data.categories[0].amount/data.outgoing_total*Math.PI-Math.PI/2;
                  const svg=document.querySelector('#reportPieChart svg');
                  const p=new DOMPoint(300+99*Math.cos(angle),150+99*Math.sin(angle)).matrixTransform(svg.getScreenCTM());
                  return {x:p.x,y:p.y};
                }''')
                if width==375: page.touchscreen.tap(point['x'],point['y'])
                else: page.mouse.click(point['x'],point['y'])
                assert page.locator('#reportSegmentDialog').evaluate('(e)=>e.open')
                selected=page.locator('#reportSegmentRows tr').count()
                assert selected>0
                assert page.evaluate('document.documentElement.scrollWidth')<=width+1
                page.locator('#reportSegmentDialog').screenshot(path=str(output/f'{width}-chart-details.png'))
                if width==1440:
                    for extension in ('xlsx','pdf'):
                        page.locator('#reportSegmentFormat').select_option(extension)
                        with page.expect_download() as download_event:
                            page.locator('#reportSegmentExport').click()
                        target=output/f'chart-selection.{extension}'
                        download_event.value.save_as(str(target))
                        if extension=='xlsx':
                            summary=load_workbook(target,data_only=True)['Report summary']
                            assert summary['B7'].value==selected
                        else:
                            reader=PdfReader(target)
                            assert 'Report summary' in reader.pages[-1].extract_text()
                page.keyboard.press('Escape')
                # Legend and keyboard offer the same selection to keyboard users.
                page.locator('#reportPieLegend button').first.focus()
                page.keyboard.press('Enter')
                assert page.locator('#reportSegmentRows tr').count()==selected
                page.keyboard.press('Escape')
            page.goto(origin+'/schedules')
            page.get_by_role('link',name='Open Report',exact=True).click()
            page.wait_for_url('**/wallet/report?plan_mode=auto_pay')
            assert page.locator('select[name=plan_mode]').input_value()=='auto_pay'
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
