import re

from fastapi.testclient import TestClient
from test_app import add_mail

from milo.mail import build_message
from milo.public import create_public_app

PIXEL = re.compile(r'<img src="http://127\.0\.0\.1:8025/o/([A-Za-z0-9_-]{24})\.gif" width="1" height="1"')


def send(client, account_id, monkeypatch, sent, **draft):
    def transport(account, saved_draft, original=None, attachments=()):
        message = build_message(account, saved_draft, original, attachments)
        sent.append(message)
        return message

    monkeypatch.setattr("milo.app.send_mail", transport)
    data = {"id": draft.pop("id"), "account_id": account_id, "to": "anna@example.com", "subject": "Ciao",
            "body": "Buongiorno", "html": "<p><b>Buongiorno</b></p>", "revision": 1, **draft}
    assert client.put("/api/drafts", json=data).status_code == 200
    assert client.post(f"/api/drafts/{data['id']}/send").status_code == 200
    return sent[-1]


def test_tracked_messages_carry_a_pixel_and_record_opens(logged_in, account_data, monkeypatch):
    client = logged_in
    add_mail(client, account_data)
    account_id = client.app.state.store.accounts()[0]["id"]
    sent = []
    message = send(client, account_id, monkeypatch, sent, id="tracked")
    html = message.get_body(("html",)).get_content()
    token = PIXEL.search(html).group(1)
    assert "Buongiorno" in message.get_body(("plain",)).get_content() and "/o/" not in message.get_body(("plain",)).get_content()
    sent_id = client.get("/api/messages?view=sent").json()["messages"][0]["id"]
    [delivery] = client.get("/api/deliveries").json()["deliveries"]
    assert delivery["id"] == sent_id and delivery["tracked"] == 1 and delivery["opened"] is None and delivery["opens"] == 0

    thread = client.get(f"/api/messages/{sent_id}/thread?load_images=true").json()
    rendered = [item for item in thread["messages"] if item["id"] == sent_id][0]
    assert "/o/" not in rendered["html"] and "Buongiorno" in rendered["html"] and not rendered["remote_images"]

    assert client.post(f"/internal/opened/{token}").status_code == 404
    local = TestClient(client.app, client=("127.0.0.1", 40000))
    assert local.post("/internal/opened/not-a-token").status_code == 404
    assert local.post("/internal/opened/" + "A" * 24).status_code == 204
    assert client.get("/api/deliveries").json()["deliveries"][0]["opened"] is None
    assert local.post(f"/internal/opened/{token}").status_code == 204
    assert local.post(f"/internal/opened/{token}").status_code == 204
    [delivery] = client.get("/api/deliveries").json()["deliveries"]
    assert delivery["opened"] and delivery["opens"] == 2


def test_untracked_messages_have_no_pixel_but_show_as_sent(logged_in, account_data, monkeypatch):
    client = logged_in
    add_mail(client, account_data)
    account_id = client.app.state.store.accounts()[0]["id"]
    message = send(client, account_id, monkeypatch, [], id="untracked", track=False)
    assert "/o/" not in message.get_body(("html",)).get_content()
    [delivery] = client.get("/api/deliveries").json()["deliveries"]
    assert delivery["tracked"] == 0 and delivery["opened"] is None


def test_plain_drafts_gain_an_html_part_for_the_pixel(logged_in, account_data, monkeypatch):
    client = logged_in
    add_mail(client, account_data)
    account_id = client.app.state.store.accounts()[0]["id"]
    message = send(client, account_id, monkeypatch, [], id="plain", html="", body="Riga uno\n\nRiga <due>")
    html = message.get_body(("html",)).get_content()
    assert html.startswith("<p>Riga uno</p><p>Riga &lt;due&gt;</p>") and PIXEL.search(html)


def test_public_pixel_reports_only_valid_tokens():
    opened = []
    with TestClient(create_public_app(opened=opened.append)) as client:
        response = client.get("/o/" + "b" * 24 + ".gif")
        assert response.status_code == 200 and response.headers["content-type"] == "image/gif"
        assert response.headers["cache-control"] == "no-store" and response.content.startswith(b"GIF89a")
        assert client.get("/o/short.gif").status_code == 200
        assert client.get("/o/" + "b" * 24 + ".png").status_code == 200
    assert opened == ["b" * 24]
