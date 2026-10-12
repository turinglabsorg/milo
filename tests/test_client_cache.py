from email.message import EmailMessage

import pytest
from playwright.sync_api import expect, sync_playwright
from test_responsive_inbox import service


def prepare_reply(app, received, sent):
    mail = EmailMessage()
    mail['From'] = 'Customer <customer@example.com>'
    mail['Reply-To'] = 'Support <support@example.com>'
    mail['To'] = 'Owner <you@example.com>, Colleague <colleague@example.com>'
    mail['Cc'] = 'Copy <copy@example.com>, support@example.com, you@example.com'
    mail.set_content('Reply-all original content')
    app.state.store.execute('UPDATE messages SET raw=?,content_version=NULL WHERE id=?', (mail.as_bytes(), received))


def test_reply_all_includes_cc_excludes_self_and_retains_draft(tmp_path):
    with service(tmp_path, prepare_reply) as (url, sent), sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(service_workers='block')
        page.goto(url)
        page.locator(f'[data-message="{sent}"]').click()
        page.get_by_role('button', name='Rispondi a tutti', exact=True).click()
        expect(page.locator('#inline-composer #compose-form')).to_be_visible()
        expect(page.locator('[name="to"]')).to_have_value('support@example.com, colleague@example.com')
        expect(page.locator('[name="cc"]')).to_have_value('copy@example.com')
        page.locator('[name="body"]').fill('Reply to everyone')
        page.get_by_role('button', name='Salva bozza', exact=True).click()
        expect(page.locator('.draft-save-status')).to_have_text('Bozza salvata')
        draft = page.request.get(url + '/api/drafts').json()['drafts'][0]
        assert draft['mode'] == 'reply_all' and draft['cc'] == 'copy@example.com'
        page.get_by_role('button', name='Chiudi', exact=True).click()
        page.get_by_role('button', name='Rispondi', exact=True).click()
        expect(page.locator('[name="to"]')).to_have_value('support@example.com')
        expect(page.locator('[name="cc"]')).to_have_value('')
        browser.close()


@pytest.mark.parametrize('width,height', [(1440, 1000), (390, 844)])
def test_cache_survives_offline_reload_and_does_not_refetch_bodies(tmp_path, width, height):
    with service(tmp_path) as (url, sent), sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={'width': width, 'height': height})
        page = context.new_page()
        errors = []
        bodies = []
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.on('request', lambda r: bodies.append(r.url) if '/api/messages/' in r.url and '/thread' not in r.url else None)
        page.goto(url)
        expect(page.locator('.message-row')).to_have_count(2)
        page.locator(f'[data-message="{sent}"]').click()
        expect(page.frame_locator('.email-html').get_by_text('HTML reply', exact=True)).to_be_visible()
        page.wait_for_function('async()=>{const {deviceCache}=await import("/static/cache.js");return !!(await deviceCache.get("api:/messages/"+document.querySelector(".message-row.selected").dataset.message));}')
        page.evaluate('()=>navigator.serviceWorker.ready.then(()=>new Promise(resolve=>navigator.serviceWorker.controller?resolve():navigator.serviceWorker.addEventListener("controllerchange",resolve,{once:true})))')
        # A reopen uses downloaded content, not another body request.
        before = len(bodies)
        if width <= 900:
            page.get_by_role('button', name='Torna alla lista').click()
        page.locator(f'[data-message="{sent}"]').click()
        expect(page.frame_locator('.email-html').get_by_text('HTML reply', exact=True)).to_be_visible()
        assert len(bodies) == before
        context.set_offline(True)
        page.reload()
        expect(page.locator('.message-row')).to_have_count(2)
        page.locator(f'[data-message="{sent}"]').click()
        expect(page.frame_locator('.email-html').get_by_text('HTML reply', exact=True)).to_be_visible()
        if width <= 900:
            page.get_by_role('button', name='Torna alla lista').click()
        expect(page.get_by_text('Sei offline. Mostro la posta salvata su questo dispositivo.')).to_be_visible()
        # Cached API payloads are stored as ciphertext, not plaintext mail.
        records = page.evaluate('()=>new Promise((resolve,reject)=>{const r=indexedDB.open("milo-device-cache",1);r.onsuccess=()=>{const q=r.result.transaction("records").objectStore("records").getAll();q.onsuccess=()=>resolve(q.result.map(x=>({id:x.id,encrypted:x.data instanceof ArrayBuffer,key:x.key?.extractable})));};r.onerror=reject;})')
        assert any(r['id'].startswith('api:/messages/') and r['encrypted'] for r in records)
        assert next(r for r in records if r['id'] == 'crypto-key')['key'] is False
        assert not errors
        context.close()
        browser.close()


def test_lazy_thread_index_excludes_mime_and_bodies(logged_in, account_data):
    from test_conversations import add
    store = logged_in.app.state.store
    account = store.add_account(account_data)
    sent = None
    for i in range(18):
        sent = add(store, account, i + 20, sent=i % 2 == 1, date=i)
        store.execute('UPDATE messages SET body=?,raw=? WHERE id=?', ('LONG-CONTENT' * 20000, b'MIME-BLOB' * 20000, sent))
    result = logged_in.get('/api/messages/' + sent + '/thread?lazy=true')
    assert result.status_code == 200 and len(result.content) < 40000
    messages = result.json()['messages']
    assert len(messages) == 18 and any(m['sent'] for m in messages)
    assert all(not {'raw', 'html', 'body'} & m.keys() and not m['body_loaded'] for m in messages)


def test_offline_delete_is_durable_and_reconciles_without_resurrection(tmp_path):
    with service(tmp_path) as (url, sent), sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context()
        page = context.new_page()
        page.goto(url)
        page.locator(f'[data-message="{sent}"]').click()
        expect(page.frame_locator('.email-html').get_by_text('HTML reply', exact=True)).to_be_visible()
        page.evaluate('()=>navigator.serviceWorker.ready.then(()=>new Promise(resolve=>navigator.serviceWorker.controller?resolve():navigator.serviceWorker.addEventListener("controllerchange",resolve,{once:true})))')
        context.set_offline(True)
        page.get_by_role('button', name='Elimina conversazione', exact=True).click()
        expect(page.locator('.message-row')).to_have_count(1)
        expect(page.locator('#toast')).to_contain_text('Modifica salvata sul dispositivo')
        page.reload()
        expect(page.locator('.message-row')).to_have_count(1)
        assert len(page.evaluate('async()=>{const {deviceCache}=await import("/static/cache.js");return await deviceCache.get("pending-operations");}')) == 1
        context.set_offline(False)
        page.reload()
        page.wait_for_function('async()=>{const response=await fetch("/api/messages");return (await response.json()).messages.length===1;}')
        page.wait_for_function('async()=>{const {deviceCache}=await import("/static/cache.js");return !(await deviceCache.get("pending-operations"))?.length;}')
        expect(page.locator('.message-row')).to_have_count(1)
        assert page.request.get(url + '/api/messages').json()['messages'][0]['id'] != sent
        browser.close()


def test_downloaded_inline_image_remains_available_offline(tmp_path):
    import base64
    png = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aA1cAAAAASUVORK5CYII=')

    def prepare(app, received, sent):
        mail = EmailMessage()
        mail.set_content('Inline image')
        mail.add_alternative('<p>Offline inline image</p><img src="cid:image" alt="cached image">', subtype='html')
        mail.get_payload()[1].add_related(png, maintype='image', subtype='png', cid='<image>')
        app.state.store.execute('UPDATE messages SET raw=?,content_version=NULL WHERE id=?', (mail.as_bytes(), sent))

    with service(tmp_path, prepare) as (url, sent), sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context()
        page = context.new_page()
        page.goto(url)
        page.evaluate('()=>navigator.serviceWorker.ready.then(()=>new Promise(resolve=>navigator.serviceWorker.controller?resolve():navigator.serviceWorker.addEventListener("controllerchange",resolve,{once:true})))')
        page.locator(f'[data-message="{sent}"]').click()
        image = page.frame_locator('.email-html').get_by_alt_text('cached image')
        expect(image).to_be_visible()
        path = image.get_attribute('src')
        page.wait_for_function('async path=>{const {deviceCache}=await import("/static/cache.js");return !!(await deviceCache.getAsset(path));}', arg=path)
        context.set_offline(True)
        page.reload()
        page.locator(f'[data-message="{sent}"]').click()
        image = page.frame_locator('.email-html').get_by_alt_text('cached image')
        expect(image).to_be_visible()
        assert image.evaluate('(el)=>el.complete&&el.naturalWidth===1')
        browser.close()
