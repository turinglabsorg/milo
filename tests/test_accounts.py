
import json

import pytest
from fastapi.testclient import TestClient
from test_app import add_mail
from test_google import CLIENT, CREDS
from test_mail import FakeIMAP

from milo.google import GoogleOAuth
from milo.mail import SyncEngine
from milo.store import Store


def test_account_edit_is_shared_and_credentials_remain_encrypted(logged_in, account_data, monkeypatch):
    client = logged_in
    message_id = add_mail(client, account_data)
    store = client.app.state.store
    account_id = store.messages()[0]["account_id"]
    monkeypatch.setattr(client.app.state.engine, "sync_account", lambda account: {})
    draft_id = client.put('/api/drafts', json={"account_id": account_id, "to": "other@example.com",
                                              "subject": "Saved", "body": "Keep this"}).json()["id"]
    second = TestClient(client.app)
    second.post('/api/login', json={"password": "a secure test passphrase"})
    response = client.patch('/api/accounts/'+account_id, json={"name": "Work", "enabled": False,
                                                               "password": "a-new-private-password", "smtp_port": 587,
                                                               "smtp_security": "starttls"})
    assert response.status_code == 200 and response.json()["id"] == account_id
    assert "password" not in response.json() and "secret" not in response.json()
    account = second.get('/api/state').json()["accounts"][0]
    assert account["name"] == "Work" and account["enabled"] == 0
    assert store.account(account_id, private=True)["password"] == "a-new-private-password"
    assert "a-new-private-password" not in store.rows("SELECT secret FROM accounts")[0]["secret"]
    assert second.get('/api/messages/'+message_id).status_code == 200
    assert second.get('/api/drafts').json()["drafts"][0]["id"] == draft_id
    reopened = Store(store.directory)
    assert reopened.account(account_id)["name"] == "Work" and not reopened.account(account_id)["enabled"]
    reopened.close()


def test_account_rename_keeps_password_and_does_not_trigger_network(logged_in, account_data, monkeypatch):
    client = logged_in
    account_id = client.app.state.store.add_account(account_data)
    calls = []
    monkeypatch.setattr(client.app.state.engine, "sync_account", lambda account: calls.append(account))
    response = client.patch('/api/accounts/'+account_id, json={"name": "Private"})
    assert response.status_code == 200 and not calls
    assert client.app.state.store.account(account_id, private=True)["password"] == account_data["password"]
    assert client.patch('/api/accounts/'+account_id, json={"enabled": False}).status_code == 200
    assert not calls
    assert client.patch('/api/accounts/'+account_id, json={"enabled": True}).status_code == 200
    assert len(calls) == 1


@pytest.mark.parametrize("patch", [{"name": None}, {"name": ""}, {"password": ""}, {"imap_host": "bad host"},
                                    {"smtp_port": 0}, {"provider": "google"}, {"email": "other@example.com"},
                                    {"secret": "overwrite"}])
def test_account_edit_rejects_invalid_or_identity_changes(logged_in, account_data, patch):
    account_id = logged_in.app.state.store.add_account(account_data)
    assert logged_in.patch('/api/accounts/'+account_id, json=patch).status_code == 422
    assert logged_in.app.state.store.account(account_id)["email"] == account_data["email"]


def test_account_updates_require_authentication(logged_in, account_data):
    account_id = logged_in.app.state.store.add_account(account_data)
    assert logged_in.patch('/api/accounts/missing', json={"name": "Name"}).status_code == 404
    logged_in.post('/api/logout')
    assert logged_in.patch('/api/accounts/'+account_id, json={"name": "Name"}).status_code == 401


def test_google_account_edit_keeps_oauth_grant_and_rejects_password(logged_in):
    store = logged_in.app.state.store
    account_id = store.google_account("mail@example.com", dict(CREDS))
    before = store.google_credentials(account_id)
    response = logged_in.patch('/api/accounts/'+account_id, json={"name": "Google work", "enabled": False})
    assert response.status_code == 200
    assert store.google_credentials(account_id) == before
    assert logged_in.patch('/api/accounts/'+account_id, json={"password": "new"}).status_code == 422
    assert logged_in.patch('/api/accounts/'+account_id, json={"username": "mail@example.com"}).status_code == 422
    assert "refresh_token" not in response.text and "client_secret" not in response.text


def test_stale_worker_snapshot_respects_pause_and_new_credentials(store, account_data, monkeypatch):
    account_id = store.add_account(account_data)
    old = store.account(account_id, private=True)
    store.update_account(account_id, {"enabled": False})
    calls = []
    remote = FakeIMAP()
    monkeypatch.setattr('milo.mail.connect', lambda account: calls.append(account) or remote)
    engine = SyncEngine(store)
    assert engine.sync_account(old)["paused"] and not calls
    assert engine.sync_all() == []
    store.update_account(account_id, {"password": "updated-password", "enabled": True})
    assert engine.sync_account(old)["ok"]
    assert calls[0]["password"] == "updated-password"


def test_paused_account_keeps_pending_changes_until_resume(store, account_data, monkeypatch):
    account_id = store.add_account(account_data)
    remote = FakeIMAP()
    monkeypatch.setattr('milo.mail.connect', lambda account: remote)
    engine = SyncEngine(store)
    engine.sync_account(store.account(account_id))
    message_id = store.messages()[0]["id"]
    store.patch_message(message_id, {"starred": True})
    store.update_account(account_id, {"enabled": False})
    assert engine.sync_all() == []
    assert not remote.boxes["INBOX"][41][1]
    assert store.rows("SELECT * FROM outbox")
    store.update_account(account_id, {"enabled": True})
    engine.sync_all()
    assert remote.boxes["INBOX"][41][1] == {"\\Flagged"}
    assert not store.rows("SELECT * FROM outbox")


def test_google_reconnect_binds_the_selected_address(store, monkeypatch):
    account_id = store.google_account("mail@example.com", dict(CREDS))
    oauth = GoogleOAuth(store, 'https://milo.example.com')
    oauth.configure(CLIENT)
    session = store.new_session()
    url, browser = oauth.start(session, account_id)
    from urllib.parse import parse_qs, urlsplit
    query = parse_qs(urlsplit(url).query)
    assert query["login_hint"] == ["mail@example.com"]
    assert store.consume_oauth(query["state"][0], "wrong") is None
    pending = store.consume_oauth(query["state"][0], browser)
    assert pending["expected_email"] == "mail@example.com"
    store.begin_oauth('state', pending)

    class Flow:
        credentials = type('Credentials', (), {'granted_scopes': CREDS['scopes'], 'scopes': CREDS['scopes']})()

        def fetch_token(self, **kwargs):
            pass

    class ProfileSession:
        def __init__(self, credentials):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def get(self, *args, **kwargs):
            return type('Response', (), {'raise_for_status': lambda self: None,
                                         'json': lambda self: {'emailAddress': 'other@example.com'}})()

    monkeypatch.setattr(oauth, 'flow', lambda **kwargs: Flow())
    monkeypatch.setattr('milo.google.AuthorizedSession', ProfileSession)
    with pytest.raises(ValueError, match='diversa'):
        oauth.finish('state', browser, 'code')
    assert len(store.accounts()) == 1
    assert store.google_credentials(account_id)['refresh_token'] == CREDS['refresh_token']


def test_google_start_cannot_reconnect_a_missing_or_imap_account(logged_in, account_data):
    logged_in.put('/api/settings/google', json=CLIENT)
    account_id = logged_in.app.state.store.add_account(account_data)
    for target in ('missing', account_id):
        assert logged_in.post('/api/oauth/google/start', json={'account_id': target}).status_code == 404
    assert not logged_in.app.state.store.rows('SELECT * FROM oauth_states')


def test_google_local_edits_and_pause_do_not_wait_for_network_sync(logged_in):
    import threading

    from test_google import remote

    from milo.google import Gmail

    store = logged_in.app.state.store
    account_id = store.google_account('mail@example.com', dict(CREDS))
    google = Gmail(store, account_id)
    google.store_message(remote())
    google.close()
    message_id = store.messages()[0]['id']
    engine = logged_in.app.state.engine
    responses = []
    done = threading.Event()

    def edit():
        try:
            responses.append(logged_in.patch('/api/messages/'+message_id, json={'read': True, 'starred': True}))
            responses.append(logged_in.patch('/api/accounts/'+account_id, json={'name': 'Work', 'enabled': False}))
        finally:
            done.set()

    thread = threading.Thread(target=edit)
    try:
        with engine.account_lock(account_id):
            thread.start()
            assert done.wait(2), 'Local edits must finish while the network sync lock is held'
    finally:
        thread.join(timeout=3)
    assert [response.status_code for response in responses] == [200, 200]
    assert store.message(message_id)['starred'] and store.message(message_id)['read']
    assert len(store.rows('SELECT * FROM outbox')) == 2
    assert not store.account(account_id)['enabled']


def test_google_send_does_not_wait_for_sync_or_delete_a_newer_shared_draft(logged_in, monkeypatch):
    import threading

    from milo.google import Gmail

    store = logged_in.app.state.store
    account_id = store.google_account('mail@example.com', dict(CREDS))
    draft={'account_id': account_id, 'to': 'other@example.com', 'subject': 'A draft', 'body': 'Submitted version'}
    draft_id=logged_in.put('/api/drafts', json=draft).json()['id']
    newer={**draft, 'id': draft_id, 'body': 'A newer saved version', 'reply_to_id': None}
    calls=[]

    def send(self, account, submitted, original, attachments=()):
        calls.append(submitted)
        store.execute('UPDATE drafts SET data=? WHERE id=?', (json.dumps(newer), draft_id))
        return {'id': 'sent-1'}

    monkeypatch.setattr(Gmail, 'send', send)
    done=threading.Event()
    responses=[]

    def submit():
        try:
            responses.append(logged_in.post('/api/drafts/'+draft_id+'/send'))
        finally:
            done.set()

    thread=threading.Thread(target=submit)
    try:
        with logged_in.app.state.engine.account_lock(account_id):
            thread.start()
            assert done.wait(2), 'Explicit Gmail sends must not wait for a mailbox backfill'
    finally:
        thread.join(timeout=3)
    assert responses[0].status_code==200 and len(calls)==1
    assert calls[0]['body']=='Submitted version'
    assert logged_in.get('/api/drafts').json()['drafts'][0]['body']=='A newer saved version'
