"""Real Chromium checks with delayed service responses, using an isolated archive."""
import threading
from contextlib import contextmanager
from email.message import EmailMessage
from socket import socket

import pytest
import uvicorn
from playwright.sync_api import expect, sync_playwright
from test_conversations import add

from milo.app import create_app


@contextmanager
def service(tmp_path):
    app = create_app(tmp_path / 'browser', demo=True)
    store = app.state.store
    account_id = store.accounts()[0]['id']
    store.execute('DELETE FROM messages')
    received = add(store, account_id, 1, date=100)
    sent = add(store, account_id, 2, sent=True, date=200)
    add(store, account_id, 3, thread='other', date=300)
    store.execute('UPDATE messages SET analysis=? WHERE id=?', ('{"summary":"Meeting arranged"}', received))
    mail = EmailMessage()
    mail.set_content('Original text')
    mail.add_alternative('<table><tr><td style="color:rgb(255, 0, 0)"><strong>HTML reply</strong></td></tr></table><script>parent.window.unsafe=true</script>', subtype='html')
    store.execute('UPDATE messages SET raw=? WHERE id=?', (mail.as_bytes(), sent))
    with socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=port, log_level='error'))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    import time
    for _ in range(100):
        if server.started:
            break
        time.sleep(.02)
    assert server.started
    try:
        yield f'http://127.0.0.1:{port}', sent
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        assert not thread.is_alive()


@pytest.mark.parametrize('width,height', [(1440, 1000), (390, 844)])
def test_threads_theme_html_pin_and_optimistic_delete(tmp_path, width, height):
    with service(tmp_path) as (url, sent), sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width': width, 'height': height})
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(url)
        expect(page.locator('.message-row')).to_have_count(2)
        expect(page.locator('.row-analysis')).to_have_count(1)
        expect(page.get_by_text('Hai risposto', exact=True)).to_be_visible()
        assert 'Un po’ di intelligenza' not in page.locator('#app').inner_text()
        # Selection displays a skeleton before the slow response reaches the UI.
        def delay_reader(route):
            if route.request.method != 'GET':
                route.continue_()
                return
            response = route.fetch()
            page.locator('.skeleton-group.reader').wait_for(state='visible')
            route.fulfill(response=response)
        page.route('**/api/messages/*/thread', delay_reader)
        page.locator(f'[data-message="{sent}"]').click()
        expect(page.locator('.thread-message')).to_have_count(2)
        expect(page.get_by_text('Risposta inviata', exact=True)).to_be_visible()
        frame = page.frame_locator('.email-html')
        expect(frame.get_by_text('HTML reply', exact=True)).to_be_visible()
        assert page.evaluate('window.unsafe') is None
        page.unroute('**/api/messages/*/thread')
        page.get_by_role('button', name='Fissa in alto', exact=True).click()
        expect(page.get_by_role('button', name='Rimuovi pin', exact=True)).to_be_visible()
        expect(page.locator('.row-pin')).to_have_count(1)
        if width <= 900:
            page.get_by_role('button', name='Torna alla lista').click()
        expect(page.locator('.message-row').first).to_have_attribute('data-message', sent)
        if width <= 600:
            page.get_by_role('button', name='Apri menu').click()
        page.get_by_role('button', name='Impostazioni', exact=True).first.click()
        page.locator('[data-settings-tab="appearance"]').click()
        page.locator('[name="theme"]').select_option('dark')
        assert page.locator('html').get_attribute('data-theme') == 'dark'
        page.get_by_role('button', name='Salva aspetto', exact=True).click()
        page.reload()
        expect(page.locator('.message-row')).to_have_count(2)
        assert page.locator('html').get_attribute('data-theme') == 'dark'
        if width <= 600:
            page.get_by_role('button', name='Apri menu').click()
        page.get_by_role('button', name='Impostazioni', exact=True).first.click()
        page.get_by_role('button', name='Gestisci', exact=True).first.click()
        page.locator('[name="color"]').fill('#f97316')
        page.get_by_role('button', name='Salva account', exact=True).click()
        page.get_by_role('button', name='Chiudi', exact=True).click()
        page.locator(f'[data-message="{sent}"]').click()
        expect(page.locator('.thread-message')).to_have_count(2)
        # The row is removed before the DELETE has any HTTP response.
        def delayed_delete(route):
            if route.request.method == 'DELETE':
                expect(page.locator(f'[data-message="{sent}"]')).to_have_count(0)
            route.continue_()
        page.route('**/api/messages/*/thread', delayed_delete)
        page.get_by_role('button', name='Elimina conversazione', exact=True).click()
        expect(page.locator('.message-row')).to_have_count(1)
        page.unroute('**/api/messages/*/thread')
        page.reload()
        expect(page.locator('.message-row')).to_have_count(1)
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        assert not errors
        browser.close()
