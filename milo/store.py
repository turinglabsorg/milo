import hashlib
import json
import os
import secrets
import sqlite3
import threading
import time
import uuid
from pathlib import Path

from cryptography.fernet import Fernet


class Store:
    def __init__(self, directory: Path):
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        directory.chmod(0o700)
        self.directory = directory
        self.lock = threading.RLock()
        key_path = directory / "vault.key"
        if not key_path.exists():
            fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as stream:
                stream.write(Fernet.generate_key())
        self.vault = Fernet(key_path.read_bytes())
        self.db = sqlite3.connect(directory / "mail.sqlite", check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            PRAGMA journal_mode=WAL;
            PRAGMA foreign_keys=ON;
            CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS accounts(
                id TEXT PRIMARY KEY, name TEXT, email TEXT, username TEXT, secret TEXT,
                imap_host TEXT, imap_port INTEGER, smtp_host TEXT, smtp_port INTEGER,
                smtp_security TEXT, color TEXT, last_sync REAL, error TEXT);
            CREATE TABLE IF NOT EXISTS messages(
                id TEXT PRIMARY KEY, account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                folder TEXT NOT NULL, uidvalidity TEXT NOT NULL, uid INTEGER NOT NULL,
                message_id TEXT, sender TEXT, sender_email TEXT, recipients TEXT, subject TEXT,
                body TEXT, preview TEXT, date REAL, read INTEGER DEFAULT 0, starred INTEGER DEFAULT 0,
                archived INTEGER DEFAULT 0, sent INTEGER DEFAULT 0, category TEXT DEFAULT 'people',
                snoozed_until REAL, analysis TEXT, raw BLOB,
                UNIQUE(account_id, folder, uidvalidity, uid));
            CREATE INDEX IF NOT EXISTS messages_date ON messages(date DESC);
            CREATE TABLE IF NOT EXISTS outbox(
                id TEXT PRIMARY KEY, message_id TEXT REFERENCES messages(id) ON DELETE CASCADE,
                kind TEXT, value TEXT, created REAL, error TEXT);
            CREATE TABLE IF NOT EXISTS drafts(id TEXT PRIMARY KEY, data TEXT, updated REAL);
            CREATE TABLE IF NOT EXISTS rules(id TEXT PRIMARY KEY, data TEXT);
        """)
        self.migrate()
        (directory / "mail.sqlite").chmod(0o600)
        self.bootstrap = self.setting("bootstrap")
        if not self.setting("password") and not self.bootstrap:
            self.bootstrap = secrets.token_urlsafe(24)
            self.set_setting("bootstrap", self.bootstrap)
        if not self.setting("ai"):
            self.set_setting("ai", {"model": "mistral-large-4:cloud", "automatic": False,
                                    "cloud_consent": False})

    def migrate(self):
        migrations = {
            "accounts": {"provider": "TEXT NOT NULL DEFAULT 'imap'", "enabled": "INTEGER NOT NULL DEFAULT 1"},
            "messages": {"provider_id": "TEXT", "thread_id": "TEXT", "labels": "TEXT",
                         "hidden": "INTEGER NOT NULL DEFAULT 0", "pinned": "INTEGER NOT NULL DEFAULT 0",
                         "trashed": "INTEGER NOT NULL DEFAULT 0", "content_version": "TEXT"},
        }
        with self.lock, self.db:
            for table, columns in migrations.items():
                existing = {row["name"] for row in self.db.execute(f"PRAGMA table_info({table})")}
                for name, definition in columns.items():
                    if name not in existing:
                        self.db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")
            self.db.executescript("""
                CREATE UNIQUE INDEX IF NOT EXISTS messages_provider_id ON messages(account_id,provider_id)
                    WHERE provider_id IS NOT NULL;
                CREATE TABLE IF NOT EXISTS oauth_states(state TEXT PRIMARY KEY, data TEXT, expires REAL);
                CREATE TABLE IF NOT EXISTS gmail_sync(
                    account_id TEXT PRIMARY KEY REFERENCES accounts(id) ON DELETE CASCADE,
                    history_id TEXT, history_page TEXT, backfill_page TEXT,
                    backfill_complete INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS gmail_scan(
                    account_id TEXT REFERENCES accounts(id) ON DELETE CASCADE,
                    provider_id TEXT, PRIMARY KEY(account_id,provider_id));
                CREATE INDEX IF NOT EXISTS messages_thread ON messages(account_id,thread_id);
                CREATE INDEX IF NOT EXISTS messages_conversation ON messages(account_id,COALESCE(thread_id,id));
            """)

    def encrypt_json(self, value):
        return self.vault.encrypt(json.dumps(value).encode()).decode()

    def decrypt_json(self, value):
        return json.loads(self.vault.decrypt(value.encode()).decode())

    def begin_oauth(self, state, data):
        with self.lock:
            self.execute("DELETE FROM oauth_states WHERE expires<?", (time.time(),))
            self.execute("INSERT INTO oauth_states VALUES(?,?,?)",
                         (hashlib.sha256(state.encode()).hexdigest(), self.encrypt_json(data), time.time()+600))

    def consume_oauth(self, state, browser):
        with self.lock:
            key = hashlib.sha256(state.encode()).hexdigest()
            rows = self.rows("SELECT * FROM oauth_states WHERE state=? AND expires>?", (key, time.time()))
            if not rows:
                return None
            data = self.decrypt_json(rows[0]["data"])
            if not secrets.compare_digest(data.get("browser", ""), browser or ""):
                return None
            self.execute("DELETE FROM oauth_states WHERE state=?", (key,))
            return data

    def google_account(self, address, credentials):
        with self.lock:
            existing = self.rows("SELECT id,provider,secret FROM accounts WHERE lower(email)=lower(?)", (address,))
            if existing and existing[0]["provider"] != "google":
                raise RuntimeError("Questo indirizzo è già collegato via IMAP.")
            if existing:
                account_id = existing[0]["id"]
                previous = self.decrypt_json(existing[0]["secret"])
                if not credentials.get("refresh_token"):
                    credentials["refresh_token"] = previous.get("refresh_token")
                if not credentials.get("refresh_token"):
                    raise RuntimeError("Google non ha fornito l'accesso persistente. Ricollega l'account.")
                self.execute("UPDATE accounts SET secret=?,error=NULL WHERE id=?",
                             (self.encrypt_json(credentials), account_id))
            else:
                if not credentials.get("refresh_token"):
                    raise RuntimeError("Google non ha fornito l'accesso persistente. Ricollega l'account concedendo l'accesso.")
                account_id = self.add_account({"name": address.split("@")[0], "email": address, "username": address,
                    "password": json.dumps(credentials), "provider": "google", "color": "#7770c8"})
            return account_id

    def google_credentials(self, account_id):
        rows = self.rows("SELECT secret FROM accounts WHERE id=? AND provider='google'", (account_id,))
        if not rows:
            raise RuntimeError("Account Google non trovato")
        return self.decrypt_json(rows[0]["secret"])

    def save_google_credentials(self, account_id, credentials, expected_secret=None):
        secret = self.encrypt_json(credentials)
        query = "UPDATE accounts SET secret=? WHERE id=? AND provider='google'"
        params = (secret, account_id)
        if expected_secret is not None:
            query += " AND secret=?"
            params += (expected_secret,)
        cursor = self.execute(query, params)
        return secret if cursor.rowcount else None

    def rows(self, query, params=()):
        with self.lock:
            return [dict(row) for row in self.db.execute(query, params).fetchall()]

    def execute(self, query, params=()):
        with self.lock, self.db:
            return self.db.execute(query, params)

    def setting(self, key):
        rows = self.rows("SELECT value FROM settings WHERE key=?", (key,))
        return json.loads(rows[0]["value"]) if rows else None

    def set_setting(self, key, value):
        self.execute("INSERT OR REPLACE INTO settings VALUES(?,?)", (key, json.dumps(value)))

    def setup_allowed(self, token):
        with self.lock:
            return bool(token and self.bootstrap and not self.setting("password")
                        and secrets.compare_digest(token.encode(), self.bootstrap.encode()))

    def setup(self, password, bootstrap):
        with self.lock:
            if not self.setup_allowed(bootstrap):
                return False
            salt = secrets.token_hex(16)
            self.set_setting("password", {"salt": salt, "hash": self.hash_password(password, salt)})
            self.set_setting("bootstrap", None)
            self.bootstrap = None
            return True

    @staticmethod
    def hash_password(password, salt):
        return hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()

    def login(self, password):
        saved = self.setting("password")
        return bool(saved and secrets.compare_digest(self.hash_password(password, saved["salt"]), saved["hash"]))

    def new_session(self):
        token = secrets.token_urlsafe(32)
        self.execute("DELETE FROM sessions WHERE expires<?", (time.time(),))
        self.execute("INSERT INTO sessions VALUES(?,?)", (hashlib.sha256(token.encode()).hexdigest(),
                                                        time.time() + 30 * 86400))
        return token

    def valid_session(self, token):
        if not token:
            return False
        return bool(self.rows("SELECT token FROM sessions WHERE token=? AND expires>?",
                              (hashlib.sha256(token.encode()).hexdigest(), time.time())))

    def logout(self, token):
        self.execute("DELETE FROM sessions WHERE token=?", (hashlib.sha256(token.encode()).hexdigest(),))

    def accounts(self, private=False):
        accounts = self.rows("SELECT * FROM accounts ORDER BY rowid")
        return [self.public_account(account, private) for account in accounts]

    def account(self, account_id, private=False):
        rows = self.rows("SELECT * FROM accounts WHERE id=?", (account_id,))
        return self.public_account(rows[0], private) if rows else None

    def public_account(self, account, private=False):
        encrypted = account.pop("secret")
        if private and account["provider"] == "imap":
            account["password"] = self.vault.decrypt(encrypted.encode()).decode()
        return account

    def update_account(self, account_id, patch):
        allowed = {"name", "enabled", "color", "username", "password", "imap_host", "imap_port", "smtp_host", "smtp_port", "smtp_security"}
        if set(patch) - allowed or any(value is None for value in patch.values()):
            raise ValueError("Impostazioni account non valide")
        with self.lock:
            account = self.account(account_id)
            if not account:
                raise ValueError("Account non trovato")
            connection = set(patch) - {"name", "enabled", "color"}
            if account["provider"] == "google" and connection:
                raise ValueError("Per aggiornare l'accesso Google usa Ricollega")
            values = dict(patch)
            if "password" in values:
                values["secret"] = self.vault.encrypt(values.pop("password").encode()).decode()
            if connection:
                values.update(error=None, last_sync=None)
            if values:
                fields = ",".join(f"{key}=?" for key in values)
                self.execute(f"UPDATE accounts SET {fields} WHERE id=?", (*values.values(), account_id))
            return self.account(account_id)

    def add_account(self, data):
        value = dict(data)
        value["id"] = uuid.uuid4().hex
        value["secret"] = self.vault.encrypt(value.pop("password").encode()).decode()
        columns = list(value)
        self.execute(f"INSERT INTO accounts({','.join(columns)}) VALUES({','.join('?' for _ in columns)})",
                     tuple(value.values()))
        return value["id"]

    def message(self, message_id, raw=False, metadata=False):
        fields = self.message_fields(metadata, raw)
        rows = self.rows(f"SELECT {fields} FROM messages WHERE id=?", (message_id,))
        if not rows:
            return None
        return self.public_message(rows[0], raw)

    @staticmethod
    def message_fields(metadata=False, raw=False):
        fields = "id,account_id,thread_id,provider_id,message_id,sender,sender_email,recipients,subject,preview,date,read,starred,archived,sent,category,snoozed_until,analysis,pinned,trashed,hidden,content_version"
        return "*" if raw else fields if metadata else fields + ",folder,uidvalidity,uid,body,labels"

    @staticmethod
    def public_message(row, raw=False):
        if not raw:
            row.pop("raw", None)
        if row.get("analysis"):
            row["analysis"] = json.loads(row["analysis"])
        return row

    def messages(self, view="inbox", category=None, account=None, search="", limit=500):
        clauses, params = ["hidden=0", "trashed=0"], []
        if view == "inbox":
            clauses.extend(["archived=0", "sent=0", "(snoozed_until IS NULL OR snoozed_until<=?)"])
            params.append(time.time())
        elif view == "starred":
            clauses.append("starred=1")
        elif view == "archive":
            clauses.append("archived=1 AND sent=0")
        elif view == "sent":
            clauses.append("sent=1")
        elif view == "snoozed":
            clauses.append("snoozed_until>?")
            params.append(time.time())
        if category:
            clauses.append("category=?")
            params.append(category)
        if account:
            clauses.append("account_id=?")
            params.append(account)
        if search:
            clauses.append("(sender LIKE ? OR sender_email LIKE ? OR subject LIKE ? OR body LIKE ?)")
            params.extend([f"%{search}%"] * 4)
        where = " AND ".join(clauses) or "1"
        return [self.public_message(row) for row in self.rows(
            f"SELECT * FROM messages WHERE {where} ORDER BY date DESC LIMIT ?", (*params, limit))]

    def upsert_message(self, data):
        with self.lock:
            existing = self.rows("SELECT id FROM messages WHERE account_id=? AND folder=? AND uidvalidity=? AND uid=?",
                                 (data["account_id"], data["folder"], data["uidvalidity"], data["uid"]))
            if existing:
                return existing[0]["id"]
            data = dict(data)
            data["content_version"] = hashlib.sha256(data["raw"]).hexdigest()
            if data.get("thread_id"):
                pinned = self.rows("SELECT MAX(pinned) AS pinned FROM messages WHERE account_id=? AND thread_id=?",
                                   (data["account_id"], data["thread_id"]))
                data["pinned"] = pinned[0]["pinned"] or 0
            data["id"] = uuid.uuid4().hex
            for rule in self.rules():
                field = {"sender": data.get("sender_email", ""), "subject": data.get("subject", ""),
                         "body": data.get("body", "")}[rule["field"]]
                if rule["contains"].casefold() in field.casefold():
                    data["category"] = rule["category"]
                    break
            columns = list(data)
            self.execute(f"INSERT INTO messages({','.join(columns)}) VALUES({','.join('?' for _ in columns)})",
                         tuple(data.values()))
            return data["id"]

    def patch_message(self, message_id, patch):
        with self.lock, self.db:
            if not self.message(message_id):
                return False
            for key, value in patch.items():
                self.db.execute(f"UPDATE messages SET {key}=? WHERE id=?", (value, message_id))
                if key in {"read", "starred", "archived"}:
                    self.db.execute("DELETE FROM outbox WHERE message_id=? AND kind=?", (message_id, key))
                    self.db.execute("INSERT INTO outbox VALUES(?,?,?,?,?,NULL)",
                                    (uuid.uuid4().hex, message_id, key, json.dumps(value), time.time()))
            return True

    def conversation(self, message_id, raw=False, metadata=False):
        message = self.message(message_id, metadata=True)
        if not message:
            return []
        if not message.get("thread_id"):
            return [self.message(message_id, raw=raw, metadata=metadata)]
        fields = self.message_fields(metadata, raw)
        return [self.public_message(row, raw=raw) for row in self.rows(
            f"SELECT {fields} FROM messages WHERE account_id=? AND thread_id=? AND hidden=0 AND trashed=0 ORDER BY date,id",
            (message["account_id"], message["thread_id"]))]

    def patch_conversation(self, message_id, patch):
        with self.lock, self.db:
            messages = self.conversation(message_id)
            for message in messages:
                self.patch_message(message["id"], patch)
            return bool(messages)

    def trash_conversation(self, message_id):
        with self.lock, self.db:
            messages = self.conversation(message_id)
            for message in messages:
                self.db.execute("UPDATE messages SET trashed=1 WHERE id=?", (message["id"],))
                self.db.execute("DELETE FROM outbox WHERE message_id=?", (message["id"],))
                self.db.execute("INSERT INTO outbox VALUES(?,?,?,?,?,NULL)",
                                (uuid.uuid4().hex, message["id"], "trash", "true", time.time()))
            return bool(messages)

    def conversations(self, view="inbox", category=None, account=None, search="", limit=100):
        # Fetch only list metadata. Bodies and MIME blobs belong to the reader.
        clauses, params = ["hidden=0", "trashed=0"], []
        views = {"inbox": "archived=0 AND sent=0 AND (snoozed_until IS NULL OR snoozed_until<=?)",
                 "starred": "starred=1", "archive": "archived=1 AND sent=0", "sent": "sent=1",
                 "snoozed": "snoozed_until>?"}
        if view in views:
            clauses.append(views[view])
            if view in {"inbox", "snoozed"}:
                params.append(time.time())
        if category:
            clauses.append("category=?")
            params.append(category)
        if account:
            clauses.append("account_id=?")
            params.append(account)
        if search:
            clauses.append("(sender LIKE ? OR sender_email LIKE ? OR subject LIKE ? OR body LIKE ?)")
            params.extend([f"%{search}%"] * 4)
        rows = self.rows("""
            WITH eligible AS (
                SELECT account_id,COALESCE(thread_id,id) AS thread FROM messages WHERE """ + " AND ".join(clauses) + """
                GROUP BY account_id,COALESCE(thread_id,id)
            ), ranked AS (
                SELECT m.id,m.account_id,m.thread_id,m.sender,m.sender_email,m.subject,m.preview,m.date,
                       m.read,m.starred,m.archived,m.sent,m.category,m.snoozed_until,
                       MAX(m.pinned) OVER w AS pinned,COUNT(*) OVER w AS message_count,
                       SUM(m.read=0 AND m.sent=0) OVER w AS unread_count,
                       SUM(m.analysis IS NOT NULL) OVER w AS analyzed_count,
                       ROW_NUMBER() OVER (PARTITION BY m.account_id,COALESCE(m.thread_id,m.id) ORDER BY m.date DESC,m.id) AS rank
                FROM messages m JOIN eligible e ON m.account_id=e.account_id AND COALESCE(m.thread_id,m.id)=e.thread
                WHERE m.hidden=0 AND m.trashed=0
                WINDOW w AS (PARTITION BY m.account_id,COALESCE(m.thread_id,m.id))
            ) SELECT * FROM ranked WHERE rank=1 ORDER BY pinned DESC,date DESC LIMIT ?
            """, (*params, limit))
        for row in rows:
            row.pop("rank")
            row["read"] = int(not row["unread_count"])
            row["replied"] = bool(row["sent"])
        return rows

    def reconcile_flags(self, message_id, read, starred):
        with self.lock:
            pending = {r["kind"] for r in self.rows("SELECT kind FROM outbox WHERE message_id=?", (message_id,))}
            for key, value in (("read", read), ("starred", starred)):
                if key not in pending:
                    self.execute(f"UPDATE messages SET {key}=? WHERE id=?", (value, message_id))

    def rules(self):
        return [{"id": row["id"], **json.loads(row["data"])} for row in self.rows("SELECT * FROM rules")]

    def add_rule(self, data):
        rule_id = uuid.uuid4().hex
        self.execute("INSERT INTO rules VALUES(?,?)", (rule_id, json.dumps(data)))
        return rule_id

    def close(self):
        self.db.close()
