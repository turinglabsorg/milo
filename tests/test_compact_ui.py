import time
from pathlib import Path

import pytest
from playwright.sync_api import expect, sync_playwright
from test_responsive_inbox import service


@pytest.mark.parametrize('width,height', [(1440, 1000), (390, 844)])
def test_compact_black_settings_account_buttons_and_cached_recap(tmp_path, width, height):
    context = {}

    def prepare(app, received, sent):
        context["bootstrap"] = app.state.store.bootstrap
        app.state.store.set_setting('identity', {'name': 'Sam Taylor', 'aliases': ['Sam'],
                                               'context': 'Export developer', 'reply_language': 'auto'})
        app.state.store.set_setting('appearance', {'theme': 'dark'})
        app.state.google.status = lambda: {'configured': True}
        result = {'overview': 'La conversazione è aggiornata. Una richiesta merita attenzione.',
                  'priorities': [{'message_id': sent, 'action': 'Controlla la richiesta e prepara una risposta.'}],
                  'message_ids': [sent], 'model': 'test'}
        app.state.store.set_setting('recap', {**result, 'generated_at': time.time()})
        app.state.store.set_setting('recap_status', {'phase': 'ready'})
        app.state.ai.recap = lambda source=None: result

    with service(tmp_path, prepare, live=True) as (url, sent), sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={'width': width, 'height': height}, service_workers='block')
        errors, recap_requests = [], []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('request', lambda request: recap_requests.append(request.method) if request.url.endswith('/api/recap') else None)
        assert page.request.post(url + "/api/setup", data={"password": "isolated UI test password", "bootstrap": context["bootstrap"]}).status == 200
        page.goto(url)
        expect(page.locator('.message-row')).to_have_count(2)
        expect(page.locator('.ai-card')).to_have_count(0)
        expect(page.locator('.sender-line .row-analysis')).to_have_count(1)
        expect(page.locator('.sender-line .account-dot')).to_have_count(0)
        expect(page.locator('.title-row .badge, .subheading, .recap-card')).to_have_count(0)
        expect(page.locator('.list-recap')).to_have_count(1)
        expect(page.locator('.all-accounts')).to_have_attribute('aria-pressed', 'true')
        assert page.locator('.reading-panel').evaluate('(el)=>getComputedStyle(el).backgroundColor') == 'rgb(0, 0, 0)'
        assert max(page.locator('.message-row').evaluate_all('(els)=>els.map(el=>el.getBoundingClientRect().height)')) < 120
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        output = Path('test-results')
        output.mkdir(exist_ok=True)
        page.screenshot(path=str(output / f'compact-inbox-{width}.png'))
        page.locator('[data-action="recap"]').click()
        expect(page.locator('.recap-overview')).to_have_text('La conversazione è aggiornata. Una richiesta merita attenzione.')
        expect(page.locator('.priority-item')).to_have_count(1)
        assert recap_requests == ['GET']
        assert page.locator('.recap-overview').evaluate('(el)=>getComputedStyle(el).color') == 'rgb(242, 242, 242)'
        page.screenshot(path=str(output / f'compact-recap-{width}.png'))
        page.get_by_role('button', name='Chiudi', exact=True).click()
        if width <= 600:
            page.get_by_role('button', name='Apri menu').click()
        page.get_by_role('button', name='Impostazioni', exact=True).first.click()
        page.locator('[data-settings-tab="identity"]').click()
        expect(page.locator('#identity-form [name="name"]')).to_have_value('Sam Taylor')
        page.locator('#identity-form [name="name"]').fill('Jordan Morgan')
        page.locator('#identity-form [name="aliases"]').fill('Jordan, Jo')
        page.get_by_role('button', name='Salva identità', exact=True).click()
        expect(page.get_by_role('dialog')).to_have_count(0)
        identity = page.request.get(url + '/api/state').json()['identity']
        assert identity['name'] == 'Jordan Morgan' and identity['aliases'] == ['Jordan', 'Jo']
        if width <= 600:
            page.get_by_role('button', name='Apri menu').click()
        page.get_by_role('button', name='Impostazioni', exact=True).first.click()
        page.locator('[data-settings-tab="identity"]').click()
        expect(page.locator('#identity-form [name="name"]')).to_have_value('Jordan Morgan')
        page.screenshot(path=str(output / f'identity-{width}.png'))
        page.get_by_role('button', name='Chiudi', exact=True).click()
        if width <= 600:
            page.get_by_role('button', name='Apri menu').click()
        page.locator('[data-action="add-account"]').click()
        expect(page.locator('.google-mark')).to_have_count(1)
        buttons = page.locator('.account-connect-actions>button').evaluate_all('(els)=>els.map(el=>({width:el.getBoundingClientRect().width,height:el.getBoundingClientRect().height}))')
        assert len(buttons) == 2 and abs(buttons[0]['width'] - buttons[1]['width']) < 1
        assert abs(buttons[0]['height'] - buttons[1]['height']) < 1
        page.screenshot(path=str(output / f'account-connect-{width}.png'))
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth') and not errors
        browser.close()
