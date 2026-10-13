import json
from email.message import EmailMessage

import pytest
import requests
from test_google import CREDS, gmail, remote
from test_mail import parse_message, raw_mail

from milo.google import gmail_error
from milo.render import render_html
from milo.store import Store


def add(store, account_id, uid, sent=False, thread="conversation", date=100):
    data = parse_message(raw_mail(msg_id=f"<{uid}@example.com>"), account_id, "Sent" if sent else "INBOX", "7", uid, sent=sent)
    data.update(thread_id=thread, date=date)
    return store.upsert_message(data)


def test_threads_include_sent_replies_and_lightweight_list(logged_in, account_data):
    store = logged_in.app.state.store
    account_id = store.add_account(account_data)
    received = add(store, account_id, 1, date=100)
    sent = add(store, account_id, 2, sent=True, date=200)
    other = add(store, account_id, 3, thread="other", date=300)
    store.execute("UPDATE messages SET analysis=? WHERE id=?", (json.dumps({"summary": "Analyzed"}), received))
    conversations = logged_in.get('/api/messages').json()['messages']
    assert len(conversations) == 2
    conversation = next(row for row in conversations if row['id'] == sent)
    assert conversation['message_count'] == 2 and conversation['analyzed_count'] == 1
    assert conversation['replied'] and not conversation['read']
    assert not {'body', 'raw', 'analysis'} & set(conversation)
    messages = logged_in.get('/api/messages/'+sent+'/thread').json()['messages']
    assert [message['id'] for message in messages] == [received, sent]
    assert messages[-1]['sent']
    assert logged_in.patch('/api/messages/'+sent+'/thread', json={'pinned': True}).status_code == 200
    assert logged_in.get('/api/messages').json()['messages'][0]['id'] == sent
    assert store.message(received)['pinned'] and not store.message(other)['pinned']
    later = add(store, account_id, 4, date=400)
    assert store.message(later)['pinned']


def test_reading_mail_never_calls_the_provider(logged_in, monkeypatch):
    store = logged_in.app.state.store
    account_id = store.google_account('mail@example.com', dict(CREDS))
    received = add(store, account_id, 1, date=100)
    add(store, account_id, 2, sent=True, date=200)

    def forbidden(self, *args, **kwargs):
        raise AssertionError('a read must not construct a provider client')

    monkeypatch.setattr('milo.app.Gmail.__init__', forbidden)
    thread = logged_in.get('/api/messages/' + received + '/thread?lazy=true')
    assert thread.status_code == 200 and len(thread.json()['messages']) == 2
    assert thread.json()['sync'] == {}
    assert logged_in.get('/api/messages/' + received).status_code == 200
    assert logged_in.get('/api/client/messages').status_code == 200
    assert logged_in.get('/api/messages').status_code == 200


def test_thread_identity_never_crosses_accounts(store, account_data):
    first = store.add_account(account_data)
    second = store.add_account({**account_data, 'email': 'another@example.com'})
    one = add(store, first, 1)
    two = add(store, second, 2)
    store.patch_conversation(one, {'pinned': True})
    assert not store.message(two)['pinned']
    assert len(store.conversations()) == 2


def test_trash_is_local_immediate_durable_and_provider_failure_keeps_it_hidden(logged_in, monkeypatch):
    store = logged_in.app.state.store
    monkeypatch.setattr(logged_in.app.state.engine, 'sync_all', lambda: [])
    client = gmail(store)
    client.store_message(remote())
    message = store.messages()[0]
    # A mailbox download owns the provider lock. Local deletion must still finish.
    lock = logged_in.app.state.engine.account_lock(client.account_id)
    with lock:
        response = logged_in.delete('/api/messages/'+message['id']+'/thread')
        assert response.status_code == 202
    assert not logged_in.get('/api/messages').json()['messages']
    reopened = Store(store.directory)
    assert reopened.message(message['id'])['trashed']
    assert reopened.rows('SELECT kind FROM outbox')[0]['kind'] == 'trash'
    reopened.close()
    client.request = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError('Temporary provider failure'))
    client.flush_changes()
    assert store.rows('SELECT error FROM outbox')[0]['error']
    client.store_message(remote())
    assert not store.conversations()
    calls = []
    client.request = lambda method, path, **kwargs: calls.append((method, path)) or {'id': 'abc'}
    client.flush_changes()
    assert calls == [('POST', 'messages/abc/trash')]
    assert not store.rows('SELECT * FROM outbox')
    client.close()


def test_shared_appearance_and_account_colors_do_not_change_google_credentials(logged_in):
    store = logged_in.app.state.store
    account_id = store.google_account('mail@example.com', dict(CREDS))
    before = store.google_credentials(account_id)
    assert logged_in.put('/api/settings/appearance', json={'theme': 'dark'}).status_code == 200
    assert logged_in.get('/api/state').json()['appearance'] == {'theme': 'dark'}
    assert logged_in.patch('/api/accounts/'+account_id, json={'color': '#f97316'}).status_code == 200
    assert store.account(account_id)['color'] == '#f97316'
    assert store.google_credentials(account_id) == before
    assert logged_in.patch('/api/accounts/'+account_id, json={'color': 'url(evil)'}).status_code == 422
    logged_in.post('/api/logout')
    assert logged_in.put('/api/settings/appearance', json={'theme': 'light'}).status_code == 401


@pytest.mark.parametrize('reason,expected', [('insufficientPermissions','Manca il permesso'),
    ('ACCESS_TOKEN_SCOPE_INSUFFICIENT','Manca il permesso'), ('SERVICE_DISABLED','Gmail API è disabilitata'),
    ('domainPolicy','amministratore'), ('userRateLimitExceeded','temporaneamente')])
def test_gmail_errors_use_precise_reasons_without_exposing_response(reason, expected):
    response = requests.Response()
    response.status_code = 403
    response._content = json.dumps({'error': {'message': 'PRIVATE-RESPONSE', 'details': [{'reason': reason}]}}).encode()
    result = gmail_error(response)
    assert expected in result and 'PRIVATE-RESPONSE' not in result


def test_html_preserves_table_styles_and_cid_images_without_active_content():
    mail = EmailMessage()
    mail.set_content('Text alternative')
    mail.add_alternative('<table><tr><td style="color:red;background-image:url(https://tracker.example/x);position:fixed">Hello</td></tr></table>'
        '<script>evil()</script><img src="cid:logo"><img src="https://tracker.example/image" onerror="evil()">'
        '<a href="javascript:evil()">bad</a><a href="https://example.com">safe</a>', subtype='html')
    mail.get_payload()[1].add_related(b'PNG', maintype='image', subtype='png', cid='<logo>')
    rendered = render_html(mail, 'message')
    html = rendered['html']
    assert '<table>' in html and 'color:red' in html
    assert '/api/messages/message/attachments/' in html
    assert not any(value in html for value in ('evil()', 'javascript:', 'onerror', 'background-image', 'position:', 'tracker.example'))
    assert 'noopener' in html and rendered['remote_images']
    assert 'https://tracker.example/image' in render_html(mail, 'message', True)['html']


def test_imap_threads_follow_references():
    original = parse_message(raw_mail(msg_id='<root@example.com>'), 'account', 'INBOX', '7', 1)
    mail = EmailMessage()
    mail['Message-ID'] = '<reply@example.com>'
    mail['References'] = '<root@example.com>'
    mail.set_content('Reply')
    reply = parse_message(mail.as_bytes(), 'account', 'Sent', '8', 2, sent=True)
    assert reply['thread_id'] == original['thread_id']
