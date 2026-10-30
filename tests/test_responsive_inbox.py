"""Real Chromium checks with delayed service responses, using an isolated archive."""
import threading
from contextlib import contextmanager
from email.message import EmailMessage
from socket import socket

import pytest
import uvicorn
from browser_helpers import type_body, wait_for_async, write_body
from playwright.sync_api import expect, sync_playwright
from test_conversations import add

from milo.app import create_app
from milo.demo import seed_demo


@contextmanager
def service(tmp_path, prepare=None, live=False):
    app = create_app(tmp_path / 'browser', demo=not live)
    if live:
        seed_demo(app.state.store)
        app.state.engine.sync_all = lambda: []
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
    store.set_raw(sent, mail.as_bytes())
    if prepare:
        prepare(app, received, sent)
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
        page = browser.new_page(viewport={'width': width, 'height': height}, service_workers='block')
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
        expect(page.get_by_role('dialog')).to_have_count(0)
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


def test_ai_reply_stays_inline_and_does_not_replace_user_edits(tmp_path):
    context = {}
    def prepare(app, received, sent):
        context['bootstrap'] = app.state.store.bootstrap
        app.state.ai.reply = lambda message_id: {'body': 'Generated suggestion'}
        mail = EmailMessage()
        mail['Reply-To'] = 'Support <support@example.com>'
        mail.set_content('Original incoming text')
        app.state.store.set_raw(received, mail.as_bytes())
        app.state.store.set_setting('ai', {'model': 'local', 'cloud_consent': False, 'automatic': False})

    with service(tmp_path, prepare, live=True) as (url, sent), sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(service_workers='block')
        assert page.request.post(url + '/api/setup', data={'password': 'isolated test password',
                                                          'bootstrap': context['bootstrap']}).status == 200
        page.goto(url)
        expect(page.locator('#login-form')).to_have_count(0)
        page.locator(f'[data-message="{sent}"]').click()
        delayed = []

        def delay_generation(route):
            delayed.append(True)
            response = route.fetch()
            expect(page.locator('#inline-composer .reply-generation')).to_be_visible()
            expect(page.get_by_role('dialog')).to_have_count(0)
            write_body(page, 'I wrote my own reply')
            route.fulfill(response=response)

        page.route('**/api/messages/*/reply', delay_generation)
        page.get_by_role('button', name='Aiutami a rispondere', exact=True).click()
        expect(page.locator('.reply-generation')).to_have_count(0)
        expect(page.locator('[name="body"]')).to_have_value('I wrote my own reply')
        assert delayed
        page.unroute('**/api/messages/*/reply')
        page.get_by_role('button', name='Elimina bozza', exact=True).click()
        expect(page.locator('#compose-form')).to_have_count(0)
        page.get_by_role('button', name='Aiutami a rispondere', exact=True).click()
        expect(page.locator('[name="body"]')).to_have_value('Generated suggestion')
        expect(page.locator('[name="to"]')).to_have_value('support@example.com')
        expect(page.get_by_role('dialog')).to_have_count(0)
        browser.close()


@pytest.mark.parametrize('width,height', [(1440, 1000), (390, 844)])
def test_large_forward_quoted_history_and_failed_close_recovery(tmp_path, width, height):
    body = 'Original complete message.\n' * 8000 + 'END-OF-ORIGINAL'

    def prepare(app, received, sent):
        mail = EmailMessage()
        mail.set_content(body)
        mail.add_alternative('<p>Latest reply</p><div class="gmail_quote">On Monday wrote:'
                             '<blockquote>' + '<p>Earlier reply</p>' * 100 + '</blockquote></div>', subtype='html')
        app.state.store.set_raw(sent, mail.as_bytes())
        app.state.store.execute('UPDATE messages SET body=?,subject=? WHERE id=?', (body, 'Re: Re: Fwd: Re: Project', sent))

    with service(tmp_path, prepare) as (url, sent), sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={'width': width, 'height': height}, service_workers='block')
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(url)
        page.locator(f'[data-message="{sent}"]').click()
        expect(page.locator('.mail-content h2')).to_have_text('Project')
        frame = page.frame_locator('.email-html')
        expect(frame.get_by_text('Latest reply', exact=True)).to_be_visible()
        expect(frame.locator('.milo-quoted-history')).not_to_have_attribute('open', '')
        expect(frame.get_by_text('Earlier reply', exact=True).first).not_to_be_visible()
        compact = page.locator('.email-html').bounding_box()['height']
        assert compact < 250
        frame.get_by_text('Mostra il testo citato', exact=True).click()
        expect(frame.get_by_text('Earlier reply', exact=True).first).to_be_visible()
        page.wait_for_function('()=>document.querySelector(".email-html").offsetHeight > 1000')
        frame.get_by_text('Mostra il testo citato', exact=True).click()
        page.wait_for_function('()=>document.querySelector(".email-html").offsetHeight < 250')
        page.get_by_role('button', name='Inoltra', exact=True).click()
        expect(page.locator('#inline-composer #compose-form')).to_be_visible()
        expect(page.get_by_role('dialog')).to_have_count(0)
        expect(page.locator('[name="subject"]')).to_have_value('Fwd: Project')
        forwarded = page.locator('[name="body"]').input_value()
        assert len(forwarded) > 100000 and forwarded.endswith(body)
        page.get_by_role('button', name='Salva bozza', exact=True).click()
        expect(page.locator('.draft-save-status')).to_have_text('Bozza salvata')
        stored = page.request.get(url + '/api/drafts').json()['drafts'][0]
        assert stored['body'] == forwarded.strip() and stored['context_message_id'] == sent

        # Closing must complete before a failing server response arrives.
        def fail_save(route):
            if route.request.method != 'PUT':
                route.continue_()
                return
            expect(page.locator('#compose-form')).to_have_count(0)
            route.fulfill(status=503, json={'detail': 'Server temporarily unavailable'})

        type_body(page, '')
        page.keyboard.press('Enter')
        page.keyboard.type('Last edit kept')
        page.route('**/api/drafts', fail_save)
        page.get_by_role('button', name='Chiudi', exact=True).click()
        expect(page.locator('#compose-form')).to_have_count(0)
        expect(page.locator('#toast')).to_have_text('Server temporarily unavailable')
        page.wait_for_function('()=>JSON.parse(localStorage.getItem("milo-pending-drafts"))[0].body.endsWith("Last edit kept")')
        page.unroute('**/api/drafts')
        page.reload()
        expect(page.locator('.message-row')).to_have_count(2)
        if width <= 600:
            page.get_by_role('button', name='Apri menu').click()
        page.locator('[data-view="drafts"]').click()
        expect(page.locator('.draft-row')).to_have_count(1)
        page.locator('.draft-row').click()
        expect(page.locator('#inline-composer #compose-form')).to_be_visible()
        restored = page.locator('[name="body"]').input_value()
        assert len(restored) > 100000 and restored.endswith('Last edit kept')
        page.get_by_role('button', name='Elimina bozza', exact=True).click()
        expect(page.locator('#compose-form')).to_have_count(0)
        expect(page.locator('#toast')).to_have_text('Bozza eliminata.')
        assert not page.request.get(url + '/api/drafts').json()['drafts']
        assert not errors
        browser.close()


def test_inline_reply_keeps_text_focus_and_caret_during_sync(tmp_path):
    context = {}

    def prepare(app, received, sent):
        context.update(store=app.state.store, received=received)

    with service(tmp_path, prepare) as (url, sent), sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(url)
        page.locator(f'[data-message="{sent}"]').click()
        page.get_by_role('button', name='Rispondi', exact=True).click()
        expect(page.locator('#inline-composer #compose-form')).to_be_visible()
        expect(page.get_by_role('dialog')).to_have_count(0)
        field = page.locator('[name="body"]')
        write_body(page, 'My draft is still here')
        frame = page.locator('#compose-form .rich-frame')
        frame.evaluate('(f)=>{f.focus();const d=f.contentDocument;d.body.focus();'
                       'd.getSelection().collapse(d.body.querySelector("p").firstChild,8);}')
        context['store'].execute('UPDATE messages SET subject=? WHERE id=?', ('Updated while typing', sent))
        expect(page.locator('.mail-content h2')).to_have_text('Updated while typing', timeout=15000)
        expect(field).to_have_value('My draft is still here')
        expect(page.frame_locator('#compose-form .rich-frame').locator('body')).to_have_text('My draft is still here')
        wait_for_async(page, '()=>{const f=document.querySelector("#compose-form .rich-frame");'
                             'return document.activeElement===f&&f.contentDocument.getSelection().anchorOffset===8;}')
        page.keyboard.type('X')
        expect(field).to_have_value('My draftX is still here')
        page.keyboard.press('Escape')
        expect(page.locator('#compose-form')).to_have_count(0)
        expect(page.locator('#toast')).not_to_have_text('String should have at most 100000 characters')
        browser.close()


@pytest.mark.parametrize('width,height', [(1440, 1000), (390, 844)])
def test_new_message_opens_in_the_reading_column(tmp_path, width, height):
    with service(tmp_path) as (url, sent), sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={'width': width, 'height': height}, service_workers='block')
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(url)
        expect(page.locator('.message-row').first).to_be_visible()
        if width < 600:
            page.locator('[data-action="menu"]').first.click()
        page.locator('[data-action="compose"]').first.click()
        form = page.locator('#reading-panel #pane-composer #compose-form')
        expect(form).to_be_visible()
        expect(page.get_by_role('dialog')).to_have_count(0)
        expect(form.locator('.rich-frame')).to_be_visible()
        expect(form.locator('[data-rich-action^="format-"]')).to_have_count(0)
        if width < 600:
            expect(page.locator('#list-panel')).to_be_hidden()
        else:
            expect(page.locator('#list-panel')).to_be_visible()
        form.locator('[name="to"]').fill('anna@example.com')
        form.locator('[name="subject"]').fill('Colonna destra')
        page.frame_locator('#compose-form .rich-frame').locator('body').click()
        page.keyboard.type('Scritto nel pannello')
        if width >= 600:
            page.locator('[data-view="drafts"]').first.click()
        else:
            page.locator('.compose-pane-toolbar .back-button').click()
        expect(page.locator('#compose-form')).to_have_count(0)
        expect(page.locator('#list-panel')).to_be_visible()
        if width < 600:
            page.locator('[data-action="menu"]').first.click()
            page.locator('[data-view="drafts"]').first.click()
        expect(page.locator('.draft-row')).to_have_count(1)
        page.locator('.draft-row').click()
        expect(form).to_be_visible()
        expect(form.locator('[name="subject"]')).to_have_value('Colonna destra')
        if width >= 600:
            page.locator('[data-view="inbox"]').first.click()
            page.locator(f'[data-message="{sent}"]').click()
            expect(page.locator('#compose-form')).to_have_count(0)
            expect(page.locator('.mail-content h2')).to_be_visible()
        assert errors == []
        browser.close()
