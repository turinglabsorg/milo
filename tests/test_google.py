import base64
import json
import logging
import time
from urllib.parse import parse_qs, urlsplit

import pytest
import requests
from test_mail import raw_mail

from milo.__main__ import PrivateAccessFormatter
from milo.google import SCOPES, Gmail, GoogleOAuth

CLIENT = {"web": {"client_id": "unit-test.apps.googleusercontent.com", "client_secret": "test-only-client-secret"}}
CREDS = {"token": "test-access-token", "refresh_token": "test-refresh-token", "client_id": CLIENT["web"]["client_id"],
         "client_secret": CLIENT["web"]["client_secret"], "token_uri": "https://oauth2.googleapis.com/token",
         "scopes": SCOPES, "expiry": "2099-01-01T00:00:00Z"}


def remote(message_id="abc", labels=None):
    return {"id": message_id, "threadId": "thread-1", "raw": base64.urlsafe_b64encode(raw_mail()).decode(),
            "labelIds": labels if labels is not None else ["INBOX", "UNREAD"], "internalDate": "1791700000000"}


def gmail(store):
    account_id = store.google_account("mail@example.com", dict(CREDS))
    return Gmail(store, account_id)


def test_authorization_uses_pkce_and_encrypted_one_time_browser_state(store):
    oauth = GoogleOAuth(store, "https://milo.example.com")
    oauth.configure(CLIENT)
    session = store.new_session()
    url, browser = oauth.start(session)
    query = parse_qs(urlsplit(url).query)
    assert urlsplit(url).hostname == "accounts.google.com"
    assert query["redirect_uri"] == ["https://milo.example.com/api/oauth/google/callback"]
    assert query["access_type"] == ["offline"]
    assert query["scope"] == SCOPES
    assert query["code_challenge_method"] == ["S256"]
    state = query["state"][0]
    saved = store.rows("SELECT * FROM oauth_states")[0]
    assert session not in saved["data"] and browser not in saved["data"]
    assert state != saved["state"]
    assert store.consume_oauth(state, "wrong-browser") is None
    pending = store.consume_oauth(state, browser)
    assert pending["session"] == session and pending["verifier"]
    assert store.consume_oauth(state, browser) is None


def test_oauth_expiry_and_revoked_session_cannot_connect(store):
    oauth = GoogleOAuth(store, "http://127.0.0.1:8025")
    oauth.configure(CLIENT)
    session = store.new_session()
    url, browser = oauth.start(session)
    state = parse_qs(urlsplit(url).query)["state"][0]
    store.logout(session)
    with pytest.raises(ValueError, match="scaduta"):
        oauth.finish(state, browser, "code")
    store.begin_oauth("expired", {"browser": "browser"})
    store.execute("UPDATE oauth_states SET expires=?", (time.time()-1,))
    assert store.consume_oauth("expired", "browser") is None


def test_google_callback_exchanges_code_and_restores_strict_session(logged_in, monkeypatch):
    client = logged_in
    monkeypatch.setattr(client.app.state.engine, "sync_account", lambda account: {})
    response = client.put("/api/settings/google", json=CLIENT)
    assert response.status_code == 200
    assert CLIENT["web"]["client_secret"] not in response.text
    url = client.post("/api/oauth/google/start").json()["url"]
    assert client.cookies.get("milo_oauth")
    query = parse_qs(urlsplit(url).query)
    requests_seen = []

    def transport(session, request, **kwargs):
        requests_seen.append(request)
        response = requests.Response()
        response.status_code = 200
        response.request, response.url = request, request.url
        if request.url == "https://oauth2.googleapis.com/token":
            body = parse_qs(request.body)
            assert body["code"] == ["google-code"]
            assert body["code_verifier"]
            assert body["redirect_uri"] == query["redirect_uri"]
            data = {"access_token": CREDS["token"], "refresh_token": CREDS["refresh_token"],
                    "expires_in": 3600, "token_type": "Bearer", "scope": " ".join(SCOPES)}
        else:
            assert request.url.endswith("/users/me/profile")
            assert request.headers["Authorization"] == "Bearer " + CREDS["token"]
            data = {"emailAddress": "mail@example.com", "historyId": "1"}
        response._content = json.dumps(data).encode()
        return response

    monkeypatch.setattr(requests.Session, "send", transport)
    # The main Strict cookie is withheld on Google's top-level cross-site return.
    client.cookies.delete("milo_session")
    response = client.get("/api/oauth/google/callback", params={"state": query["state"][0], "code": "google-code"},
                          follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"].endswith("#google_connected=1")
    assert "SameSite=strict" in response.headers["set-cookie"]
    state = client.get("/api/state").json()
    assert state["accounts"][0]["provider"] == "google"
    assert CREDS["refresh_token"] not in json.dumps(state)
    assert "password" not in client.app.state.store.accounts(private=True)[0]
    assert not client.cookies.get("milo_oauth")
    assert len(requests_seen) == 2
    response = client.get("/api/oauth/google/callback", params={"state": query["state"][0], "code": "google-code"},
                          follow_redirects=False)
    assert "google_error" in response.headers["location"]
    assert len(requests_seen) == 2


def test_google_config_rejects_installed_client_and_does_not_trust_urls(store):
    oauth = GoogleOAuth(store, "https://milo.example.com")
    with pytest.raises(ValueError):
        oauth.configure({"installed": CLIENT["web"]})
    oauth.configure({"web": {**CLIENT["web"], "token_uri": "https://evil.example/token"}})
    assert oauth.config()["web"]["token_uri"] == "https://oauth2.googleapis.com/token"
    assert CLIENT["web"]["client_secret"] not in store.rows("SELECT value FROM settings WHERE key='google_client'")[0]["value"]


def test_google_reconnect_preserves_account_and_refresh_token(store):
    account_id = store.google_account("mail@example.com", dict(CREDS))
    new = {**CREDS, "token": "new", "refresh_token": None}
    assert store.google_account("mail@example.com", new) == account_id
    assert store.google_credentials(account_id)["refresh_token"] == CREDS["refresh_token"]
    with pytest.raises(RuntimeError, match="persistente"):
        store.google_account("new@example.com", {**CREDS, "refresh_token": None})


def test_gmail_labels_preserve_analysis_and_pending_changes(store):
    client = gmail(store)
    client.store_message(remote())
    message = store.messages()[0]
    store.execute("UPDATE messages SET analysis=?,category='updates' WHERE id=?", ('{"summary":"Kept"}', message["id"]))
    store.patch_message(message["id"], {"starred": True})
    client.store_message(remote(labels=["INBOX"]))
    updated = store.message(message["id"])
    assert updated["read"] and updated["starred"] and updated["category"] == "updates"
    assert updated["analysis"]["summary"] == "Kept"
    assert len(store.rows("SELECT id FROM messages")) == 1
    client.store_message(remote(labels=["TRASH"]))
    assert not store.messages() and store.message(message["id"])["hidden"]
    client.close()


def test_gmail_outbox_uses_native_idempotent_labels(store, monkeypatch):
    client = gmail(store)
    client.store_message(remote())
    message_id = store.messages()[0]["id"]
    store.patch_message(message_id, {"read": True, "starred": True, "archived": True})
    calls = []
    monkeypatch.setattr(client, "request", lambda method, path, **kwargs: calls.append((method, path, kwargs)) or {"id": "abc"})
    client.flush_changes()
    assert [call[2]["json"] for call in calls] == [
        {"addLabelIds": [], "removeLabelIds": ["UNREAD"]},
        {"addLabelIds": ["STARRED"], "removeLabelIds": []},
        {"addLabelIds": [], "removeLabelIds": ["INBOX"]}]
    assert all(call[:2] == ("POST", "messages/abc/modify") for call in calls)
    assert not store.rows("SELECT * FROM outbox")
    client.close()


def test_gmail_backfill_does_not_advance_cursor_on_partial_failure(store, monkeypatch):
    client = gmail(store)
    store.execute("INSERT INTO gmail_sync VALUES(?, '10', NULL, NULL, 0)", (client.account_id,))
    monkeypatch.setattr(client, "request", lambda *args, **kwargs: {"messages": [{"id": "abc"}, {"id": "def"}], "nextPageToken": "next"})

    def fetch(message_id):
        if message_id == "def":
            raise RuntimeError("connection lost")
        return remote(message_id)

    monkeypatch.setattr(client, "fetch_remote", fetch)
    with pytest.raises(RuntimeError):
        client.backfill()
    assert store.rows("SELECT backfill_page FROM gmail_sync")[0]["backfill_page"] is None
    monkeypatch.setattr(client, "fetch_remote", lambda message_id: remote(message_id))
    client.backfill()
    assert store.rows("SELECT backfill_page FROM gmail_sync")[0]["backfill_page"] == "next"
    assert len(store.rows("SELECT id FROM messages")) == 2
    client.close()


def test_gmail_history_pages_and_expired_cursor_retain_cache(store, monkeypatch):
    client = gmail(store)
    client.store_message(remote())
    store.execute("INSERT INTO gmail_sync VALUES(?, '10', NULL, NULL, 1)", (client.account_id,))
    calls = []
    pages = iter([{"historyId": "20", "nextPageToken": "page-2"}, {"historyId": "22"}, None,
                  {"historyId": "30"}])
    monkeypatch.setattr(client, "request", lambda method, path, **kwargs: calls.append((path, kwargs)) or next(pages))
    client.history()
    assert store.rows("SELECT * FROM gmail_sync")[0]["history_id"] == "10"
    client.history()
    assert calls[1][1]["params"] == {"startHistoryId": "10", "maxResults": 100, "pageToken": "page-2"}
    assert store.rows("SELECT * FROM gmail_sync")[0]["history_id"] == "22"
    client.history()
    assert len(store.messages()) == 1
    assert not store.rows("SELECT * FROM gmail_sync")[0]["backfill_complete"]
    assert store.rows("SELECT * FROM gmail_sync")[0]["history_id"] == "30"
    client.close()


def test_google_send_uses_gmail_and_single_remote_identity(store, monkeypatch):
    client = gmail(store)
    client.store_message(remote())
    original = store.messages()[0]
    account = store.accounts()[0]
    sent = []
    monkeypatch.setattr(client, "request", lambda method, path, **kwargs: sent.append((path, kwargs)) or {"id": "sent-1", "threadId": "thread-1"})
    client.send(account, {"to": "person@example.com", "cc": "copy@example.com", "subject": "Re: Hello", "body": "Reply"}, original)
    assert sent[0][0] == "messages/send" and sent[0][1]["json"]["threadId"] == "thread-1"
    sent_message = store.messages("sent")[0]
    assert sent_message["provider_id"] == "sent-1" and sent_message["thread_id"] == "thread-1"
    assert "In-Reply-To:" in base64.urlsafe_b64decode(sent[0][1]["json"]["raw"]).decode()
    assert "Cc: copy@example.com" in base64.urlsafe_b64decode(sent[0][1]["json"]["raw"]).decode()
    client.store_message(remote("sent-1", ["SENT"]))
    assert len(store.messages("sent")) == 1
    client.close()


def test_refreshed_google_tokens_are_persisted_without_exposure(store, monkeypatch):
    client = gmail(store)

    def request(*args, **kwargs):
        client.credentials.token = "refreshed-access"
        response = requests.Response()
        response.status_code = 200
        response._content = b'{"historyId":"20"}'
        return response

    monkeypatch.setattr(client.session, "request", request)
    client.request("GET", "profile")
    assert store.google_credentials(client.account_id)["token"] == "refreshed-access"
    assert "refreshed-access" not in json.dumps(store.accounts(private=True))
    client.close()


def test_authorization_codes_are_removed_from_access_logs():
    formatter = PrivateAccessFormatter('%(request_line)s')
    record = logging.LogRecord("uvicorn.access", logging.INFO, "", 0, '%s - "%s %s HTTP/%s" %d',
                               ("client", "GET", "/api/oauth/google/callback?code=secret&state=state", "1.1", 303), None)
    output = formatter.format(record)
    assert "callback" in output and "secret" not in output and "state=" not in output


def test_inflight_refresh_does_not_overwrite_a_new_google_grant(store, monkeypatch):
    client = gmail(store)
    store.google_account("mail@example.com", {**CREDS, "refresh_token": "new-grant-refresh"})

    def request(*args, **kwargs):
        client.credentials.token = "old-grant-access"
        response = requests.Response()
        response.status_code = 200
        response._content = b'{}'
        return response

    monkeypatch.setattr(client.session, "request", request)
    client.request("GET", "profile")
    assert store.google_credentials(client.account_id)["refresh_token"] == "new-grant-refresh"
    client.close()


def test_new_google_edit_is_not_removed_by_an_inflight_outbox_ack(store, monkeypatch):
    client = gmail(store)
    client.store_message(remote())
    message_id = store.messages()[0]['id']
    store.patch_message(message_id, {'starred': True})

    def request(method, path, **kwargs):
        # The user changes their mind while Gmail processes the first request.
        store.patch_message(message_id, {'starred': False})
        return {'id': 'abc'}

    monkeypatch.setattr(client, 'request', request)
    client.flush_changes()
    pending = store.rows('SELECT * FROM outbox')
    assert len(pending) == 1 and pending[0]['value'] == 'false'
    assert not store.message(message_id)['starred']
    client.close()


def test_google_flag_reconciliation_is_atomic_with_local_edits(store, monkeypatch):
    import threading

    client = gmail(store)
    client.store_message(remote(labels=['INBOX']))
    message_id = store.messages()[0]['id']
    queried, release, attempted, finished = (threading.Event() for _ in range(4))
    rows = store.rows

    def blocked_rows(query, params=()):
        result = rows(query, params)
        if query.startswith('SELECT kind FROM outbox'):
            queried.set()
            assert release.wait(3)
        return result

    monkeypatch.setattr(store, 'rows', blocked_rows)
    updater = threading.Thread(target=lambda: client.store_message(remote(labels=['INBOX'])))

    def edit():
        attempted.set()
        store.patch_message(message_id, {'starred': True})
        finished.set()

    editor = threading.Thread(target=edit)
    try:
        updater.start()
        assert queried.wait(2)
        editor.start()
        assert attempted.wait(2)
        assert not finished.wait(.1), 'A local edit must not interleave between pending-flag check and reconciliation'
    finally:
        release.set()
        updater.join(timeout=3)
        if editor.ident:
            editor.join(timeout=3)
    assert finished.is_set() and store.message(message_id)['starred']
    client.close()
