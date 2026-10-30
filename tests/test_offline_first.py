import json
import time
from email.message import EmailMessage
from pathlib import Path

from browser_helpers import wait_for_async, write_body
from playwright.sync_api import expect, sync_playwright
from test_conversations import add
from test_responsive_inbox import service


def read_mail(app, received, sent):
    app.state.store.execute('UPDATE messages SET read=1')


def warm(page, url, sent):
    page.goto(url)
    expect(page.locator('.message-row')).to_have_count(2)
    page.locator(f'[data-message="{sent}"]').click()
    expect(page.frame_locator('.email-html').get_by_text('HTML reply', exact=True)).to_be_visible()
    page.evaluate('()=>navigator.serviceWorker.ready.then(()=>new Promise(resolve=>navigator.serviceWorker.controller?resolve():navigator.serviceWorker.addEventListener("controllerchange",resolve,{once:true})))')
    wait_for_async(page, 'async id=>{const {deviceCache}=await import("/static/cache.js");return !!(await deviceCache.get("api:/messages/"+id+"?load_images=true"));}', arg=sent)


def test_cached_navigation_edits_and_reload_work_with_all_server_responses_held(tmp_path):
    with service(tmp_path, read_mail) as (url, sent), sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context()
        page = context.new_page()
        errors, held, timings = [], [], {}
        page.on('pageerror', lambda error: errors.append(str(error)))
        warm(page, url, sent)

        def hold(route):
            held.append(route)

        page.route('**/api/**', hold)
        start = time.perf_counter()
        page.reload(wait_until='domcontentloaded')
        expect(page.locator('.message-row')).to_have_count(2, timeout=1000)
        timings['cached_inbox_ms'] = (time.perf_counter() - start) * 1000
        start = time.perf_counter()
        page.locator(f'[data-message="{sent}"]').click()
        expect(page.frame_locator('.email-html').get_by_text('HTML reply', exact=True)).to_be_visible(timeout=1000)
        timings['cached_reader_ms'] = (time.perf_counter() - start) * 1000
        page.keyboard.press('p')
        expect(page.get_by_role('button', name='Rimuovi dai preferiti', exact=True)).to_be_visible(timeout=1000)
        start = time.perf_counter()
        page.get_by_role('button', name='Preferiti', exact=False).filter(has=page.locator('.icon')).first.click()
        expect(page.locator('.message-row')).to_have_count(1, timeout=1000)
        timings['local_favorites_ms'] = (time.perf_counter() - start) * 1000
        page.locator(f'[data-message="{sent}"]').click()
        expect(page.get_by_role('button', name='Archivia', exact=True)).to_be_visible()
        page.get_by_role('button', name='Archivia', exact=True).click()
        page.locator('[data-view="inbox"]').click()
        expect(page.locator('.message-row')).to_have_count(1, timeout=1000)
        page.locator('[data-view="archive"]').click()
        expect(page.locator('.message-row')).to_have_count(1, timeout=1000)
        wait_for_async(page, 'async()=>{const {deviceCache}=await import("/static/cache.js");return (await deviceCache.get("pending-operations"))?.length===2;}')
        for route in held:
            try:
                route.abort()
            except Exception:
                pass
        context.set_offline(True)
        page.reload(wait_until='domcontentloaded')
        expect(page.locator('.message-row')).to_have_count(1, timeout=1000)
        page.locator('[data-view="archive"]').click()
        expect(page.locator('.message-row')).to_have_count(1, timeout=1000)
        page.locator(f'[data-message="{sent}"]').click()
        expect(page.frame_locator('.email-html').get_by_text('HTML reply', exact=True)).to_be_visible(timeout=1000)
        assert not errors and max(timings.values()) < 700
        Path('test-results').mkdir(exist_ok=True)
        Path('test-results/offline-first-latency.json').write_text(json.dumps(timings, indent=2))
        page.screenshot(path='test-results/offline-first-queued.png')
        browser.close()


def test_stale_metadata_and_delayed_ack_preserve_latest_favorite(tmp_path):
    applied=[]

    def prepare(app, received, sent):
        read_mail(app, received, sent)
        original=app.state.store.patch_conversation
        def track(message, patch):
            result=original(message,patch)
            applied.append(patch.copy())
            return result
        app.state.store.patch_conversation=track

    with service(tmp_path, prepare) as (url, sent), sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        warm(page, url, sent)
        held, blocked = [], []
        delay_state={'hold_lists':True}

        def delay(route):
            if delay_state['hold_lists'] and route.request.method == 'GET' and '/api/messages?' in route.request.url:
                response = route.fetch()
                held.append((route, response))
            elif route.request.method == 'PATCH' and not blocked:
                blocked.append((route, route.fetch()))
            else:
                route.continue_()

        page.route('**/api/**', delay)
        page.reload()
        expect(page.locator('.message-row')).to_have_count(2)
        page.locator(f'[data-message="{sent}"]').click()
        expect(page.frame_locator('.email-html').get_by_text('HTML reply', exact=True)).to_be_visible()
        page.get_by_role('button', name='Aggiungi ai preferiti', exact=True).click()
        expect(page.get_by_role('button', name='Rimuovi dai preferiti', exact=True)).to_be_visible(timeout=1000)
        page.get_by_role('button', name='Rimuovi dai preferiti', exact=True).click()
        page.get_by_role('button', name='Aggiungi ai preferiti', exact=True).click()
        wait_for_async(page, 'async()=>{const {deviceCache}=await import("/static/cache.js");return (await deviceCache.get("pending-operations"))?.length===3;}')
        assert held and blocked
        delay_state['hold_lists']=False
        for route, response in list(held):
            route.fulfill(response=response)
        expect(page.get_by_role('button', name='Rimuovi dai preferiti', exact=True)).to_be_visible()
        for route, response in blocked:
            route.fulfill(response=response)
        wait_for_async(page, 'async id=>(await (await fetch("/api/messages/"+id+"/thread")).json()).messages.every(m=>m.starred)', arg=sent)
        wait_for_async(page, 'async()=>{const {deviceCache}=await import("/static/cache.js");return !(await deviceCache.get("pending-operations"))?.length;}', timeout=10000)
        thread = page.request.get(url + '/api/messages/' + sent + '/thread').json()['messages']
        page.unroute('**/api/**', delay)
        assert applied == [{'starred': True}, {'starred': False}, {'starred': True}], applied
        assert all(m['starred'] for m in thread)
        assert page.request.get(url + '/api/state').json()['counts']['starred'] == 1
        expect(page.locator('[data-view="starred"] .count')).to_have_text('1')
        page.reload()
        expect(page.locator(f'[data-message="{sent}"] .row-star')).to_have_count(1)
        browser.close()


def test_recent_bodies_are_prefetched_in_background_without_opening(tmp_path):
    captured = {}

    def prepare(app, received, sent):
        read_mail(app, received, sent)
        captured['other'] = app.state.store.rows("SELECT id FROM messages WHERE thread_id='other'")[0]['id']

    with service(tmp_path, prepare) as (url, sent), sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context()
        page = context.new_page()
        page.goto(url)
        expect(page.locator('.message-row')).to_have_count(2)
        wait_for_async(page, 'async id=>{const {deviceCache}=await import("/static/cache.js");return !!(await deviceCache.get("api:/messages/"+id+"?load_images=true"));}',
                       arg=captured['other'])
        context.set_offline(True)
        page.reload()
        expect(page.locator('.message-row')).to_have_count(2)
        page.locator(f'[data-message="{captured["other"]}"]').click()
        expect(page.locator('.thread-message')).to_have_count(1)
        expect(page.locator('.thread-message').get_by_text('Parliamone domani.', exact=False).first).to_be_visible()
        browser.close()


def test_downloaded_body_search_is_local_and_survives_offline_restart(tmp_path):
    def prepare(app, received, sent):
        read_mail(app, received, sent)
        body = 'Only the downloaded body contains uniquebodyneedle.'
        mail = EmailMessage()
        mail.set_content(body)
        app.state.store.set_raw(sent, mail.as_bytes())
        app.state.store.execute('UPDATE messages SET body=? WHERE id=?', (body, sent))

    with service(tmp_path, prepare) as (url, sent), sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context()
        page = context.new_page()
        page.goto(url)
        page.locator(f'[data-message="{sent}"]').click()
        expect(page.get_by_text('Only the downloaded body contains uniquebodyneedle.', exact=True)).to_be_visible()
        wait_for_async(page, 'async()=>{const {deviceCache}=await import("/static/cache.js");return (await deviceCache.get("mailbox-replica"))?.rows.some(m=>m.search_terms?.includes("uniquebodyneedle."));}')
        page.evaluate('async()=>{const {replica}=await import("/static/replica.js");await replica.commit();}')
        page.evaluate('()=>navigator.serviceWorker.ready')
        context.set_offline(True)
        page.reload()
        expect(page.locator('.message-row')).to_have_count(2)
        page.locator('#search-input').fill('uniquebodyneedle')
        expect(page.locator('.message-row')).to_have_count(1, timeout=1000)
        expect(page.locator('.message-row')).to_have_attribute('data-message', sent)
        browser.close()


def test_offline_draft_save_delete_and_identity_are_local_then_sync(tmp_path):
    with service(tmp_path, read_mail) as (url, sent), sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context()
        page = context.new_page()
        warm(page, url, sent)
        context.set_offline(True)
        page.get_by_role('button', name='Impostazioni', exact=True).first.click()
        page.locator('[data-settings-tab="identity"]').click()
        page.locator('#identity-form [name="name"]').fill('Offline Owner')
        page.get_by_role('button', name='Salva identità', exact=True).click()
        expect(page.get_by_role('dialog')).to_have_count(0, timeout=1000)
        page.locator('[data-action="compose"]').click()
        page.locator('#compose-form [name="to"]').fill('customer@example.com')
        page.locator('#compose-form [name="subject"]').fill('Offline draft')
        write_body(page, 'Stored locally before sync')
        page.get_by_role('button', name='Salva bozza', exact=True).click()
        expect(page.locator('.draft-save-status')).to_contain_text('sul dispositivo', timeout=1000)
        page.get_by_role('button', name='Chiudi', exact=True).click()
        expect(page.locator('#compose-form')).to_have_count(0, timeout=1000)
        page.locator('[data-view="drafts"]').click()
        expect(page.locator('.draft-row')).to_have_count(1)
        page.reload()
        expect(page.locator('.message-row')).to_have_count(2)
        page.get_by_role('button', name='Impostazioni', exact=True).first.click()
        page.locator('[data-settings-tab="identity"]').click()
        expect(page.locator('#identity-form [name="name"]')).to_have_value('Offline Owner')
        page.get_by_role('button', name='Chiudi', exact=True).click()
        page.locator('[data-view="drafts"]').click()
        page.locator('.draft-row').click()
        page.get_by_role('button', name='Elimina bozza', exact=True).click()
        expect(page.locator('#compose-form')).to_have_count(0, timeout=1000)
        expect(page.locator('.draft-row')).to_have_count(0)
        context.set_offline(False)
        wait_for_async(page, 'async()=>(await (await fetch("/api/state")).json()).identity.name==="Offline Owner"', timeout=10000)
        wait_for_async(page, 'async()=>{const {deviceCache}=await import("/static/cache.js");return !(await deviceCache.get("pending-operations"))?.length;}', timeout=10000)
        assert page.request.get(url + '/api/drafts').json()['drafts'] == []
        browser.close()


def test_metadata_snapshot_is_private_paged_and_stable_when_pins_change(logged_in, account_data):
    store = logged_in.app.state.store
    account = store.add_account(account_data)
    for i in range(205):
        add(store, account, i + 100, thread=str(i), date=i // 2)
    page = logged_in.get('/api/client/messages').json()
    assert len(page['messages']) == 200 and page['next']
    ids = {m['id'] for m in page['messages']}
    first = page['messages'][0]
    store.patch_message(first['id'], {'pinned': True})
    second = logged_in.get('/api/client/messages', params=page['next']).json()
    assert len(second['messages']) == 5 and not second['next']
    assert ids.isdisjoint(m['id'] for m in second['messages'])
    assert all(not {'body', 'raw', 'html'} & m.keys() and m['has_inbox'] for m in page['messages'])
    assert logged_in.get('/api/client/messages?before_id=invalid').status_code == 422
    assert logged_in.get('/api/client/messages?before_date=nan&before_id=invalid').status_code == 422
    logged_in.cookies.clear()
    assert logged_in.get('/api/client/messages').status_code == 401


def test_rejected_preference_does_not_block_mail_sync_and_can_be_corrected(tmp_path):
    with service(tmp_path, read_mail) as (url, sent), sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        warm(page, url, sent)
        page.route('**/api/settings/identity', lambda route: route.fulfill(status=422, json={'detail': 'Check identity'}))
        page.get_by_role('button', name='Impostazioni', exact=True).first.click()
        page.locator('[data-settings-tab="identity"]').click()
        page.locator('#identity-form [name="name"]').fill('Rejected Owner')
        page.get_by_role('button', name='Salva identità', exact=True).click()
        expect(page.get_by_role('dialog')).to_have_count(0, timeout=1000)
        expect(page.locator('#sync-status')).to_contain_text('da controllare')
        page.get_by_role('button', name='Aggiungi ai preferiti', exact=True).click()
        wait_for_async(page, 'async id=>(await (await fetch("/api/messages/"+id+"/thread")).json()).messages.every(m=>m.starred)', arg=sent)
        wait_for_async(page, 'async()=>{const {deviceCache}=await import("/static/cache.js");const q=await deviceCache.get("pending-operations");return q.length===1&&!!q[0].error;}')
        page.unroute('**/api/settings/identity')
        page.get_by_role('button', name='Impostazioni', exact=True).first.click()
        page.locator('[data-settings-tab="identity"]').click()
        page.locator('#identity-form [name="name"]').fill('Corrected Owner')
        page.get_by_role('button', name='Salva identità', exact=True).click()
        wait_for_async(page, 'async()=>(await (await fetch("/api/state")).json()).identity.name==="Corrected Owner"')
        wait_for_async(page, 'async()=>{const {deviceCache}=await import("/static/cache.js");return !(await deviceCache.get("pending-operations"))?.length;}')
        expect(page.locator('#sync-status')).not_to_contain_text('da controllare')
        browser.close()


def test_queued_edit_finds_thread_after_provider_message_identity_changes(tmp_path):
    stores = []

    def prepare(app, received, sent):
        read_mail(app, received, sent)
        stores.append(app.state.store)

    with service(tmp_path, prepare) as (url, sent), sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        warm(page, url, sent)
        newer = 'new-provider-message-id'
        stores[0].execute('UPDATE messages SET id=? WHERE id=?', (newer, sent))
        page.get_by_role('button', name='Aggiungi ai preferiti', exact=True).click()
        wait_for_async(page, 'async id=>(await (await fetch("/api/messages/"+id+"/thread")).json()).messages.every(m=>m.starred)', arg=newer)
        wait_for_async(page, 'async()=>{const {deviceCache}=await import("/static/cache.js");return !(await deviceCache.get("pending-operations"))?.length;}')
        assert all(m['starred'] for m in stores[0].conversation(newer))
        browser.close()


def test_thread_lookup_is_authenticated_and_scoped_to_account(logged_in, account_data):
    store = logged_in.app.state.store
    account = store.add_account(account_data)
    message = add(store, account, 1)
    response = logged_in.get('/api/client/thread', params={'account': account, 'thread': 'conversation'})
    assert response.status_code == 200 and response.json()['message']['id'] == message
    assert not {'raw', 'body', 'html'} & response.json()['message'].keys()
    assert logged_in.get('/api/client/thread', params={'account': 'other', 'thread': 'conversation'}).status_code == 404
    logged_in.cookies.clear()
    assert logged_in.get('/api/client/thread', params={'account': account, 'thread': 'conversation'}).status_code == 401


def test_service_worker_retires_old_shell_and_refreshes_cached_client_assets(tmp_path):
    from fastapi.responses import Response
    from fastapi.routing import APIRoute

    version = {'name': 'original'}
    source = (Path(__file__).resolve().parent.parent / 'web/app.js').read_text()

    def prepare(app, received, sent):
        read_mail(app, received, sent)
        app.router.routes.insert(0, APIRoute('/static/app.js',
            lambda: Response(source + '\n// shell-version-' + version['name'], media_type='text/javascript'),
            methods=['GET']))

    with service(tmp_path, prepare) as (url, sent), sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(url + '/static/icon.svg')
        page.evaluate('()=>caches.open("milo-shell-v10").then(cache=>cache.put("/static/app.js",new Response("// obsolete-client")))')
        warm(page, url, sent)
        wait_for_async(page, 'async()=>{const keys=await caches.keys();return keys.includes("milo-shell-v36")&&!keys.includes("milo-shell-v10");}')
        version['name'] = 'updated'
        old = page.evaluate('()=>fetch("/static/app.js").then(response=>response.text())')
        assert 'shell-version-original' in old
        wait_for_async(page, 'async()=>{const response=await caches.match("/static/app.js");return (await response.text()).includes("shell-version-updated");}')
        browser.close()


def test_conversation_deleted_on_another_device_disappears_on_refresh(tmp_path):
    apps = []

    def prepare(app, received, sent):
        read_mail(app, received, sent)
        apps.append(app)

    with service(tmp_path, prepare) as (url, sent), sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(service_workers='block')
        page.goto(url)
        expect(page.locator('.message-row')).to_have_count(2)
        apps[0].state.store.trash_conversation(sent)
        expect(page.locator('.message-row')).to_have_count(1, timeout=15000)
        browser.close()


def test_unread_view_refreshes_when_read_state_changes(tmp_path):
    apps = []

    def prepare(app, received, sent):
        apps.append(app)

    with service(tmp_path, prepare) as (url, sent), sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(service_workers='block')
        page.goto(url)
        expect(page.locator('.message-row')).to_have_count(2)
        page.locator('[data-view="unread"]').click()
        expect(page.locator('.message-row')).to_have_count(2)
        store = apps[0].state.store
        # Read elsewhere (another device): the row leaves Da leggere on refresh.
        store.execute("UPDATE messages SET read=1 WHERE thread_id='other'")
        expect(page.locator('.message-row')).to_have_count(1, timeout=15000)
        store.execute('UPDATE messages SET read=1')
        expect(page.locator('.message-row')).to_have_count(0, timeout=15000)
        # Unread elsewhere: the row comes back without a reload.
        store.execute("UPDATE messages SET read=0 WHERE thread_id='other'")
        expect(page.locator('.message-row')).to_have_count(1, timeout=15000)
        # Reading here removes the row from the list as well.
        page.locator('.message-row').first.click()
        expect(page.locator('.message-row')).to_have_count(0, timeout=15000)
        browser.close()


def test_confirmation_code_is_copied_when_opening_the_mail(tmp_path):
    def prepare(app, received, sent):
        app.state.store.execute('UPDATE messages SET body=? WHERE id=?',
                                ('Il tuo codice di conferma è 482916. Non condividerlo con nessuno.', received))

    with service(tmp_path, prepare) as (url, sent), sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context()
        context.grant_permissions(['clipboard-read', 'clipboard-write'])
        page = context.new_page()
        page.goto(url)
        expect(page.locator('.message-row')).to_have_count(2)
        page.locator(f'[data-message="{sent}"]').click()
        expect(page.locator('.confirmation-code')).to_contain_text('482916', timeout=10000)
        wait_for_async(page, "async()=> (await navigator.clipboard.readText())==='482916'")
        browser.close()


def test_unread_view_refreshes_over_event_stream_when_live(tmp_path):
    apps = []

    def prepare(app, received, sent):
        apps.append(app)

    with service(tmp_path, prepare, live=True) as (url, sent), sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context()
        page = context.new_page()
        response = page.request.post(url + '/api/setup', data={
            'password': 'a secure test passphrase', 'bootstrap': apps[0].state.store.bootstrap})
        assert response.ok
        page.goto(url)
        expect(page.locator('.message-row')).to_have_count(2)
        page.locator('[data-view="unread"]').click()
        expect(page.locator('.message-row')).to_have_count(2)
        store = apps[0].state.store
        store.execute("UPDATE messages SET read=1 WHERE thread_id='other'")
        expect(page.locator('.message-row')).to_have_count(1, timeout=15000)
        store.execute("UPDATE messages SET read=0 WHERE thread_id='other'")
        expect(page.locator('.message-row')).to_have_count(2, timeout=15000)
        browser.close()
