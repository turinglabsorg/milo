import time

from playwright.sync_api import expect, sync_playwright
from test_conversations import add
from test_responsive_inbox import service

from milo.mail import build_message

CONTEXT = {}


def prepare(app, received, sent):
    store, features = app.state.store, app.state.features
    account_id = store.accounts()[0]["id"]
    unanswered = store.rows("SELECT id FROM messages WHERE thread_id='other'")[0]["id"]
    features.sync_todos(unanswered, {"priority": "high", "action_items": ["Confermare la riunione"]})
    store.set_setting("signatures", {account_id: "Sam Taylor"})
    store.set_setting("templates", [{"name": "Grazie", "body": "Grazie mille, ti aggiorno a breve."}])
    features.set_screener(True)
    newcomer = add(store, account_id, 9, thread="newcomer", date=time.time() + 5)
    store.execute("UPDATE messages SET sender='Nuova Persona',sender_email='nuova@example.com' WHERE id=?", (newcomer,))
    CONTEXT["bootstrap"] = store.bootstrap


def test_daily_features_in_the_client(tmp_path, monkeypatch):
    sent_mail = []
    monkeypatch.setattr("milo.app.send_mail", lambda account, draft, original=None, attachments=():
                        sent_mail.append(build_message(account, draft, original)) or sent_mail[-1])
    with service(tmp_path, prepare, live=True) as (url, sent), sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000}, service_workers="block")
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        assert page.request.post(url + "/api/setup", data={"password": "isolated test password",
                                                           "bootstrap": CONTEXT["bootstrap"]}).status == 200
        page.goto(url)
        expect(page.locator(".message-row")).to_have_count(2)

        page.locator('.nav-button[data-view="todo"]').click()
        expect(page.locator(".todo-text")).to_have_text(["Confermare la riunione"])
        page.locator(".todo-check").click()
        expect(page.locator(".todo-row")).to_have_count(0)
        expect(page.locator("#toast")).to_contain_text("Fatto.")

        page.locator('.nav-button[data-view="screener"]').click()
        expect(page.locator(".screener-row")).to_have_count(1)
        expect(page.locator(".screener-row")).to_contain_text("nuova@example.com")
        page.locator(".screener-row").get_by_role("button", name="Approva").click()
        expect(page.locator(".screener-row")).to_have_count(0)

        page.keyboard.press("Control+k")
        page.locator("#palette-input").fill("bozz")
        page.keyboard.press("Enter")
        expect(page.locator(".title-row h1")).to_have_text("Bozze")

        page.locator('.nav-button[data-view="inbox"]').click()
        expect(page.locator(".message-row")).to_have_count(3)
        rows = page.locator(".message-row")
        rows.nth(0).click(modifiers=["Control"])
        rows.nth(1).click(modifiers=["Control"])
        expect(page.locator(".bulk-bar strong")).to_have_text("2 selezionate")
        page.locator('[data-bulk="archive"]').click()
        expect(page.locator(".message-row")).to_have_count(1)

        page.keyboard.press("c")
        form = page.locator("#compose-form")
        expect(form.locator('[name="body"]')).to_have_value("\n\n-- \nSam Taylor")
        form.locator('[name="to"]').fill("anna@example.com")
        form.locator('[name="subject"]').fill("Aggiornamento")
        form.locator(".template-select").select_option(label="Grazie")
        expect(form.locator('[name="body"]')).to_have_value("Grazie mille, ti aggiorno a breve.\n\n-- \nSam Taylor")
        form.locator('[name="followup_days"]').select_option("3")
        form.get_by_role("button", name="Invia messaggio").click()
        expect(page.locator("#toast")).to_contain_text("Messaggio in partenza")
        page.locator(".toast-action").click()
        expect(page.locator("#compose-form [name='subject']")).to_have_value("Aggiornamento")
        assert not page.request.get(url + "/api/drafts").json()["drafts"][0]["scheduled"]

        page.locator("#compose-form").get_by_role("button", name="Invia messaggio").click()
        expect(page.locator("#toast")).to_contain_text("Messaggio in partenza")
        deadline = time.time() + 20
        while time.time() < deadline and not page.request.get(url + "/api/drafts").json()["drafts"] == []:
            page.wait_for_timeout(500)
        assert page.request.get(url + "/api/drafts").json()["drafts"] == []
        assert len(sent_mail) == 1 and sent_mail[0]["Subject"] == "Aggiornamento"

        page.keyboard.press("?")
        expect(page.locator(".shortcut-list")).to_contain_text("Rispondi a tutti")
        page.keyboard.press("Escape")
        assert not errors
        browser.close()
