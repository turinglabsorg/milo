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
        (directory / "mail.sqlite").chmod(0o600)
        self.bootstrap = self.setting("bootstrap")
        if not self.setting("password") and not self.bootstrap:
            self.bootstrap = secrets.token_urlsafe(24)
            self.set_setting("bootstrap", self.bootstrap)
        if not self.setting("ai"):
            self.set_setting("ai", {"model": "mistral-large-4:cloud", "automatic": False,
                                    "cloud_consent": False})

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

    def setup(self, password, bootstrap):
        with self.lock:
            if self.setting("password") or not secrets.compare_digest(bootstrap, self.bootstrap or ""):
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
        for account in accounts:
            encrypted = account.pop("secret")
            if private:
                account["password"] = self.vault.decrypt(encrypted.encode()).decode()
        return accounts

    def add_account(self, data):
        value = dict(data)
        value["id"] = uuid.uuid4().hex
        value["secret"] = self.vault.encrypt(value.pop("password").encode()).decode()
        columns = list(value)
        self.execute(f"INSERT INTO accounts({','.join(columns)}) VALUES({','.join('?' for _ in columns)})",
                     tuple(value.values()))
        return value["id"]

    def message(self, message_id, raw=False):
        rows = self.rows("SELECT * FROM messages WHERE id=?", (message_id,))
        if not rows:
            return None
        return self.public_message(rows[0], raw)

    @staticmethod
    def public_message(row, raw=False):
        if not raw:
            row.pop("raw", None)
        if row.get("analysis"):
            row["analysis"] = json.loads(row["analysis"])
        return row

    def messages(self, view="inbox", category=None, account=None, search="", limit=500):
        clauses, params = [], []
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
