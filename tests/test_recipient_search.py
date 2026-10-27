from email.message import EmailMessage

import pytest

from milo.mail import parse_message


def add_message(store, account, uid, recipient, *, sent=True, thread=None, date=100):
    mail = EmailMessage()
    mail['From'] = 'Sender <sender@example.com>'
    mail['To'] = recipient
    mail['Subject'] = 'Proposal'
    mail['Message-ID'] = f'<search-{uid}@example.com>'
    mail.set_content('Here is our proposal.')
    data = parse_message(mail.as_bytes(), account, 'Sent' if sent else 'INBOX', '1', uid, sent=sent)
    data.update(thread_id=thread, date=date)
    return store.upsert_message(data)


@pytest.mark.parametrize('search', ['office@recipient.example', 'OFFICE@RECIPIENT.EXAMPLE', 'Recipient Council'])
def test_recipient_search_finds_sent_mail_in_store_and_api(logged_in, account_data, search):
    store = logged_in.app.state.store
    account = store.add_account(account_data)
    first = add_message(store, account, 1, 'Recipient Council <office@recipient.example>', thread='proposal')
    latest = add_message(store, account, 2, 'someone@else.example', thread='proposal', date=200)
    add_message(store, account, 3, 'another@else.example', thread='other')

    assert [row['id'] for row in store.messages(view='sent', account=account, search=search)] == [first]
    for view in ('sent', 'all'):
        response = logged_in.get('/api/messages', params={'view': view, 'account': account, 'search': search})
        assert response.status_code == 200
        rows = response.json()['messages']
        assert [row['id'] for row in rows] == [latest]
        assert rows[0]['message_count'] == 2
        assert not {'body', 'raw', 'analysis'} & set(rows[0])


def test_recipient_search_preserves_account_view_and_visibility_filters(logged_in, account_data):
    store = logged_in.app.state.store
    account = store.add_account(account_data)
    other = store.add_account({**account_data, 'email': 'other@example.com'})
    recipient = 'office@recipient.example'
    sent = add_message(store, account, 1, recipient)
    incoming = add_message(store, account, 2, recipient, sent=False)
    add_message(store, other, 3, recipient)
    hidden = add_message(store, account, 4, recipient)
    trashed = add_message(store, account, 5, recipient)
    store.execute('UPDATE messages SET hidden=1 WHERE id=?', (hidden,))
    store.execute('UPDATE messages SET trashed=1 WHERE id=?', (trashed,))

    for view, expected in [('sent', {sent}), ('inbox', {incoming}), ('all', {sent, incoming})]:
        assert {row['id'] for row in store.messages(view=view, account=account, search=recipient)} == expected
        response = logged_in.get('/api/messages', params={'view': view, 'account': account, 'search': recipient})
        assert response.status_code == 200
        assert {row['id'] for row in response.json()['messages']} == expected


def test_recipient_search_index_is_built_and_survives_repeated_maintenance(store):
    store.ensure_search_indexes()
    store.ensure_search_indexes()
    rows = store.rows("SELECT i.indisvalid,i.indisready,pg_get_indexdef(i.indexrelid) AS definition "
                      "FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid "
                      "WHERE c.relname='messages_search_recipients'")
    assert len(rows) == 1 and rows[0]['indisvalid'] and rows[0]['indisready']
    assert 'gin (recipients gin_trgm_ops)' in rows[0]['definition']
