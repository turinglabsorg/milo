import json
import time
from email.message import EmailMessage

import httpx
from fastapi.testclient import TestClient
from test_conversations import add
from test_mail import parse_message

from milo.ai import AI
from milo.app import create_app
from milo.recap import RecapWorker
from milo.store import Store


def test_identity_is_authenticated_validated_and_persisted(logged_in, account_data):
    client = logged_in
    store = client.app.state.store
    store.add_account(account_data)
    profile = {'name': 'Sam Taylor', 'aliases': [' Sam ', 'SAM', 'S.T.'],
               'context': 'I maintain the export pipeline.', 'reply_language': 'auto'}
    assert client.put('/api/settings/identity', json=profile).status_code == 200
    saved = client.get('/api/state').json()['identity']
    assert saved == {**profile, 'aliases': ['Sam', 'S.T.']}
    reopened = Store(store.directory)
    assert reopened.setting('identity') == saved
    reopened.close()
    for invalid in ({'name': 'x' * 121}, {'aliases': ['x' * 81]}, {'reply_language': 'unknown'}, {'unknown': True}):
        assert client.put('/api/settings/identity', json=invalid).status_code == 422
        assert store.setting('identity') == saved
    client.post('/api/logout')
    assert client.put('/api/settings/identity', json=profile).status_code == 401
    assert client.get('/api/recap').status_code == 401


def test_reply_prompt_has_owner_aliases_account_roles_thread_and_language(store, account_data, monkeypatch):
    account = store.add_account(account_data)
    store.add_account({**account_data, 'email': 'work@example.com', 'name': 'Work'})
    store.set_setting('identity', {'name': 'Sam Taylor', 'aliases': ['Sam'],
                                 'context': 'Export developer', 'reply_language': 'auto'})
    store.set_setting('ai', {'model': 'local', 'automatic': False, 'cloud_consent': False})
    received = add(store, account, 1, date=100)
    sent = add(store, account, 2, sent=True, date=200)
    store.execute('UPDATE messages SET body=?,sender=?,sender_email=?,recipients=? WHERE id=?',
                  ('Hi Sam, we will await news from Sam about the export fix.', 'Customer',
                   'customer@example.com', 'Sam <you@example.com>', received))
    store.execute('UPDATE messages SET body=?,sender=?,sender_email=? WHERE id=?',
                  ('I have deployed the export fix.', 'Sam Taylor', 'you@example.com', sent))
    payloads = []

    def post(url, json, timeout):
        payloads.append(json)
        return httpx.Response(200, json={'message': {'content': '{"body":"Hi, I have deployed the fix."}'}},
                              request=httpx.Request('POST', url))

    monkeypatch.setattr('milo.ai.httpx.post', post)
    assert AI(store).reply(received)['body'].startswith('Hi, I ')
    system = payloads[0]['messages'][0]['content']
    assert 'first person' in system and 'language of the target incoming message' in system
    assert 'Rispondi in italiano' not in system
    assert 'current_time_utc' in system and 'Sam Taylor' in system and 'Sam' in system
    assert 'work@example.com' in system and account_data['password'] not in system
    context = json.loads(payloads[0]['messages'][1]['content'].split('\n', 1)[1])
    assert context['target_message_id'] == received and context['sending_account'] == 'you@example.com'
    assert [message['author'] for message in context['conversation']] == ['other_participant', 'owner']
    assert 'deployed' in context['conversation'][-1]['body']
    store.set_setting('identity', {**store.setting('identity'), 'reply_language': 'fr'})
    AI(store).reply(received)
    assert '"reply_language": "fr"' in payloads[-1]['messages'][0]['content']


def test_reply_context_is_bounded_and_keeps_requested_message(store, account_data, monkeypatch):
    account = store.add_account(account_data)
    target = add(store, account, 1, date=1)
    for i in range(2, 20):
        add(store, account, i, sent=i % 2 == 0, date=i)
    store.execute('UPDATE messages SET body=?', ('Large body ' * 20000,))
    captured = []

    def chat(prompt, schema, system):
        captured.append(json.loads(prompt.split('\n', 1)[1]))
        return {'body': 'Thanks.'}

    monkeypatch.setattr(AI, 'chat', lambda self, *args, **kwargs: chat(*args, **kwargs))
    AI(store).reply(target)
    conversation = captured[0]['conversation']
    assert len(conversation) == 12 and any(m['id'] == target for m in conversation)
    assert len(json.dumps(captured[0])) < 24000
    assert all(len(m['body']) <= (6000 if m['id'] == target else 1000) for m in conversation)


def test_recap_reads_saved_result_without_generation(logged_in, monkeypatch):
    client = logged_in
    saved = {'overview': 'Already ready', 'priorities': [], 'message_ids': [],
             'generated_at': 123, 'fingerprint': 'internal'}
    client.app.state.store.set_setting('recap', saved)
    client.app.state.store.set_setting('recap_status', {'phase': 'ready'})
    monkeypatch.setattr(AI, 'recap', lambda *args: (_ for _ in ()).throw(AssertionError('Generated on click')))
    for method in ('get', 'post'):
        result = getattr(client, method)('/api/recap').json()
        assert result['overview'] == 'Already ready' and result['generated_at'] == 123
        assert 'fingerprint' not in result


def test_received_mail_updates_recap_in_background_once_and_retains_previous_on_error(tmp_path, account_data, monkeypatch):
    app = create_app(tmp_path / 'background')
    store = app.state.store
    account = store.add_account(account_data)
    store.set_setting('ai', {'model': 'local', 'cloud_consent': False, 'automatic': False})
    app.state.engine.sync_all = lambda: []
    app.state.recaps.debounce = .02
    app.state.recaps.interval = .1
    calls = []
    fail = False

    def chat(self, prompt, schema, **kwargs):
        if fail:
            raise RuntimeError('Model temporarily unavailable')
        calls.append(prompt)
        return {'overview': f'Recap {len(calls)}', 'priorities': []}

    monkeypatch.setattr(AI, 'chat', chat)
    with TestClient(app) as client:
        client.post('/api/setup', json={'password': 'a secure test password', 'bootstrap': store.bootstrap})
        message = EmailMessage()
        message['From'] = 'Other <other@example.com>'
        message['To'] = 'you@example.com'
        message['Subject'] = 'New arrival'
        message.set_content('Please review the export.')
        data = parse_message(message.as_bytes(), account, 'INBOX', 1, 1)
        message_id = store.upsert_message(data)
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            result = client.get('/api/recap').json()
            if message_id in result['message_ids']:
                break
            time.sleep(.03)
        assert result['status']['phase'] == 'ready' and result['generated_at']
        assert len(calls) == 1
        original = result['overview']
        store.upsert_message(data)
        app.state.recaps.refresh()
        assert len(calls) == 1
        fail = True
        add(store, account, 2, thread='new-thread', date=time.time() + 1)
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            result = client.get('/api/recap').json()
            if result['status']['phase'] == 'error':
                break
            time.sleep(.03)
        assert result['overview'] == original and result['status']['phase'] == 'error'
    reopened = Store(tmp_path / 'background')
    assert reopened.setting('recap')['overview'] == original
    reopened.close()


def test_background_recap_respects_cloud_consent(store, account_data, monkeypatch):
    add(store, store.add_account(account_data), 1)
    monkeypatch.setattr(AI, 'chat', lambda *args: (_ for _ in ()).throw(AssertionError('Cloud without consent')))
    worker = RecapWorker(store, AI(store))
    worker.refresh()
    assert worker.snapshot()['status']['phase'] == 'disabled'
    assert not store.setting('recap')


def test_recipient_metadata_does_not_load_message_body(logged_in, account_data, monkeypatch):
    store = logged_in.app.state.store
    account = store.add_account(account_data)
    mail = EmailMessage()
    mail['From'] = 'Other <other@example.com>'
    mail['To'] = 'Owner <you@example.com>, Colleague <colleague@example.com>'
    mail['Cc'] = 'Copy <copy@example.com>'
    mail['Reply-To'] = 'Support <support@example.com>'
    mail.set_content('A very large body. ' * 500000)
    message_id = store.upsert_message(parse_message(mail.as_bytes(), account, 'INBOX', '1', 1))
    original = store.message

    def only_metadata(message_id, raw=False, metadata=False):
        assert metadata and not raw
        return original(message_id, metadata=True)

    monkeypatch.setattr(store, 'message', only_metadata)
    response = logged_in.get('/api/messages/' + message_id + '/recipients')
    assert response.status_code == 200 and len(response.content) < 2000
    result = response.json()
    assert result['cc_addresses'] == [{'name': 'Copy', 'email': 'copy@example.com'}]
    assert result['reply_to_addresses'] == [{'name': 'Support', 'email': 'support@example.com'}]
    assert not {'body', 'raw', 'html'} & result.keys()
    assert logged_in.get('/api/messages/missing/recipients').status_code == 404


def test_container_host_ollama_remains_local_but_cloud_models_require_consent(store):
    store.set_setting('ai', {'model': 'local-model', 'cloud_consent': False, 'automatic': False})
    assert AI(store, 'http://host.docker.internal:11434').permitted()
    assert not AI(store, 'https://external.example.com').permitted()
    store.set_setting('ai', {'model': 'mistral-large-4:cloud', 'cloud_consent': False, 'automatic': False})
    assert not AI(store, 'http://host.docker.internal:11434').permitted()
