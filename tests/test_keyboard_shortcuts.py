import pytest
from browser_helpers import type_body, write_body
from playwright.sync_api import expect, sync_playwright
from test_conversations import add
from test_responsive_inbox import service


def test_favorite_shortcut_works_in_html_and_preserves_typing(tmp_path):
    with service(tmp_path) as (url, sent), sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(service_workers='block')
        errors, writes = [], []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('request', lambda request: writes.append(request.method)
                if request.method in {'PATCH', 'DELETE'} else None)
        page.goto(url)
        page.locator(f'[data-message="{sent}"]').click()
        frame = page.frame_locator('.email-html')
        expect(frame.get_by_text('HTML reply', exact=True)).to_be_visible()
        expect(page.get_by_role('button', name='Aggiungi ai preferiti', exact=True)).to_be_visible()
        frame.locator('body').evaluate('(body)=>{body.tabIndex=-1;body.focus();}')
        page.keyboard.press('p')
        expect(page.get_by_role('button', name='Rimuovi dai preferiti', exact=True)).to_be_visible()
        page.wait_for_function('async id=>(await (await fetch("/api/messages/"+id+"/thread")).json()).messages.every(m=>m.starred)', arg=sent)
        page.locator('.reading-toolbar').click(position={'x': 4, 'y': 4})
        page.keyboard.press('Shift+P')
        expect(page.get_by_role('button', name='Aggiungi ai preferiti', exact=True)).to_be_visible()
        page.wait_for_function('async id=>(await (await fetch("/api/messages/"+id+"/thread")).json()).messages.every(m=>!m.starred)', arg=sent)
        before = len(writes)
        for flags in ({'ctrlKey': True}, {'metaKey': True}, {'altKey': True}, {'repeat': True}, {'isComposing': True}):
            page.evaluate('(flags)=>document.body.dispatchEvent(new KeyboardEvent("keydown",{key:"p",bubbles:true,cancelable:true,...flags}))', flags)
        page.locator('#search-input').focus()
        page.keyboard.press('p')
        page.keyboard.press('Backspace')
        page.keyboard.press('Delete')
        expect(page.locator('#search-input')).to_have_value('')
        page.get_by_role('button', name='Impostazioni', exact=True).first.click()
        page.get_by_role('dialog').get_by_role('button', name='Chiudi', exact=True).focus()
        page.keyboard.press('p')
        page.keyboard.press('Delete')
        expect(page.get_by_role('dialog')).to_be_visible()
        page.keyboard.press('Escape')
        page.locator(f'[data-message="{sent}"]').click()
        page.get_by_role('button', name='Rispondi', exact=True).click()
        write_body(page, 'Keep this draft')
        type_body(page, 'p')
        page.keyboard.press('Backspace')
        expect(page.locator('[name="body"]')).to_have_value('Keep this draft')
        page.locator('.reading-toolbar').click(position={'x': 4, 'y': 4})
        page.keyboard.press('p')
        page.keyboard.press('Delete')
        expect(page.locator('#compose-form')).to_be_visible()
        page.get_by_role('button', name='Chiudi', exact=True).click()
        page.evaluate('()=>{const editor=document.createElement("div");editor.contentEditable="true";editor.id="editable-fixture";editor.textContent="Editable content";document.body.append(editor);editor.focus();}')
        page.keyboard.press('p')
        page.keyboard.press('Backspace')
        page.keyboard.press('Delete')
        page.evaluate('()=>document.querySelector("#editable-fixture").remove()')
        expect(page.locator('.message-row')).to_have_count(2)
        expect(page.get_by_role('button', name='Aggiungi ai preferiti', exact=True)).to_be_visible()
        assert len(writes) == before and not errors
        browser.close()


@pytest.mark.parametrize('key', ['Backspace', 'Delete'])
def test_delete_shortcut_removes_conversation_before_response(tmp_path, key):
    with service(tmp_path) as (url, sent), sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(service_workers='block')
        page.goto(url)
        page.keyboard.press(key)
        expect(page.locator('.message-row')).to_have_count(2)
        page.locator(f'[data-message="{sent}"]').click()
        expect(page.frame_locator('.email-html').get_by_text('HTML reply', exact=True)).to_be_visible()
        deleted = []

        def delay_response(route):
            if route.request.method == 'DELETE':
                expect(page.locator(f'[data-message="{sent}"]')).to_have_count(0)
                deleted.append(route.request.url)
            route.continue_()

        page.route('**/api/messages/*/thread', delay_response)
        page.frame_locator('.email-html').locator('body').evaluate('(body)=>{body.tabIndex=-1;body.focus();}')
        page.keyboard.press(key)
        expect(page.locator('.message-row')).to_have_count(1)
        expect(page.locator('.thread-message')).to_have_count(1)
        expect(page.locator('#toast')).to_contain_text('Conversazione eliminata')
        # The delete leaves through the client queue after the UI updates: wait for it.
        for _ in range(100):
            if deleted:
                break
            page.wait_for_timeout(50)
        assert len(deleted) == 1
        for _ in range(100):  # let the server apply it before reloading
            if all(m['id'] != sent for m in page.request.get(url + '/api/messages').json()['messages']):
                break
            page.wait_for_timeout(50)
        page.reload()
        expect(page.locator('.message-row')).to_have_count(1)
        assert not page.request.get(url + '/api/messages').json()['messages'][0]['id'] == sent
        browser.close()


def test_all_accounts_restores_unified_list_and_clears_previous_selection(tmp_path, account_data):
    context = {}

    def prepare(app, received, sent):
        store = app.state.store
        context['first'] = store.accounts()[0]['id']
        context['second'] = store.add_account({**account_data, 'name': 'Second mailbox',
                                             'email': 'second@example.com', 'enabled': False})
        add(store, context['second'], 40, thread='second-account', date=400)

    with service(tmp_path, prepare) as (url, sent), sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(service_workers='block')
        page.goto(url)
        expect(page.locator('.message-row')).to_have_count(3)
        expect(page.locator('.all-accounts')).to_have_attribute('aria-pressed', 'true')
        page.locator(f'[data-account="{context["first"]}"]').click()
        expect(page.locator('.message-row')).to_have_count(2)
        page.locator(f'[data-message="{sent}"]').click()
        expect(page.locator('.thread-message')).to_have_count(2)
        page.locator(f'[data-account="{context["second"]}"]').click()
        expect(page.locator('.message-row')).to_have_count(1)
        expect(page.locator('.thread-message')).to_have_count(0)
        page.get_by_role('button', name='Tutti gli account', exact=True).click()
        expect(page.locator('.message-row')).to_have_count(3)
        expect(page.locator('.all-accounts')).to_have_attribute('aria-pressed', 'true')
        page.reload()
        expect(page.locator('.message-row')).to_have_count(3)
        browser.close()
