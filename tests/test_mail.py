import json
import time
from email.message import EmailMessage

import pytest

from milo.mail import SyncEngine, parse_message, send_mail


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
    draft = {"to": "Giulia <giulia@example.com>", "subject": "Re: Hello", "body": "Ci sono!"}
    original = {"message_id": "<thread@example.com>"}
    mail = send_mail(account_data, draft, original)
    assert calls[0][2] is True
    assert mail["In-Reply-To"] == original["message_id"]
    calls.clear()
    send_mail({**account_data, "smtp_port": 587, "smtp_security": "starttls"}, draft)
    assert calls.index("starttls") < calls.index("login")
    message = send_mail(account_data, {**draft, 'cc': 'Marco <marco@example.com>, giulia@example.com'})
    assert 'marco@example.com' in message['Cc']
    assert envelopes[-1] == ['giulia@example.com', 'marco@example.com']
    with pytest.raises(ValueError):
        send_mail(account_data, {**draft, "to": "invalid"})


def test_preview_skips_newsletter_links():
    mail = EmailMessage()
    mail["From"] = "Brand <news@brand.example>"
    mail["Subject"] = "Ottobre"
    mail.set_content("<https://track.example/e/r?q=abc>\n[image: Logo]\nOfferta valida fino a domenica (https://brand.example/x)")
    parsed = parse_message(mail.as_bytes(), "account", "INBOX", "1", 1)
    assert parsed["preview"] == "Offerta valida fino a domenica"


def test_existing_link_previews_are_rewritten_once(store, account_data):
    account_id = store.add_account(account_data)
    store.execute("INSERT INTO messages(id,account_id,folder,uidvalidity,uid,body,preview) VALUES('m',?,'INBOX','1',1,?,?)",
                  (account_id, "<https://t.example/x> Ciao", "<https://t.example/x> Ciao"))
    store.execute("PRAGMA user_version=0")
    store.rewrite_link_previews(batch=1)
    assert store.rows("SELECT preview FROM messages WHERE id='m'")[0]["preview"] == "Ciao"


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


def test_original_mime_moves_out_of_messages_without_losing_access(store, account_data):
    account_id = store.add_account(account_data)
    legacy, current = raw_mail("Legacy", "<legacy@example.com>"), raw_mail("Current", "<current@example.com>")
    store.execute("INSERT INTO messages(id,account_id,folder,uidvalidity,uid,subject,raw) VALUES('old',?,'INBOX','1',1,'Legacy',?)",
                  (account_id, legacy))
    new_id = store.upsert_message(parse_message(current, account_id, "INBOX", "1", 2))
    store.execute("PRAGMA user_version=1")
    assert store.message("old", raw=True)["raw"] == legacy
    assert store.rows("SELECT raw FROM messages WHERE id=?", (new_id,))[0]["raw"] is None
    assert store.message(new_id, raw=True)["raw"] == current
    store.move_raw_out(batch=1)
    assert store.rows("PRAGMA user_version")[0]["user_version"] == 2
    assert not store.rows("SELECT id FROM messages WHERE raw IS NOT NULL")
    assert store.message("old", raw=True)["raw"] == legacy
    assert store.message_headers("old").startswith(b"From:")
    store.execute("DELETE FROM messages WHERE id='old'")
    assert not store.rows("SELECT id FROM message_raw WHERE id='old'")
