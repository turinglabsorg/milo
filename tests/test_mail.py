import json
import os
import time
from email.message import EmailMessage

import pytest

from milo.mail import SyncEngine, build_message, parse_message, send_mail


def raw_mail(subject="Hello", msg_id="<mail-1@example.com>", body="Ciao,\nParliamone domani."):
    mail = EmailMessage()
    mail["From"] = "Giulia Rossi <giulia@example.com>"
    mail["To"] = "you@example.com"
    mail["Subject"] = subject
    mail["Message-ID"] = msg_id
    mail["Date"] = "Sun, 11 Oct 2026 10:00:00 +0200"
    mail.set_content(body)
    return mail.as_bytes()


class FakeIMAP:
    capabilities = ("IMAP4REV1", "MOVE")

    def __init__(self):
        self.boxes = {"INBOX": {41: [raw_mail(), set()]}, "Archive": {}, "Sent": {}}
        self.validities = {"INBOX": "7", "Archive": "8", "Sent": "9"}
        self.selected = None
        self.fail_store = False
        self.operations = []

    def list(self):
        return "OK", [b'(\\HasNoChildren) "/" "INBOX"', b'(\\Archive) "/" "Archive"', b'(\\Sent) "/" "Sent"']

    def select(self, folder):
        self.selected = folder.strip('"')
        return "OK", [str(len(self.boxes[self.selected])).encode()]

    def response(self, key):
        return key, [self.validities[self.selected].encode()]

    def uid(self, command, *args):
        self.operations.append((self.selected, command, args))
        box = self.boxes[self.selected]
        if command == "SEARCH":
            return "OK", [b" ".join(str(uid).encode() for uid in box)]
        if command == "FETCH":
            result = []
            for uid in map(int, args[0].split(",")):
                if uid not in box:
                    continue
                raw, flags = box[uid]
                descriptor = f"1 (UID {uid} FLAGS ({' '.join(flags)}))".encode()
                result.append((descriptor, raw) if "BODY.PEEK" in args[1] else descriptor)
            return "OK", result
        uid = int(args[0])
        if command == "STORE":
            if self.fail_store:
                return "NO", [b"temporary failure"]
            flag = args[2].strip("()")
            if args[1].startswith("+"):
                box[uid][1].add(flag)
            else:
                box[uid][1].discard(flag)
            return "OK", []
        if command == "MOVE":
            target = args[1].strip('"')
            self.boxes[target][123] = box.pop(uid)
            return "OK", []
        if command == "COPY":
            target = args[1].strip('"')
            self.boxes[target][123] = [box[uid][0], set(box[uid][1])]
            return "OK", []
        if command == "EXPUNGE":
            if "\\Deleted" in box[uid][1]:
                box.pop(uid)
            return "OK", []
        raise AssertionError(command)

    def logout(self):
        pass


@pytest.fixture
def synced(store, account_data, monkeypatch):
    account_id = store.add_account(account_data)
    account = store.accounts(private=True)[0]
    remote = FakeIMAP()
    monkeypatch.setattr("milo.mail.connect", lambda _: remote)
    engine = SyncEngine(store)
    assert engine.sync_account(account)["ok"]
    return store, account_id, account, remote, engine


def test_import_is_idempotent_and_uses_uid_not_sequence(synced):
    store, _, account, remote, engine = synced
    assert len(store.messages()) == 1
    assert store.messages()[0]["uid"] == 41
    assert engine.sync_account(account)["added"] == 0
    assert len(store.messages()) == 1
    fetch = [op for op in remote.operations if op[1] == "FETCH"]
    assert fetch[0][2] == ("41", "(UID FLAGS BODY.PEEK[])")


def test_pending_flags_survive_failure_and_reconcile(synced):
    store, _, account, remote, engine = synced
    message = store.messages()[0]
    store.patch_message(message["id"], {"read": True, "starred": True})
    remote.fail_store = True
    assert engine.sync_account(account)["ok"]
    assert store.message(message["id"])["read"]
    assert store.message(message["id"])["starred"]
    assert all(row["error"] for row in store.rows("SELECT * FROM outbox"))
    remote.fail_store = False
    engine.sync_account(account)
    assert not store.rows("SELECT * FROM outbox")
    assert remote.boxes["INBOX"][41][1] == {"\\Seen", "\\Flagged"}
    remote.boxes["INBOX"][41][1].clear()
    engine.sync_account(account)
    assert not store.message(message["id"])["read"]


def test_archive_move_retains_analysis_and_changes_remote_uid(synced):
    store, _, account, remote, engine = synced
    message = store.messages()[0]
    analysis = {"summary": "Discuss the project", "priority": "high", "action_items": []}
    store.execute("UPDATE messages SET analysis=?,category='updates',snoozed_until=? WHERE id=?",
                  (json.dumps(analysis), time.time() + 300, message["id"]))
    store.patch_message(message["id"], {"archived": True})
    engine.sync_account(account)
    assert not remote.boxes["INBOX"]
    archived = store.messages("archive")[0]
    assert archived["uid"] == 123
    assert archived["analysis"] == analysis
    assert archived["category"] == "updates"
    assert archived["snoozed_until"] > time.time()
    store.patch_message(archived["id"], {"archived": False})
    engine.sync_account(account)
    assert remote.boxes["INBOX"]
    assert not store.messages("archive")


def test_archive_without_move_copies_and_expunges_only_that_uid(synced):
    store, _, account, remote, engine = synced
    remote.capabilities = ("IMAP4REV1", "UIDPLUS")
    remote.boxes["INBOX"][42] = [raw_mail("Keep me", "<keep@example.com>"), {"\\Deleted"}]
    message = next(m for m in store.messages() if m["uid"] == 41)
    store.patch_message(message["id"], {"archived": True})
    engine.sync_account(account)
    assert 41 not in remote.boxes["INBOX"] and 42 in remote.boxes["INBOX"]
    assert remote.boxes["Archive"][123]
    assert not store.rows("SELECT * FROM outbox")
    assert ("INBOX", "EXPUNGE", ("41",)) in remote.operations


def test_uidvalidity_reset_does_not_apply_old_operations(synced):
    store, _, account, remote, engine = synced
    old = store.messages()[0]
    store.patch_message(old["id"], {"read": True})
    remote.validities["INBOX"] = "10"
    remote.boxes["INBOX"] = {41: [raw_mail("A different email", "<different@example.com>"), set()]}
    engine.sync_account(account)
    assert store.message(old["id"]) is None
    assert store.messages()[0]["subject"] == "A different email"
    assert not store.messages()[0]["read"]
    assert not any(op[1] == "STORE" for op in remote.operations)


def test_remote_expunges_and_new_mail(synced):
    store, _, account, remote, engine = synced
    del remote.boxes["INBOX"][41]
    remote.boxes["INBOX"][88] = [raw_mail("New one", "<new@example.com>"), {"\\Seen"}]
    engine.sync_account(account)
    assert len(store.messages()) == 1
    assert store.messages()[0]["uid"] == 88
    assert store.messages()[0]["read"]


def test_html_scripts_not_in_plain_email():
    message = EmailMessage()
    message["From"] = "Sender <sender@example.com>"
    message["List-Unsubscribe"] = "<mailto:unsubscribe@example.com>"
    message.set_content('<html><head><style>hidden</style></head><body>Hello<script>steal()</script><p>World</p></body></html>', subtype="html")
    parsed = parse_message(message.as_bytes(), "a", "INBOX", "1", 1)
    assert "Hello" in parsed["body"] and "World" in parsed["body"]
    assert "steal" not in parsed["body"] and "hidden" not in parsed["body"]
    assert parsed["category"] == "newsletters"


def test_smtp_requires_tls_and_preserves_reply_headers(account_data, monkeypatch):
    calls = []
    envelopes = []

    class SMTP:
        def __init__(self, host, port, timeout, **kwargs):
            calls.append((host, port, "context" in kwargs))

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def ehlo(self):
            pass

        def starttls(self, context):
            calls.append("starttls")

        def login(self, user, password):
            calls.append("login")

        def send_message(self, message, **kwargs):
            calls.append(message)
            envelopes.append(kwargs['to_addrs'])
            return {}

    monkeypatch.setattr("milo.mail.smtplib.SMTP_SSL", SMTP)
    monkeypatch.setattr("milo.mail.smtplib.SMTP", SMTP)
    draft = {"to": "Giulia <giulia@example.com>, ", "subject": "Re: Hello", "body": "Ci sono!"}
    original = {"message_id": "<thread@example.com>"}
    mail = send_mail(account_data, draft, original)
    assert calls[0][2] is True
    assert mail["In-Reply-To"] == original["message_id"]
    calls.clear()
    send_mail({**account_data, "smtp_port": 587, "smtp_security": "starttls"}, draft)
    assert calls.index("starttls") < calls.index("login")
    message = send_mail(account_data, {**draft, 'cc': 'Marco <marco@example.com>, giulia@example.com, '})
    assert 'marco@example.com' in message['Cc']
    assert envelopes[-1] == ['giulia@example.com', 'marco@example.com']
    with pytest.raises(ValueError):
        send_mail(account_data, {**draft, "to": "invalid"})


@pytest.mark.parametrize("to,cc", [
    ("recipient@example.com,", ""),
    ("Recipient <recipient@example.com>, ", "Other <other@example.com>, "),
    ('"Last, First" <recipient@example.com>, ', ""),
    ("", "other@example.com, "),
])
def test_recipient_completion_separators_are_not_empty_recipients(account_data, to, cc):
    from email.utils import getaddresses

    message = build_message(account_data, {"to": to, "cc": cc, "subject": "Forward", "body": "Original"})
    addresses = getaddresses([str(message[header]) for header in ("To", "Cc") if message[header]])
    assert addresses and all(address for _, address in addresses)
    assert {address for _, address in addresses} == ({"recipient@example.com"} if to else set()) | (
        {"other@example.com"} if cc else set())


@pytest.mark.parametrize("to", ["", ", ", "invalid", "recipient@example.com, invalid, ",
                                "recipient@example.com, broken@, ", "recipient@example.com\r\nBcc: hidden@example.com"])
def test_recipient_normalization_still_rejects_invalid_addresses(account_data, to):
    with pytest.raises(ValueError, match="destinatari validi"):
        build_message(account_data, {"to": to, "subject": "Forward", "body": "Original"})


def test_replies_quote_the_original_below_the_answer():
    account = {"email": "me@example.com"}
    draft = {"to": "anna@example.com", "subject": "Re: Cena", "body": "Volentieri!\n\n-- \nSeb", "mode": "reply"}
    original = {"message_id": "<cena@example.com>", "sender": "Anna Rossi", "sender_email": "anna@example.com",
                "date": 1792044000.0, "body": "Ci vediamo sabato?\n\nA."}
    body = build_message(account, draft, original).get_content()
    assert body.startswith("Volentieri!\n\n-- \nSeb\n\nIl giorno ")
    assert "Anna Rossi <anna@example.com> ha scritto:\n> Ci vediamo sabato?\n>\n> A.\n" in body
    already = {**draft, "body": "Ok\n\nIl giorno ieri Anna ha scritto:\n> Ci vediamo sabato?"}
    assert build_message(account, already, original).get_content().count("ha scritto:") == 1
    assert "ha scritto" not in build_message(account, {**draft, "mode": "forward"}, original).get_content()
    assert "ha scritto" not in build_message(account, draft, {**original, "body": ""}).get_content()
    assert "ha scritto" not in build_message(account, draft).get_content()


def test_preview_skips_newsletter_links():
    mail = EmailMessage()
    mail["From"] = "Brand <news@brand.example>"
    mail["Subject"] = "Ottobre"
    mail.set_content("<https://track.example/e/r?q=abc>\n[image: Logo]\nOfferta valida fino a domenica (https://brand.example/x)")
    parsed = parse_message(mail.as_bytes(), "account", "INBOX", "1", 1)
    assert parsed["preview"] == "Offerta valida fino a domenica"


def test_reads_do_not_wait_for_a_running_write(store, account_data):
    import threading
    account_id = store.add_account(account_data)
    holding, release = threading.Event(), threading.Event()

    def writer():
        with store.transaction():
            store.execute("UPDATE accounts SET name='Busy' WHERE id=?", (account_id,))
            assert store.rows("SELECT name FROM accounts")[0]["name"] == "Busy"
            holding.set()
            release.wait(5)

    thread = threading.Thread(target=writer)
    thread.start()
    assert holding.wait(5)
    started = time.monotonic()
    assert store.rows("SELECT name FROM accounts")[0]["name"] == "Personal"
    assert time.monotonic() - started < 0.5
    release.set()
    thread.join()
    assert store.rows("SELECT name FROM accounts")[0]["name"] == "Busy"


def test_short_lived_reader_threads_share_a_bounded_pool(store):
    import threading

    from milo.store import READER_POOL
    for _ in range(4):
        threads = [threading.Thread(target=store.rows, args=("SELECT pg_sleep(0.01)",)) for _ in range(30)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
    assert len(store._readers) <= READER_POOL
    count = store.rows("SELECT count(*) AS n FROM pg_stat_activity WHERE datname=current_database()")[0]["n"]
    assert count <= READER_POOL + 1


def test_original_mime_lives_compressed_outside_the_database(store, account_data):
    account_id = store.add_account(account_data)
    current = raw_mail("Current", "<current@example.com>")
    new_id = store.upsert_message(parse_message(current, account_id, "INBOX", "1", 2))
    path = store.blobs.path(new_id)
    assert path.exists() and path.read_bytes() != current and path.stat().st_mode & 0o777 == 0o600
    assert store.message(new_id, raw=True)["raw"] == current
    assert store.message_headers(new_id).startswith(b"From:")
    assert "raw" not in store.rows("SELECT * FROM messages WHERE id=?", (new_id,))[0]
    store.execute("DELETE FROM messages WHERE id=?", (new_id,))
    assert store.sweep_blobs() == 0 and path.exists()
    os.utime(path, (time.time() - 7200, time.time() - 7200))
    assert store.sweep_blobs() == 1 and not path.exists()


def test_search_uses_trigram_indexes(store, account_data):
    from milo.store import SEARCH_COLUMNS
    account_id = store.add_account(account_data)
    store.upsert_message(parse_message(raw_mail("Fattura ottobre", "<fattura@example.com>"), account_id, "INBOX", "1", 1))
    store.ensure_search_indexes()
    store.ensure_search_indexes()  # idempotent
    names = {row["indexname"] for row in store.rows("SELECT indexname FROM pg_indexes WHERE tablename='messages'")}
    assert {f"messages_search_{column}" for column in SEARCH_COLUMNS} <= names
    assert [row["subject"] for row in store.conversations("all", search="attura ott")] == ["Fattura ottobre"]
    with store.reader() as connection:
        connection.execute("SET enable_seqscan=off")
        try:
            plan = "\n".join(row["QUERY PLAN"] for row in connection.execute(
                "EXPLAIN SELECT id FROM messages WHERE sender ILIKE %(q)s OR sender_email ILIKE %(q)s "
                "OR subject ILIKE %(q)s OR body ILIKE %(q)s", {"q": "%fattura%"}).fetchall())
        finally:
            connection.execute("RESET enable_seqscan")
    assert "messages_search_body" in plan
