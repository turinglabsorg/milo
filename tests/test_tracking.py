import re

from fastapi.testclient import TestClient
from test_app import add_mail

from milo.mail import build_message
from milo.public import create_public_app
from milo.signature import render_signature

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
        assert client.get("/o/" + "b" * 24 + ".jpg").status_code == 200
    assert opened == ["b" * 24]


def test_signature_becomes_the_tracked_image(logged_in, account_data, monkeypatch):
    client = logged_in
    add_mail(client, account_data)
    account_id = client.app.state.store.accounts()[0]["id"]
    signature = "Sebastiano Cataudo\nZonzolab · you@example.com"
    assert client.put("/api/settings/signatures", json={"signatures": {account_id: signature}}).status_code == 200
    html = "<p>Buongiorno</p><p>-- <br>Sebastiano Cataudo<br>Zonzolab · you@example.com</p>"
    message = send(client, account_id, monkeypatch, [], id="signed", html=html,
                   body="Buongiorno\n\n-- \n" + signature)
    sent_html = message.get_body(("html",)).get_content()
    token = re.search(r'src="http://127\.0\.0\.1:8025/o/([A-Za-z0-9_-]{24})\.png" width="\d+" height="\d+"', sent_html).group(1)
    assert "Sebastiano Cataudo<br>" not in sent_html and sent_html.startswith('<p>Buongiorno</p><div style="margin:16px 0 0"><img')
    assert 'alt="Sebastiano Cataudo · Zonzolab · you@example.com"' in sent_html
    assert signature in message.get_body(("plain",)).get_content() and "-- " not in sent_html

    sent_id = client.get("/api/messages?view=sent").json()["messages"][0]["id"]
    thread = client.get(f"/api/messages/{sent_id}/thread").json()
    rendered = [item for item in thread["messages"] if item["id"] == sent_id][0]["html"]
    assert f'src="/api/signature/{token}.png"' in rendered
    own = client.get(f"/api/signature/{token}.png")
    assert own.status_code == 200 and own.content.startswith(b"\x89PNG")
    assert client.get("/api/deliveries").json()["deliveries"][0]["opened"] is None

    local = TestClient(client.app, client=("127.0.0.1", 40000))
    opened = local.post(f"/internal/opened/{token}")
    assert opened.status_code == 200 and opened.headers["content-type"] == "image/png"
    assert opened.content == own.content
    assert client.get("/api/deliveries").json()["deliveries"][0]["opens"] == 1


def test_missing_signature_is_appended_as_image(logged_in, account_data, monkeypatch):
    client = logged_in
    add_mail(client, account_data)
    account_id = client.app.state.store.accounts()[0]["id"]
    assert client.put("/api/settings/signatures", json={"signatures": {account_id: "Seb"}}).status_code == 200
    message = send(client, account_id, monkeypatch, [], id="unsigned")
    html = message.get_body(("html",)).get_content()
    assert re.match(r'<p><b>Buongiorno</b></p><div style="margin:16px 0 0"><img src="http://127\.0\.0\.1:8025/o/[A-Za-z0-9_-]{24}\.png"', html)


def test_public_signature_image_comes_from_the_private_service():
    with TestClient(create_public_app(opened=lambda token: b"\x89PNG-card" if token == "c" * 24 else None)) as client:
        card = client.get("/o/" + "c" * 24 + ".png")
        assert card.headers["content-type"] == "image/png" and card.content == b"\x89PNG-card"
        fallback = client.get("/o/" + "d" * 24 + ".png")
        assert fallback.headers["content-type"] == "image/gif"


def test_template_documents_keep_their_own_signature(logged_in, account_data, monkeypatch):
    client = logged_in
    add_mail(client, account_data)
    account_id = client.app.state.store.accounts()[0]["id"]
    assert client.put("/api/settings/signatures", json={"signatures": {account_id: "Seb"}}).status_code == 200
    template = '<!doctype html><html><head><style>.brand{color:#0f3d3e}</style></head><body><p>Gentile Comune</p></body></html>'
    message = send(client, account_id, monkeypatch, [], id="template", html=template)
    html = message.get_body(("html",)).get_content()
    assert ".png" not in html and "-- " not in html
    assert re.search(r'<img src="http://127\.0\.0\.1:8025/o/[A-Za-z0-9_-]{24}\.gif" width="1" height="1"[^>]*></body></html>', html)
    assert client.get("/api/deliveries").json()["deliveries"][0]["tracked"] == 1


def test_signature_links_stay_clickable_under_the_card(logged_in, account_data, monkeypatch):
    client = logged_in
    add_mail(client, account_data)
    account_id = client.app.state.store.accounts()[0]["id"]
    card = "Sebastiano Cataudo\nZonzolab · you@example.com\n+39 334 112 3870"
    signature = card + "\nhttps://www.linkedin.com/in/someone\nhttps://x.com/someone"
    assert client.put("/api/settings/signatures", json={"signatures": {account_id: signature}}).status_code == 200
    html = "<p>Buongiorno</p><p>-- <br>" + "<br>".join(signature.split("\n")) + "</p>"
    message = send(client, account_id, monkeypatch, [], id="linked", html=html, body="Buongiorno\n\n-- \n" + signature)
    sent_html = message.get_body(("html",)).get_content()
    assert sent_html.startswith('<p>Buongiorno</p><div style="margin:16px 0 0"><img')
    assert 'alt="Sebastiano Cataudo · Zonzolab · you@example.com · +39 334 112 3870"' in sent_html
    assert '<a href="https://www.linkedin.com/in/someone"' in sent_html and ">LinkedIn</a>" in sent_html
    assert '<a href="https://x.com/someone"' in sent_html and ">X</a>" in sent_html
    assert "<br>https://" not in sent_html
    token = re.search(r"/o/([A-Za-z0-9_-]{24})\.png", sent_html).group(1)
    sender = client.app.state.store.accounts()[0]["email"]
    assert client.get(f"/api/signature/{token}.png").content == render_signature(card, sender)[0]


def test_composer_previews_the_account_signature_card(logged_in, account_data):
    client = logged_in
    add_mail(client, account_data)
    account = client.app.state.store.accounts()[0]
    signature = "Sebastiano Cataudo\n+39 334 112 3870\nhttps://x.com/someone"
    assert client.get(f"/api/signatures/{account['id']}/card.png").status_code == 404
    assert client.put("/api/settings/signatures", json={"signatures": {account["id"]: signature}}).status_code == 200
    card = client.get(f"/api/signatures/{account['id']}/card.png")
    assert card.status_code == 200 and card.headers["content-type"] == "image/png"
    assert card.content == render_signature(signature, account["email"])[0]
    assert client.get("/api/signatures/unknown/card.png").status_code == 404
