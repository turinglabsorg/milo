import json
import os
import time
from email.message import EmailMessage

from milo.features import public_https
from milo.mail import parse_message


def mail(subject="Hello", msg_id="<m1@example.com>", sender="Giulia <giulia@example.com>", headers=None,
         references=None, date="Sun, 11 Oct 2026 10:00:00 +0200"):
    message = EmailMessage()
    message["From"] = sender
    message["To"] = "you@example.com"
    message["Subject"] = subject
    message["Message-ID"] = msg_id
    message["Date"] = date
    if references:
        message["References"] = references
    for key, value in (headers or {}).items():
        message[key] = value
    message.set_content("Ciao, " + subject)
    return message.as_bytes()


def add(store, account_id, uid, **kwargs):
    date = kwargs.pop("when", time.time())
    category = kwargs.pop("category", None)
    data = parse_message(mail(**kwargs), account_id, "INBOX", "1", uid)
    data["date"] = date
    if category:
        data["category"] = category
    return store.upsert_message(data)


def setup_account(client, account_data):
    store = client.app.state.store
    return store, store.add_account(account_data)


def fake_smtp(monkeypatch, sent):
    from milo.mail import build_message

    def send(account, draft, original=None, attachments=()):
        message = build_message(account, draft, original, attachments)
        sent.append(message)
        return message
    monkeypatch.setattr("milo.app.send_mail", send)


def save_draft(client, account_id, **fields):
    body = {"account_id": account_id, "to": "anna@example.com", "subject": "Proposta", "body": "Ecco la proposta", **fields}
    response = client.put("/api/drafts", json=body)
    assert response.status_code == 200
    return response.json()["id"]


def test_scheduled_send_waits_can_be_undone_and_then_sends(logged_in, account_data, monkeypatch):
    store, account_id = setup_account(logged_in, account_data)
    sent = []
    fake_smtp(monkeypatch, sent)
    draft_id = save_draft(logged_in, account_id)
    assert logged_in.put(f"/api/drafts/{draft_id}/schedule", json={"send_at": time.time() + 600}).status_code == 200
    logged_in.app.state.feature_tick(False)
    assert not sent
    drafts = logged_in.get("/api/drafts").json()["drafts"]
    assert drafts[0]["scheduled"]["send_at"] > time.time()
    assert logged_in.delete(f"/api/drafts/{draft_id}/schedule").status_code == 200
    assert logged_in.delete(f"/api/drafts/{draft_id}/schedule").status_code == 409
    assert logged_in.put(f"/api/drafts/{draft_id}/schedule", json={"send_at": time.time() - 1}).status_code == 200
    logged_in.app.state.feature_tick(False)
    assert len(sent) == 1 and sent[0]["Subject"] == "Proposta"
    assert not logged_in.get("/api/drafts").json()["drafts"]
    assert not store.rows("SELECT * FROM scheduled")


def test_scheduled_failure_is_kept_and_never_retried(logged_in, account_data, monkeypatch):
    _, account_id = setup_account(logged_in, account_data)
    calls = []

    def broken(account, draft, original=None, attachments=()):
        calls.append(draft)
        raise OSError("down")
    monkeypatch.setattr("milo.app.send_mail", broken)
    draft_id = save_draft(logged_in, account_id)
    logged_in.put(f"/api/drafts/{draft_id}/schedule", json={"send_at": time.time() - 1})
    logged_in.app.state.feature_tick(False)
    logged_in.app.state.feature_tick(False)
    assert len(calls) == 1
    draft = logged_in.get("/api/drafts").json()["drafts"][0]
    assert "non viene ripetuto" in draft["scheduled"]["error"]


def test_unanswered_mail_becomes_a_follow_up_todo(logged_in, account_data, monkeypatch):
    store, account_id = setup_account(logged_in, account_data)
    sent = []
    fake_smtp(monkeypatch, sent)
    draft_id = save_draft(logged_in, account_id)
    logged_in.put(f"/api/drafts/{draft_id}/schedule", json={"send_at": time.time() - 1, "followup_days": 3})
    logged_in.app.state.feature_tick(False)
    followup = store.rows("SELECT * FROM followups")[0]
    assert followup["due"] > time.time() + 2 * 86400
    store.execute("UPDATE followups SET due=0")
    logged_in.app.state.feature_tick(True)
    todos = logged_in.get("/api/todos").json()["todos"]
    assert todos[0]["kind"] == "followup" and todos[0]["text"] == "Nessuna risposta: Proposta"
    assert logged_in.get("/api/state").json()["counts"]["todo"] == 1


def test_a_reply_resolves_the_follow_up(logged_in, account_data, monkeypatch):
    store, account_id = setup_account(logged_in, account_data)
    sent = []
    fake_smtp(monkeypatch, sent)
    draft_id = save_draft(logged_in, account_id)
    logged_in.put(f"/api/drafts/{draft_id}/schedule", json={"send_at": time.time() - 1, "followup_days": 1})
    logged_in.app.state.feature_tick(False)
    add(store, account_id, 7, subject="Re: Proposta", msg_id="<answer@example.com>", sender="Anna <anna@example.com>",
        references=sent[0]["Message-ID"], when=time.time() + 5)
    logged_in.app.state.feature_tick(True)
    assert store.rows("SELECT resolved FROM followups")[0]["resolved"]
    assert not logged_in.get("/api/todos").json()["todos"]


def test_analysis_action_items_become_todos_and_can_be_completed(logged_in, account_data):
    store, account_id = setup_account(logged_in, account_data)
    message_id = add(store, account_id, 1)
    features = logged_in.app.state.features
    features.sync_todos(message_id, {"priority": "high", "action_items": ["Inviare il preventivo", "Fissare call"]})
    todos = logged_in.get("/api/todos").json()["todos"]
    assert [todo["text"] for todo in todos] == ["Inviare il preventivo", "Fissare call"]
    assert logged_in.patch(f"/api/todos/{todos[0]['id']}", json={"done": True}).status_code == 200
    features.sync_todos(message_id, {"priority": "high", "action_items": ["Inviare il preventivo", "Rispondere"]})
    assert [todo["text"] for todo in logged_in.get("/api/todos").json()["todos"]] == ["Rispondere"]
    assert logged_in.patch("/api/todos/missing", json={"done": True}).status_code == 404
    features.sync_todos(message_id, {"priority": "low", "action_items": ["Nessuna azione richiesta", "Rispondere"]})
    assert [todo["text"] for todo in logged_in.get("/api/todos").json()["todos"]] == ["Rispondere"]
    store.execute("UPDATE messages SET archived=1 WHERE id=?", (message_id,))
    assert logged_in.get("/api/todos").json()["todos"] == [] and logged_in.get("/api/state").json()["counts"]["todo"] == 0


def test_blocked_sender_is_archived_now_and_later(logged_in, account_data):
    store, account_id = setup_account(logged_in, account_data)
    first = add(store, account_id, 1, sender="Spam <spam@example.com>", msg_id="<s1@example.com>")
    response = logged_in.patch("/api/senders/Spam@Example.com", json={"status": "blocked"})
    assert response.status_code == 200 and response.json()["email"] == "spam@example.com"
    assert store.message(first)["archived"]
    later = add(store, account_id, 2, sender="Spam <spam@example.com>", msg_id="<s2@example.com>", subject="Again")
    logged_in.app.state.feature_tick(True)
    assert store.message(later)["archived"]
    assert store.rows("SELECT kind FROM outbox WHERE message_id=?", (later,))[0]["kind"] == "archived"


def test_vip_and_newsletter_senders(logged_in, account_data):
    store, account_id = setup_account(logged_in, account_data)
    for uid in range(3):
        add(store, account_id, uid, sender="News <news@brand.example>", msg_id=f"<n{uid}@x>", subject=f"N{uid}",
            category="newsletters")
    add(store, account_id, 9, sender="Boss <boss@example.com>", msg_id="<b@x>")
    logged_in.patch("/api/senders/boss@example.com", json={"vip": True})
    assert logged_in.get("/api/state").json()["vips"] == ["boss@example.com"]
    senders = logged_in.get("/api/senders/newsletters").json()["senders"]
    assert senders[0]["email"] == "news@brand.example" and senders[0]["threads"] == 3 and senders[0]["unread"] == 3
    response = logged_in.post("/api/senders/news@brand.example/action", json={"action": "trash"})
    assert response.json()["conversations"] == 3
    assert not logged_in.get("/api/senders/newsletters").json()["senders"]


def test_screener_holds_only_new_unknown_senders(logged_in, account_data):
    store, account_id = setup_account(logged_in, account_data)
    add(store, account_id, 1, sender="Old <old@example.com>", msg_id="<old@x>", when=time.time() - 86400)
    assert logged_in.put("/api/settings/screener", json={"enabled": True}).json()["enabled"]
    add(store, account_id, 2, sender="New <new@example.com>", msg_id="<new@x>", when=time.time() + 1)
    add(store, account_id, 3, sender="Old <old@example.com>", msg_id="<old2@x>", when=time.time() + 1)
    sent = parse_message(mail(sender="you@example.com", msg_id="<mine@x>"), account_id, "Sent", "1", 4, sent=True)
    sent.update(recipients="Friend <friend@example.com>", date=time.time())
    store.upsert_message(sent)
    add(store, account_id, 5, sender="Friend <friend@example.com>", msg_id="<friend@x>", when=time.time() + 2)
    logged_in.app.state.features._screening = (0, [])
    state = logged_in.get("/api/state").json()
    assert state["screener"]["pending"] == ["new@example.com"] and state["counts"]["screener"] == 1
    logged_in.patch("/api/senders/new@example.com", json={"status": "approved"})
    assert logged_in.get("/api/state").json()["screener"]["pending"] == []


def test_unsubscribe_options_and_one_click(logged_in, account_data, monkeypatch):
    store, account_id = setup_account(logged_in, account_data)
    headers = {"List-Unsubscribe": "<mailto:leave@brand.example?subject=stop>, <https://brand.example/u/1>",
               "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"}
    message_id = add(store, account_id, 1, headers=headers, sender="News <news@brand.example>")
    detail = logged_in.get(f"/api/messages/{message_id}").json()
    assert detail["unsubscribe"] == {"one_click": True, "url": "https://brand.example/u/1",
                                     "mailto": "mailto:leave@brand.example?subject=stop"}
    posted = []
    monkeypatch.setattr("milo.features.public_https", lambda url: True)
    monkeypatch.setattr("milo.features.httpx.post", lambda url, **kwargs: posted.append((url, kwargs)) or
                        type("R", (), {"status_code": 200})())
    assert logged_in.post(f"/api/messages/{message_id}/unsubscribe").json() == {"method": "one-click"}
    assert posted[0][0] == "https://brand.example/u/1" and posted[0][1]["data"] == {"List-Unsubscribe": "One-Click"}
    assert store.rows("SELECT unsubscribed FROM senders WHERE email='news@brand.example'")[0]["unsubscribed"]


def test_unsubscribe_by_mail_and_unsafe_links(logged_in, account_data, monkeypatch):
    store, account_id = setup_account(logged_in, account_data)
    sent = []
    fake_smtp(monkeypatch, sent)
    message_id = add(store, account_id, 1, headers={"List-Unsubscribe": "<mailto:leave@brand.example?subject=stop>"})
    assert logged_in.post(f"/api/messages/{message_id}/unsubscribe").json() == {"method": "email"}
    assert sent[0]["To"] == "leave@brand.example" and sent[0]["Subject"] == "stop"
    assert not public_https("https://127.0.0.1/unsubscribe")
    assert not public_https("http://example.com/unsubscribe")
    assert not public_https("https://localhost:8443/u")


def test_signatures_templates_and_validation(logged_in, account_data):
    _, account_id = setup_account(logged_in, account_data)
    response = logged_in.put("/api/settings/signatures", json={"signatures": {account_id: "Seb", "unknown": "x"}})
    assert response.json() == {"signatures": {account_id: "Seb"}}
    templates = [{"name": "Grazie", "body": "Grazie, ti aggiorno a breve."}]
    assert logged_in.put("/api/settings/templates", json={"templates": templates}).status_code == 200
    state = logged_in.get("/api/state").json()
    assert state["signatures"] == {account_id: "Seb"} and state["templates"] == templates
    assert logged_in.put("/api/settings/templates", json={"templates": [{"name": "", "body": "x"}]}).status_code == 422


def test_ai_suggestions_and_questions_use_archive(logged_in, account_data, monkeypatch):
    store, account_id = setup_account(logged_in, account_data)
    contract = add(store, account_id, 1, subject="Contratto firmato", sender="Marco <marco@example.com>")
    add(store, account_id, 2, subject="Pranzo", msg_id="<p@x>")
    ai = logged_in.app.state.ai
    prompts = []

    def chat(prompt, schema, system=None):
        prompts.append(prompt)
        if "replies" in schema["properties"]:
            return {"replies": ["Perfetto, grazie!", "Ci sentiamo domani.", "Ti confermo entro sera.", "extra"]}
        if "keywords" in schema["properties"]:
            return {"keywords": ["contratto", "Marco"]}
        return {"answer": "Marco ha mandato il contratto firmato.", "message_ids": [contract]}
    monkeypatch.setattr(ai, "chat", chat)
    assert logged_in.post(f"/api/messages/{contract}/suggestions").json()["replies"] == [
        "Perfetto, grazie!", "Ci sentiamo domani.", "Ti confermo entro sera."]
    answer = logged_in.post("/api/ask", json={"question": "Quando mi ha mandato Marco il contratto?"}).json()
    assert answer["answer"].startswith("Marco") and answer["sources"][0]["id"] == contract
    assert "Pranzo" not in prompts[-1]


def test_account_removal_purges_mail_and_drafts(logged_in, account_data):
    store, account_id = setup_account(logged_in, account_data)
    message_id = add(store, account_id, 1)
    save_draft(logged_in, account_id)
    assert logged_in.delete(f"/api/accounts/{account_id}").status_code == 202
    assert not logged_in.get("/api/state").json()["accounts"]
    assert not store.rows("SELECT id FROM messages WHERE id=?", (message_id,))
    path = store.blobs.path(message_id)
    os.utime(path, (time.time() - 7200, time.time() - 7200))
    store.sweep_blobs()
    assert not path.exists()
    assert not store.rows("SELECT id FROM drafts")
    assert not store.rows("SELECT id FROM accounts")


def test_configuration_backup_restores_into_a_fresh_archive(logged_in, account_data, tmp_path):
    from fastapi.testclient import TestClient

    from milo.app import create_app
    store, account_id = setup_account(logged_in, account_data)
    message_id = add(store, account_id, 1)
    store.execute("UPDATE messages SET analysis=?,category='updates',pinned=1 WHERE id=?",
                  (json.dumps({"summary": "S", "action_items": []}), message_id))
    logged_in.app.state.features.sync_todos(message_id, {"priority": "normal", "action_items": ["Chiamare"]})
    logged_in.put("/api/settings/templates", json={"templates": [{"name": "Ok", "body": "Va bene"}]})
    logged_in.patch("/api/senders/boss@example.com", json={"vip": True})
    save_draft(logged_in, account_id)
    exported = logged_in.get("/api/backup")
    assert "attachment" in exported.headers["content-disposition"]
    data = exported.json()
    assert "password" not in json.dumps(data["accounts"]) and data["accounts"][0]["email"] == "you@example.com"

    with TestClient(create_app(tmp_path / "fresh")) as fresh:
        fresh.post("/api/setup", json={"password": "a secure test passphrase", "bootstrap": fresh.app.state.store.bootstrap})
        other = fresh.app.state.store
        other_account = other.add_account(account_data)
        restored_message = add(other, other_account, 1)
        counts = fresh.post("/api/backup/restore", content=json.dumps(data)).json()
        assert counts["messages"] == 1 and counts["todos"] == 1 and counts["drafts"] == 1
        restored = other.message(restored_message)
        assert restored["category"] == "updates" and restored["pinned"] and restored["analysis"]["summary"] == "S"
        state = fresh.get("/api/state").json()
        assert state["templates"] == [{"name": "Ok", "body": "Va bene"}] and state["vips"] == ["boss@example.com"]
        assert fresh.post("/api/backup/restore", content=b'{"format":"other"}').status_code == 422


def test_pdf_attachments_preview_inline_only_on_request(logged_in, account_data):
    store, account_id = setup_account(logged_in, account_data)
    message = EmailMessage()
    message["From"] = "a@example.com"
    message["Subject"] = "Doc"
    message["Message-ID"] = "<pdf@x>"
    message.set_content("Allegato")
    message.add_attachment(b"%PDF-1.4 test", maintype="application", subtype="pdf", filename="doc.pdf")
    message_id = store.upsert_message(parse_message(message.as_bytes(), account_id, "INBOX", "1", 1))
    index = logged_in.get(f"/api/messages/{message_id}").json()["attachments"][0]["index"]
    download = logged_in.get(f"/api/messages/{message_id}/attachments/{index}")
    assert download.headers["content-type"] == "application/octet-stream"
    preview = logged_in.get(f"/api/messages/{message_id}/attachments/{index}?preview=true")
    assert preview.headers["content-type"] == "application/pdf" and preview.headers["content-disposition"].startswith("inline")


def test_outgoing_attachments_are_sent_and_cleaned_up(logged_in, account_data, monkeypatch):
    store, account_id = setup_account(logged_in, account_data)
    sent = []
    fake_smtp(monkeypatch, sent)
    draft_id = "8f1c2d3e-aaaa-bbbb-cccc-1234567890ab"
    upload = logged_in.post(f"/api/drafts/{draft_id}/attachments?name=Preventivo%20finale.pdf",
                            content=b"%PDF-1.7 test", headers={"Content-Type": "application/pdf"})
    assert upload.status_code == 200
    first = upload.json()
    assert first["name"] == "Preventivo finale.pdf" and first["size"] == 13
    second = logged_in.post(f"/api/drafts/{draft_id}/attachments?name=../../nota.txt",
                            content=b"ciao", headers={"Content-Type": "text/plain"}).json()
    assert second["name"] == ".. .. nota.txt"
    assert logged_in.delete(f"/api/drafts/{draft_id}/attachments/{second['id']}").status_code == 200
    assert logged_in.delete(f"/api/drafts/{draft_id}/attachments/{second['id']}").status_code == 404
    assert logged_in.post("/api/drafts/..%2F..%2Fetc/attachments?name=x", content=b"x").status_code == 404
    assert logged_in.post(f"/api/drafts/{draft_id}/attachments?name=vuoto", content=b"").status_code == 422
    monkeypatch.setattr("milo.store.ATTACHMENT_LIMIT", 20)
    too_big = logged_in.post(f"/api/drafts/{draft_id}/attachments?name=big.bin", content=b"x" * 10)
    assert too_big.status_code == 413
    save_draft(logged_in, account_id, id=draft_id)
    listed = logged_in.get("/api/drafts").json()["drafts"][0]
    assert [item["name"] for item in listed["attachments"]] == ["Preventivo finale.pdf"]
    assert logged_in.post(f"/api/drafts/{draft_id}/send").status_code == 200
    parts = [part for part in sent[0].iter_attachments()]
    assert [(part.get_filename(), part.get_content_type(), part.get_content()) for part in parts] == [
        ("Preventivo finale.pdf", "application/pdf", b"%PDF-1.7 test")]
    assert store.draft_attachments(draft_id) == []
    assert not store.attachment_path(draft_id).exists()


def test_orphaned_attachments_are_swept(store):
    store.add_draft_attachment("gone", "a.txt", "text/plain", b"a")
    store.add_draft_attachment("kept", "b.txt", "text/plain", b"b")
    store.execute("INSERT INTO drafts VALUES(?,?,?)", ("kept", "{}", time.time()))
    assert store.sweep_draft_attachments(older_than=-1) == 1
    assert store.draft_attachments("gone") == [] and len(store.draft_attachments("kept")) == 1
    assert not store.attachment_path("gone").exists()


def test_desktop_notifications_follow_arrival_order_and_push_rules(logged_in, account_data):
    store, account_id = setup_account(logged_in, account_data)
    add(store, account_id, 1, subject="Vecchia", msg_id="<old@example.com>")
    start = logged_in.get("/api/notifications").json()
    assert start["messages"] == [] and start["cursor"] > 0
    add(store, account_id, 2, subject="Cena sabato?", msg_id="<n1@example.com>")
    add(store, account_id, 3, subject="Offerta", msg_id="<n2@example.com>", sender="Shop <shop@example.com>",
        category="newsletters")
    add(store, account_id, 4, subject="Spam", msg_id="<n3@example.com>", sender="Spam <spam@example.com>")
    add(store, account_id, 5, subject="Ieri", msg_id="<n4@example.com>", when=time.time() - 7200)
    logged_in.app.state.features.set_sender("spam@example.com", status="blocked")
    result = logged_in.get("/api/notifications", params={"after": start["cursor"]}).json()
    assert [message["subject"] for message in result["messages"]] == ["Cena sabato?"]
    assert result["cursor"] > start["cursor"]
    assert logged_in.get("/api/notifications", params={"after": result["cursor"]}).json()["messages"] == []


def test_linux_notifier_announces_and_remembers_the_cursor(tmp_path, monkeypatch):
    import httpx

    from scripts import notifier
    monkeypatch.setattr(notifier, "STATE", tmp_path / "notifier.json")
    monkeypatch.setattr(notifier, "milo_focused", lambda server: False)
    shown = []
    monkeypatch.setattr(notifier, "banner", lambda title, body, message_id=None: shown.append((title, body)))
    replies = [{"cursor": 7, "messages": []},
               {"cursor": 12, "messages": [{"sender": f"Persona {n}", "subject": f"Tema {n}"} for n in range(5)]}]
    seen = []

    def handler(request):
        seen.append(dict(request.url.params))
        return httpx.Response(200, json=replies.pop(0))
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        first = notifier.Notifier("https://milo.example.ts.net", client)
        first.check()
        first.check()
    assert seen == [{}, {"after": "7"}]
    assert shown == [("Persona 0", "Tema 0"), ("Persona 1", "Tema 1"), ("Persona 2", "Tema 2"),
                     ("Milo", "Altre 2 email nuove")]
    assert notifier.load_cursor() == 12
