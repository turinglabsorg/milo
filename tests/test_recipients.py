import sys
import threading
import time
from email.message import EmailMessage
from socket import socket

import pytest
import uvicorn
from playwright.sync_api import expect, sync_playwright

from milo.app import create_app
from milo.mail import parse_message


def sent_mail(store, account_id, uid, recipients, when, sender="You <you@example.com>"):
    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipients
    message["Subject"] = "Ciao"
    message["Message-ID"] = f"<sent-{uid}@example.com>"
    message["Date"] = "Sun, 11 Oct 2026 10:00:00 +0200"
    message.set_content("A dopo.")
    data = parse_message(message.as_bytes(), account_id, "Sent", "9", uid, sent=True)
    data["date"] = when
    data["recipients"] = recipients
    return store.upsert_message(data)


def test_recipients_require_authentication(client):
    assert client.get("/api/recipients").status_code == 401


def test_recent_recipients_then_contact_search(logged_in, account_data):
    store = logged_in.app.state.store
    account_id = store.add_account(account_data)
    sent_mail(store, account_id, 1, "Chiara Neri <chiara@example.com>", 100)
    sent_mail(store, account_id, 2, "Anna Rossi <anna@example.com>, you@example.com", 500)
    incoming = EmailMessage()
    incoming["From"] = "Marco Bianchi <marco@example.com>"
    incoming["To"] = "you@example.com"
    incoming["Subject"] = "Ciao"
    incoming["Message-ID"] = "<in-1@example.com>"
    incoming["Date"] = "Mon, 12 Oct 2026 10:00:00 +0200"
    incoming.set_content("Ci sei?")
    data = parse_message(incoming.as_bytes(), account_id, "INBOX", "1", 3)
    data["date"] = 400
    store.upsert_message(data)

    recent = logged_in.get("/api/recipients").json()["recipients"]
    assert [row["email"] for row in recent] == ["anna@example.com", "chiara@example.com"]
    assert recent[0]["name"] == "Anna Rossi"
    assert "you@example.com" not in {row["email"] for row in recent}

    found = logged_in.get("/api/recipients", params={"q": "mar"}).json()["recipients"]
    assert found[0]["email"] == "marco@example.com" and found[0]["name"] == "Marco Bianchi"
    assert logged_in.get("/api/recipients", params={"q": "rossi"}).json()["recipients"][0]["email"] == "anna@example.com"
    # % and _ are literal, so they do not match every contact.
    assert logged_in.get("/api/recipients", params={"q": "%"}).json()["recipients"] == []
    assert logged_in.get("/api/recipients", params={"q": "a_na"}).json()["recipients"] == []

    logged_in.app.state.features.sent(
        "draft-1", account_id, {"to": "Nuova <nuova@example.com>", "cc": "Copia <copia@example.com>"}, None, None)
    emailed = {row["email"] for row in logged_in.get("/api/recipients").json()["recipients"]}
    assert {"nuova@example.com", "copia@example.com"} <= emailed

    store.execute("DELETE FROM correspondents")
    store.set_progress("correspondents_done", False)
    store.set_progress("correspondents_seq", 0)
    store.backfill_correspondents()
    assert store.setting("correspondents_done") is True
    again = {row["email"] for row in store.recipient_suggestions("anna")}
    assert "anna@example.com" in again and "marco@example.com" not in {row["email"] for row in store.recipient_suggestions("")}
    restored = store.rows("SELECT COUNT(*) AS count FROM correspondents")[0]["count"]
    store.set_progress("correspondents_done", False)
    store.set_progress("correspondents_seq", 0)
    store.backfill_correspondents()
    assert store.rows("SELECT COUNT(*) AS count FROM correspondents")[0]["count"] == restored


def test_composer_offers_recent_people_and_inserts_a_contact(tmp_path):
    app = create_app(tmp_path / "ui", demo=True)
    store = app.state.store
    account_id = store.accounts()[0]["id"]
    sent_mail(store, account_id, 50, "Anna Rossi <anna@example.com>", time.time())
    with socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.02)
    assert server.started
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 800}, service_workers="block")
            page.goto(f"http://127.0.0.1:{port}", wait_until="networkidle")
            page.locator('[data-action="compose"]').click()
            field = page.locator('#compose-form [name="to"]')
            field.click()
            expect(page.locator(".recipient-option").filter(has_text="Anna Rossi")).to_be_visible()
            field.fill("mar")
            option = page.locator(".recipient-option").filter(has_text="Marco Bianchi")
            expect(option).to_be_visible()
            option.click()
            expect(field).to_have_value("Marco Bianchi <marco@example.com>, ")
            page.locator(".recipient-option").filter(has_text="Anna Rossi").click()
            expect(field).to_have_value("Marco Bianchi <marco@example.com>, Anna Rossi <anna@example.com>, ")
            browser.close()
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        assert not thread.is_alive()


@pytest.mark.parametrize("engine", ["chromium", pytest.param(
    "webkit", marks=pytest.mark.skipif(sys.platform != "darwin", reason="macOS WebKit coverage"))])
def test_forward_from_recipient_suggestions_reaches_transport(tmp_path, monkeypatch, engine):
    from test_responsive_inbox import service

    from milo.mail import build_message

    context, submitted = {}, []

    def prepare(app, received, sent):
        store = app.state.store
        context["bootstrap"] = store.bootstrap
        store.note_addresses("Recipient <recipient@example.com>", time.time())
        store.note_addresses("Copy <copy@example.com>", time.time())

    def deliver(account, draft, original=None, attachments=()):
        message = build_message(account, draft, original, attachments)
        submitted.append(message)
        return message

    monkeypatch.setattr("milo.app.send_mail", deliver)
    with service(tmp_path, prepare, live=True) as (url, sent), sync_playwright() as playwright:
        browser = getattr(playwright, engine).launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000}, service_workers="block")
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        assert page.request.post(url + "/api/setup", data={
            "password": "isolated test password", "bootstrap": context["bootstrap"],
        }).status == 200
        page.goto(url)
        page.locator(f'[data-message="{sent}"]').click()
        page.get_by_role("button", name="Inoltra", exact=True).click()
        form = page.locator("#compose-form")
        for field, label in [("to", "Recipient"), ("cc", "Copy")]:
            form.locator(f'[name="{field}"]').fill(label)
            page.locator(".recipient-option").filter(has_text=label).click()
        expect(form.locator('[name="to"]')).to_have_value("Recipient <recipient@example.com>, ")
        expect(form.locator('[name="cc"]')).to_have_value("Copy <copy@example.com>, ")
        form.get_by_role("button", name="Invia messaggio").click()
        expect(page.locator("#toast")).to_contain_text("Messaggio in partenza")
        deadline = time.time() + 25
        while time.time() < deadline and page.request.get(url + "/api/drafts").json()["drafts"]:
            page.wait_for_timeout(250)
        assert page.request.get(url + "/api/drafts").json()["drafts"] == []
        assert len(submitted) == 1
        assert str(submitted[0]["To"]) == "Recipient <recipient@example.com>"
        assert str(submitted[0]["Cc"]) == "Copy <copy@example.com>"
        assert "Messaggio inoltrato" in submitted[0].get_body(("plain",)).get_content()
        assert not errors
        browser.close()
