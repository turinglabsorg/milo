import hashlib
import json
import os
import re
import secrets
import shutil
import threading
import time
import uuid
import zlib
from contextlib import contextmanager
from email.utils import getaddresses
from pathlib import Path

import psycopg
from cryptography.fernet import Fernet
from psycopg.adapt import Dumper
from psycopg.rows import dict_row

LINK_NOISE = re.compile(r"<\s*(?:https?|mailto):[^>]*>|\[(?:image|cid|https?)\b[^\]]*\]|\(\s*https?://[^)]*\)|(?:https?://|www\.)\S+", re.I)

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, expires DOUBLE PRECISION NOT NULL);
CREATE TABLE IF NOT EXISTS accounts(
    seq BIGSERIAL, id TEXT PRIMARY KEY, name TEXT, email TEXT, username TEXT, secret TEXT,
    imap_host TEXT, imap_port INTEGER, smtp_host TEXT, smtp_port INTEGER, smtp_security TEXT, color TEXT,
    last_sync DOUBLE PRECISION, error TEXT, provider TEXT NOT NULL DEFAULT 'imap',
    enabled INTEGER NOT NULL DEFAULT 1, removing INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS messages(
    seq BIGSERIAL, id TEXT PRIMARY KEY, account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    folder TEXT NOT NULL, uidvalidity TEXT NOT NULL, uid BIGINT NOT NULL,
    message_id TEXT, sender TEXT, sender_email TEXT, recipients TEXT, subject TEXT,
    body TEXT, preview TEXT, date DOUBLE PRECISION, read INTEGER DEFAULT 0, starred INTEGER DEFAULT 0,
    archived INTEGER DEFAULT 0, sent INTEGER DEFAULT 0, category TEXT DEFAULT 'people',
    snoozed_until DOUBLE PRECISION, analysis TEXT, provider_id TEXT, thread_id TEXT, labels TEXT,
    hidden INTEGER NOT NULL DEFAULT 0, pinned INTEGER NOT NULL DEFAULT 0, trashed INTEGER NOT NULL DEFAULT 0,
    content_version TEXT, UNIQUE(account_id, folder, uidvalidity, uid));
CREATE INDEX IF NOT EXISTS messages_date ON messages(date DESC);
CREATE INDEX IF NOT EXISTS messages_recent ON messages(date DESC,id DESC) WHERE hidden=0 AND trashed=0;
CREATE UNIQUE INDEX IF NOT EXISTS messages_provider_id ON messages(account_id,provider_id) WHERE provider_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS messages_thread ON messages(account_id,thread_id);
CREATE INDEX IF NOT EXISTS messages_conversation ON messages(account_id,(COALESCE(thread_id,id)));
CREATE INDEX IF NOT EXISTS messages_message_id ON messages(account_id,message_id);
CREATE INDEX IF NOT EXISTS messages_sender ON messages(lower(sender_email)) WHERE hidden=0 AND trashed=0;
CREATE INDEX IF NOT EXISTS messages_inbox ON messages(account_id,(COALESCE(thread_id,id)))
    WHERE hidden=0 AND trashed=0 AND archived=0 AND sent=0;
-- Flags are strongly correlated (most Gmail mail is archived): give the planner joint statistics.
CREATE STATISTICS IF NOT EXISTS messages_flags (dependencies, mcv) ON archived, sent, hidden, trashed, category FROM messages;
CREATE INDEX IF NOT EXISTS messages_analyzed ON messages(account_id,(COALESCE(thread_id,id)))
    WHERE analysis IS NOT NULL AND hidden=0 AND trashed=0;
CREATE INDEX IF NOT EXISTS messages_catalogue ON messages(account_id,(COALESCE(thread_id,id)),date DESC,id)
    INCLUDE (thread_id,sender,sender_email,subject,preview,read,starred,archived,sent,category,
             snoozed_until,pinned,content_version)
    WHERE hidden=0 AND trashed=0;
CREATE TABLE IF NOT EXISTS outbox(
    id TEXT PRIMARY KEY, message_id TEXT REFERENCES messages(id) ON DELETE CASCADE ON UPDATE CASCADE,
    kind TEXT, value TEXT, created DOUBLE PRECISION, error TEXT);
CREATE TABLE IF NOT EXISTS drafts(id TEXT PRIMARY KEY, data TEXT, updated DOUBLE PRECISION);
CREATE TABLE IF NOT EXISTS rules(seq BIGSERIAL, id TEXT PRIMARY KEY, data TEXT);
CREATE TABLE IF NOT EXISTS oauth_states(state TEXT PRIMARY KEY, data TEXT, expires DOUBLE PRECISION);
CREATE TABLE IF NOT EXISTS gmail_sync(
    account_id TEXT PRIMARY KEY REFERENCES accounts(id) ON DELETE CASCADE,
    history_id TEXT, history_page TEXT, backfill_page TEXT, backfill_complete INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS gmail_scan(
    account_id TEXT REFERENCES accounts(id) ON DELETE CASCADE, provider_id TEXT, PRIMARY KEY(account_id,provider_id));
CREATE TABLE IF NOT EXISTS scheduled(
    draft_id TEXT PRIMARY KEY, send_at DOUBLE PRECISION NOT NULL, followup_days INTEGER, error TEXT,
    created DOUBLE PRECISION);
CREATE TABLE IF NOT EXISTS senders(
    email TEXT PRIMARY KEY, status TEXT, vip INTEGER NOT NULL DEFAULT 0, unsubscribed DOUBLE PRECISION,
    updated DOUBLE PRECISION);
CREATE TABLE IF NOT EXISTS todos(
    seq BIGSERIAL, id TEXT PRIMARY KEY, message_id TEXT NOT NULL, text TEXT NOT NULL, priority TEXT,
    kind TEXT NOT NULL DEFAULT 'action', created DOUBLE PRECISION, done DOUBLE PRECISION, accepted DOUBLE PRECISION);
ALTER TABLE todos ADD COLUMN IF NOT EXISTS accepted DOUBLE PRECISION;
CREATE INDEX IF NOT EXISTS todos_open ON todos(message_id) WHERE done IS NULL;
CREATE INDEX IF NOT EXISTS todos_message ON todos(message_id);
CREATE INDEX IF NOT EXISTS todos_accepted_open ON todos(message_id)
    WHERE done IS NULL AND (kind<>'action' OR accepted IS NOT NULL);
CREATE TABLE IF NOT EXISTS followups(
    id TEXT PRIMARY KEY, account_id TEXT NOT NULL, rfc_message_id TEXT, thread_id TEXT, subject TEXT,
    recipients TEXT, created DOUBLE PRECISION, due DOUBLE PRECISION, resolved DOUBLE PRECISION);
CREATE INDEX IF NOT EXISTS followups_open ON followups(due) WHERE resolved IS NULL;
-- People you wrote to, and people who wrote to you. Autocomplete reads this
-- instead of scanning message headers on every keystroke.
CREATE TABLE IF NOT EXISTS correspondents(
    email TEXT PRIMARY KEY, name TEXT NOT NULL DEFAULT '',
    last_sent DOUBLE PRECISION, last_seen DOUBLE PRECISION NOT NULL);
CREATE INDEX IF NOT EXISTS correspondents_recent ON correspondents(last_sent DESC) WHERE last_sent IS NOT NULL;
CREATE TABLE IF NOT EXISTS devices(
    token TEXT PRIMARY KEY, environment TEXT NOT NULL, created DOUBLE PRECISION, last_seen DOUBLE PRECISION);
CREATE TABLE IF NOT EXISTS draft_attachments(
    id TEXT PRIMARY KEY, draft_id TEXT NOT NULL, name TEXT NOT NULL, type TEXT NOT NULL,
    size BIGINT NOT NULL, created DOUBLE PRECISION NOT NULL);
CREATE INDEX IF NOT EXISTS draft_attachments_draft ON draft_attachments(draft_id, created);
"""
# Most providers refuse messages above 25 MB once encoded; base64 adds a third.
ATTACHMENT_LIMIT = 18 * 1024 * 1024
DRAFT_ID = re.compile(r"[A-Za-z0-9_-]{1,80}")


def address_pairs(header):
    """Display name and lowercase address from a To/Cc header. Skips junk."""
    pairs = []
    for name, email in getaddresses([header or ""]):
        email = email.strip().lower()
        if "@" not in email or any(character in email for character in " \t\r\n,;<>"):
            continue
        name = name.strip().strip('"')[:200]
        if name.lower() == email:
            name = ""
        pairs.append((name, email[:320]))
    return pairs


def like_contains(text):
    """A contains-pattern whose % and _ are literal."""
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def preview_text(body):
    """List previews show readable text, not the tracking links newsletters open with."""
    return re.sub(r"\s+", " ", LINK_NOISE.sub(" ", body or "")).strip()[:240]


def database_url(directory):
    """The archive's Postgres. The password stays in a file next to the data, never in the URL."""
    url = os.environ.get("MILO_DATABASE_URL")
    if not url:
        raise RuntimeError("MILO_DATABASE_URL non configurato: Milo usa PostgreSQL.")
    password_file = os.environ.get("MILO_DATABASE_PASSWORD_FILE")
    if password_file:
        return psycopg.conninfo.make_conninfo(url, password=Path(password_file).read_text().strip())
    return url


def sql(query, params=()):
    """Queries are written with ? placeholders; psycopg wants %s and, with parameters, literal % doubled."""
    return query.replace("%", "%%").replace("?", "%s") if params else query


class FlagDumper(Dumper):
    """Flags are INTEGER columns: store Python booleans as 0/1."""
    oid = psycopg.adapters.types["int4"].oid

    def dump(self, obj):
        return b"1" if obj else b"0"


def clean(value):
    return value.replace("\x00", "") if isinstance(value, str) else value


class Blobs:
    """Original MIME as compressed files, one per message, outside the database."""

    def __init__(self, root: Path):
        self.root = root
        root.mkdir(parents=True, exist_ok=True, mode=0o700)

    def path(self, message_id):
        return self.root / message_id[:2] / f"{message_id}.eml.z"

    def put(self, message_id, raw):
        path = self.path(message_id)
        path.parent.mkdir(exist_ok=True, mode=0o700)
        temporary = path.with_suffix(f".{uuid.uuid4().hex}.tmp")
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(zlib.compress(raw, 6))
        os.replace(temporary, path)

    def get(self, message_id):
        try:
            return zlib.decompress(self.path(message_id).read_bytes())
        except FileNotFoundError:
            return None

    def head(self, message_id, size):
        try:
            data = self.path(message_id).read_bytes()
        except FileNotFoundError:
            return b""
        decompressor = zlib.decompressobj()
        return decompressor.decompress(data, size)

    def sweep(self, known, stop=lambda: False):
        """Remove files whose message no longer exists (deleted, purged or replaced)."""
        removed = 0
        for directory in self.root.iterdir():
            if stop():
                break
            if not directory.is_dir():
                continue
            for path in directory.iterdir():
                message_id = path.name.split(".", 1)[0]
                # Originals are written before their row: only files older than an hour can be orphans.
                if time.time() - path.stat().st_mtime < 3600:
                    continue
                if path.suffix == ".tmp" or (path.name.endswith(".eml.z") and message_id not in known):
                    path.unlink(missing_ok=True)
                    removed += 1
        return removed


class WriterLock:
    """Reentrant lock that knows its owner, so reads inside a write see that write."""

    def __init__(self):
        self._lock = threading.RLock()
        self._owner = None
        self._depth = 0

    def acquire(self, blocking=True, timeout=-1):
        if not self._lock.acquire(blocking, timeout):
            return False
        self._owner = threading.get_ident()
        self._depth += 1
        return True

    def release(self):
        self._depth -= 1
        if not self._depth:
            self._owner = None
        self._lock.release()

    __enter__ = acquire

    def __exit__(self, *exc):
        self.release()

    def owned(self):
        return self._owner == threading.get_ident()


READER_POOL = 12
SEARCH_COLUMNS = ("sender", "sender_email", "subject", "preview", "body")
VISIBLE_WRITE = re.compile(r"\s*(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+(?:messages|drafts|scheduled|todos|senders|accounts|settings|rules|followups)\b", re.I)


class Store:
    def __init__(self, directory: Path, dsn=None):
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        directory.chmod(0o700)
        self.directory = directory
        self.dsn = dsn or database_url(directory)
        self.lock = WriterLock()
        # Bounded reader pool: worker threads come and go (anyio retires idle
        # ones), so per-thread connections leaked until Postgres refused clients.
        self._readers = []
        self._idle = []
        self._slots = threading.BoundedSemaphore(READER_POOL)
        self._pool_lock = threading.Lock()
        self._txn_depth = 0
        self.on_mail_change = lambda: None
        # Any write clients would see in a list or thread (drives /api/events).
        self.on_change = lambda: None
        self._changed_in_txn = False
        self.on_new_message = lambda data: None
        key_path = directory / "vault.key"
        if not key_path.exists():
            fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as stream:
                stream.write(Fernet.generate_key())
        self.vault = Fernet(key_path.read_bytes())
        self.blobs = Blobs(directory / "blobs")
        self.db = self.connect()
        with self.lock:
            # Serialize schema creation across processes sharing the archive.
            self.db.execute("SELECT pg_advisory_lock(80250)")
            try:
                # Re-running the DDL takes table locks even when nothing changes; that
                # deadlocks with a concurrent index build, so run it only when it changed.
                version = hashlib.sha256(SCHEMA.encode()).hexdigest()
                applied = self.db.execute("SELECT to_regclass('settings') IS NOT NULL AS ready").fetchone()["ready"] and \
                    self.db.execute("SELECT value FROM settings WHERE key='schema'").fetchone()
                if not applied or json.loads(applied["value"]) != version:
                    self.db.execute(SCHEMA)
                    self.db.execute("INSERT INTO settings VALUES('schema',%s) ON CONFLICT(key) DO UPDATE "
                                    "SET value=excluded.value", (json.dumps(version),))
            finally:
                self.db.execute("SELECT pg_advisory_unlock(80250)")
        self.bootstrap = self.setting("bootstrap")
        if not self.setting("password") and not self.bootstrap:
            self.bootstrap = secrets.token_urlsafe(24)
            self.set_setting("bootstrap", self.bootstrap)
        if not self.setting("ai"):
            self.set_setting("ai", {"model": "deepseek-v4.1-flash:cloud", "automatic": False,
                                    "cloud_consent": False})

    def connect(self):
        connection = psycopg.connect(self.dsn, autocommit=True, row_factory=dict_row,
                                     application_name="milo")
        connection.adapters.register_dumper(bool, FlagDumper)
        return connection

    def writer(self):
        if self.db.closed or self.db.broken:
            self.db = self.connect()
        return self.db

    @contextmanager
    def reader(self):
        """Borrow a pooled connection: readers never wait for the sync writer."""
        self._slots.acquire()
        connection = None
        try:
            with self._pool_lock:
                while self._idle and connection is None:
                    candidate = self._idle.pop()
                    if candidate.closed or candidate.broken:
                        self._readers.remove(candidate)
                        candidate.close()
                    else:
                        connection = candidate
            if connection is None:
                connection = self.connect()
                with self._pool_lock:
                    self._readers.append(connection)
            yield connection
        finally:
            if connection is not None:
                with self._pool_lock:
                    self._idle.append(connection)
            self._slots.release()

    def rows(self, query, params=()):
        if self.lock.owned():
            return self.writer().execute(sql(query, params), params or None).fetchall()
        with self.reader() as connection:
            return connection.execute(sql(query, params), params or None).fetchall()

    def execute(self, query, params=()):
        with self.lock:
            result = self.writer().execute(sql(query, params), tuple(clean(value) for value in params) or None)
            self._changed(query)
            return result

    def executemany(self, query, params):
        with self.lock, self.writer().cursor() as cursor:
            cursor.executemany(sql(query, True), [tuple(clean(value) for value in row) for row in params])
            self._changed(query)

    def _changed(self, query):
        if VISIBLE_WRITE.match(query):
            if self._txn_depth:
                self._changed_in_txn = True
            else:
                self.on_change()

    @contextmanager
    def transaction(self):
        """Batch writes into one commit. Callers must not do network I/O inside."""
        with self.lock:
            if self._txn_depth:
                self._txn_depth += 1
                try:
                    yield
                finally:
                    self._txn_depth -= 1
                return
            self._txn_depth += 1
            self._changed_in_txn = False
            try:
                with self.writer().transaction():
                    yield
            finally:
                self._txn_depth -= 1
            # Signal only once the batch is committed and visible to readers.
            if self._changed_in_txn:
                self._changed_in_txn = False
                self.on_change()

    def set_raw(self, message_id, raw):
        self.blobs.put(message_id, raw)

    # Outgoing attachments: files under draft-attachments/<draft>/<id>, rows for metadata.

    def attachment_path(self, draft_id, attachment_id=None):
        if not DRAFT_ID.fullmatch(draft_id) or (attachment_id is not None and not DRAFT_ID.fullmatch(attachment_id)):
            raise ValueError("Bozza non valida")
        folder = self.directory / "draft-attachments" / draft_id
        return folder / attachment_id if attachment_id else folder

    def draft_attachments(self, draft_id):
        return self.rows("SELECT id,name,type,size FROM draft_attachments WHERE draft_id=? ORDER BY created",
                         (draft_id,))

    def add_draft_attachment(self, draft_id, name, content_type, data):
        name = re.sub(r"[\x00-\x1f/\\]+", " ", name or "").strip()[:200] or "allegato"
        if not re.fullmatch(r"[\w.+-]+/[\w.+-]+", content_type or ""):
            content_type = "application/octet-stream"
        attachment_id = uuid.uuid4().hex
        path = self.attachment_path(draft_id, attachment_id)
        with self.lock:
            used = sum(row["size"] for row in self.draft_attachments(draft_id))
            if used + len(data) > ATTACHMENT_LIMIT:
                raise ValueError("Gli allegati superano 18 MB: il messaggio verrebbe rifiutato.")
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
            self.execute("INSERT INTO draft_attachments VALUES(?,?,?,?,?,?)",
                         (attachment_id, draft_id, name, content_type, len(data), time.time()))
        return {"id": attachment_id, "name": name, "type": content_type, "size": len(data)}

    def draft_attachment_files(self, draft_id):
        return [{**row, "data": self.attachment_path(draft_id, row["id"]).read_bytes()}
                for row in self.draft_attachments(draft_id)]

    def remove_draft_attachments(self, draft_id, attachment_id=None):
        folder = self.attachment_path(draft_id)
        if attachment_id:
            path = self.attachment_path(draft_id, attachment_id)
            removed = self.execute("DELETE FROM draft_attachments WHERE draft_id=? AND id=?",
                                   (draft_id, attachment_id)).rowcount
            path.unlink(missing_ok=True)
            return bool(removed)
        self.execute("DELETE FROM draft_attachments WHERE draft_id=?", (draft_id,))
        shutil.rmtree(folder, ignore_errors=True)
        return True

    def sweep_draft_attachments(self, older_than=86400):
        """Attachments whose draft disappeared (sent elsewhere, account removed)."""
        orphans = self.rows("SELECT DISTINCT draft_id FROM draft_attachments a WHERE created<? AND NOT EXISTS("
                            "SELECT 1 FROM drafts d WHERE d.id=a.draft_id)", (time.time() - older_than,))
        for row in orphans:
            self.remove_draft_attachments(row["draft_id"])
        return len(orphans)

    def ensure_search_indexes(self, stop=lambda: False):
        """Trigram indexes let the existing ILIKE searches use an index.

        Built CONCURRENTLY on a dedicated connection: mail keeps syncing and
        startup never waits (the health check would restart a slow container).
        """
        with self.connect() as connection:
            self._maintenance = connection
            # One builder at a time across processes; others simply skip.
            if not connection.execute("SELECT pg_try_advisory_lock(80251) AS locked").fetchone()["locked"]:
                return
            connection.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
            for column in SEARCH_COLUMNS:
                if stop():
                    return
                name = f"messages_search_{column}"
                state = connection.execute("SELECT i.indisvalid FROM pg_class c JOIN pg_index i ON i.indexrelid=c.oid "
                                           "WHERE c.relname=%s", (name,)).fetchone()
                if state and state["indisvalid"]:
                    continue
                if state:  # an interrupted concurrent build leaves an invalid index
                    connection.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {name}")
                connection.execute(f"CREATE INDEX CONCURRENTLY {name} ON messages USING gin ({column} gin_trgm_ops)")

    def cancel_maintenance(self):
        """Stop a long index build at shutdown; the next start rebuilds it."""
        connection = getattr(self, "_maintenance", None)
        if connection and not connection.closed:
            connection.cancel_safe()

    def sweep_blobs(self, stop=lambda: False):
        known = {row["id"] for row in self.rows("SELECT id FROM messages")}
        return self.blobs.sweep(known, stop)

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

    def setting(self, key):
        rows = self.rows("SELECT value FROM settings WHERE key=?", (key,))
        return json.loads(rows[0]["value"]) if rows else None

    def set_setting(self, key, value):
        if key == "ai":
            with self.transaction():
                if value.get("automatic") and not (self.setting("ai") or {}).get("automatic"):
                    self.reset_automatic_analysis()
                self.set_progress(key, value)
                self._changed("UPDATE settings")
            return
        self.execute("INSERT INTO settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                     (key, json.dumps(value)))

    def reset_automatic_analysis(self):
        sequence = self.rows(
            "SELECT CASE WHEN is_called THEN last_value ELSE 0 END AS seq FROM messages_seq_seq")[0]["seq"]
        self.set_progress("ai_automatic_boundary", {"since": time.time(), "after_seq": sequence})

    def set_progress(self, key, value):
        """Like set_setting, but clients are not told: a backfill cursor is not a visible change."""
        with self.lock:
            self.writer().execute(
                "INSERT INTO settings VALUES(%s,%s) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, json.dumps(value)))

    def own_addresses(self):
        return {row["email"].strip().lower() for row in self.rows("SELECT email FROM accounts") if row.get("email")}

    def remember_correspondent(self, email, name, when, sent_to):
        email = (email or "").strip().lower()
        if "@" not in email or any(character in email for character in " \t\r\n,;<>"):
            return
        name = (name or "").strip().strip('"')[:200]
        if name.lower() == email:
            name = ""
        when = float(when or time.time())
        self.execute(
            "INSERT INTO correspondents(email,name,last_sent,last_seen) VALUES(?,?,?,?) "
            "ON CONFLICT(email) DO UPDATE SET "
            "last_sent=GREATEST(correspondents.last_sent, excluded.last_sent), "
            "last_seen=GREATEST(correspondents.last_seen, excluded.last_seen), "
            "name=CASE WHEN excluded.last_seen>=correspondents.last_seen AND excluded.name<>'' THEN excluded.name "
            "WHEN correspondents.name='' THEN excluded.name ELSE correspondents.name END",
            (email[:320], name, when if sent_to else None, when))

    def note_addresses(self, header, when, sent_to=True, own=None):
        own = self.own_addresses() if own is None else own
        for name, email in address_pairs(header):
            if email not in own:
                self.remember_correspondent(email, name, when, sent_to)

    def note_message_correspondents(self, data, own=None):
        """Sent mail records who you wrote to. Received mail records who wrote to you."""
        own = self.own_addresses() if own is None else own
        when = data.get("date") or time.time()
        if data.get("sent"):
            self.note_addresses(data.get("recipients"), when, True, own)
        else:
            email = (data.get("sender_email") or "").strip().lower()
            if email and email not in own:
                self.remember_correspondent(email, data.get("sender") or "", when, False)

    def backfill_correspondents(self, stop=lambda: False):
        """One pass over mail already in the archive. New mail is recorded as it arrives."""
        if self.setting("correspondents_done"):
            return
        cursor = self.setting("correspondents_seq") or 0
        while not stop():
            batch = self.rows(
                "SELECT seq,sent,sender,sender_email,recipients,date FROM messages WHERE seq>? ORDER BY seq LIMIT 400",
                (cursor,))
            if not batch:
                self.set_progress("correspondents_done", True)
                return
            own = self.own_addresses()
            with self.transaction():
                for row in batch:
                    self.note_message_correspondents(row, own)
                cursor = batch[-1]["seq"]
                self.set_progress("correspondents_seq", cursor)

    def _recent_sent_recipients(self, limit=400):
        found = {}
        rows = self.rows(
            "SELECT recipients,date FROM messages WHERE sent=1 AND hidden=0 AND recipients<>'' "
            "ORDER BY date DESC LIMIT ?", (limit,))
        for row in rows:
            when = row["date"] or 0
            for name, email in address_pairs(row["recipients"]):
                previous = found.get(email)
                if previous is None or when >= previous[1]:
                    found[email] = (name or (previous[0] if previous else ""), when)
        return found

    def recipient_suggestions(self, query="", limit=8):
        """Empty query: people you wrote to most recently. Otherwise name or address search."""
        query = " ".join((query or "").split())[:80]
        own = self.own_addresses()
        ranked = {}

        def add(email, name, last_sent, last_seen):
            if not email or email in own:
                return
            current = ranked.get(email)
            if current and (current["last_sent"] or 0, current["last_seen"] or 0) >= (last_sent or 0, last_seen or 0):
                if name and not current["name"]:
                    current["name"] = name
                return
            ranked[email] = {"name": name or (current["name"] if current else ""), "email": email,
                             "last_sent": last_sent, "last_seen": last_seen or last_sent}

        if query:
            pattern = like_contains(query)
            for row in self.rows(
                    "SELECT email,name,last_sent,last_seen FROM correspondents "
                    "WHERE email ILIKE ? OR name ILIKE ? "
                    "ORDER BY (last_sent IS NOT NULL) DESC, COALESCE(last_sent, last_seen) DESC LIMIT 24",
                    (pattern, pattern)):
                add(row["email"], row["name"], row["last_sent"], row["last_seen"])
        else:
            for row in self.rows(
                    "SELECT email,name,last_sent,last_seen FROM correspondents WHERE last_sent IS NOT NULL "
                    "ORDER BY last_sent DESC LIMIT 24"):
                add(row["email"], row["name"], row["last_sent"], row["last_seen"])
        # Until the archive has been walked, recent sent mail and incoming senders fill the gap.
        if not self.setting("correspondents_done"):
            needle = query.casefold()
            for email, (name, when) in self._recent_sent_recipients().items():
                if not needle or needle in email.casefold() or needle in (name or "").casefold():
                    add(email, name, when, when)
            if needle:
                for row in self.rows(
                        "SELECT DISTINCT ON (lower(sender_email)) sender,sender_email,date FROM messages "
                        "WHERE hidden=0 AND sent=0 AND sender_email<>'' AND (sender_email ILIKE ? OR sender ILIKE ?) "
                        "ORDER BY lower(sender_email), date DESC LIMIT 24", (like_contains(query), like_contains(query))):
                    add((row["sender_email"] or "").lower(), row["sender"] or "", None, row["date"])
        ordered = sorted(ranked.values(), key=lambda row: (row["last_sent"] is not None, row["last_sent"] or 0,
                                                           row["last_seen"] or 0), reverse=True)
        if not query:
            ordered = [row for row in ordered if row["last_sent"] is not None]
        return [{"name": row["name"] or "", "email": row["email"]} for row in ordered[:limit]]

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
        accounts = self.rows("SELECT * FROM accounts WHERE removing=0 ORDER BY seq")
        return [self.public_account(account, private) for account in accounts]

    def account(self, account_id, private=False):
        rows = self.rows("SELECT * FROM accounts WHERE id=?", (account_id,))
        return self.public_account(rows[0], private) if rows else None

    def public_account(self, account, private=False):
        account.pop("seq", None)
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
        return self.public_message(rows[0], raw, self.blobs)

    @staticmethod
    def message_fields(metadata=False, raw=False):
        fields = "id,account_id,thread_id,provider_id,message_id,sender,sender_email,recipients,subject,preview,date,read,starred,archived,sent,category,snoozed_until,analysis,pinned,trashed,hidden,content_version"
        return fields if metadata and not raw else fields + ",folder,uidvalidity,uid,body,labels"

    @staticmethod
    def public_message(row, raw=False, blobs=None):
        if raw and blobs:
            row["raw"] = blobs.get(row["id"]) or b""
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
            clauses.append("(sender ILIKE ? OR sender_email ILIKE ? OR subject ILIKE ? OR body ILIKE ?)")
            params.extend([f"%{search}%"] * 4)
        where = " AND ".join(clauses)
        return [self.public_message(row) for row in self.rows(
            f"SELECT {self.message_fields()} FROM messages WHERE {where} ORDER BY date DESC LIMIT ?", (*params, limit))]

    def upsert_message(self, data):
        existing = self.rows("SELECT id FROM messages WHERE account_id=? AND folder=? AND uidvalidity=? AND uid=?",
                             (data["account_id"], data["folder"], data["uidvalidity"], data["uid"]))
        if existing:
            return existing[0]["id"]
        data = dict(data)
        raw = data.pop("raw")
        data["content_version"] = hashlib.sha256(raw).hexdigest()
        data["id"] = uuid.uuid4().hex
        # Write the original before the row: a crash leaves at most an orphan file, never a row without mail.
        self.blobs.put(data["id"], raw)
        with self.lock:
            existing = self.rows("SELECT id FROM messages WHERE account_id=? AND folder=? AND uidvalidity=? AND uid=?",
                                 (data["account_id"], data["folder"], data["uidvalidity"], data["uid"]))
            if existing:
                return existing[0]["id"]
            if data.get("thread_id"):
                pinned = self.rows("SELECT MAX(pinned) AS pinned FROM messages WHERE account_id=? AND thread_id=?",
                                   (data["account_id"], data["thread_id"]))
                data["pinned"] = pinned[0]["pinned"] or 0
            for rule in self.rules():
                field = {"sender": data.get("sender_email", ""), "subject": data.get("subject", ""),
                         "body": data.get("body", "")}[rule["field"]]
                if rule["contains"].casefold() in (field or "").casefold():
                    data["category"] = rule["category"]
                    break
            columns = list(data)
            self.execute(f"INSERT INTO messages({','.join(columns)}) VALUES({','.join('?' for _ in columns)})",
                         tuple(data.values()))
            self.note_message_correspondents(data)
            self.on_mail_change()
            self.on_new_message(data)
            return data["id"]

    def patch_message(self, message_id, patch):
        with self.transaction():
            if not self.message(message_id, metadata=True):
                return False
            for key, value in patch.items():
                self.execute(f"UPDATE messages SET {key}=? WHERE id=?", (value, message_id))
                if key in {"read", "starred", "archived"}:
                    self.execute("DELETE FROM outbox WHERE message_id=? AND kind=?", (message_id, key))
                    self.execute("INSERT INTO outbox VALUES(?,?,?,?,?,NULL)",
                                 (uuid.uuid4().hex, message_id, key, json.dumps(value), time.time()))
            return True

    def conversation(self, message_id, raw=False, metadata=False, limit=None, body_limit=None):
        message = self.message(message_id, metadata=True)
        if not message:
            return []
        if not message.get("thread_id"):
            return [self.message(message_id, raw=raw, metadata=metadata)]
        fields = self.message_fields(metadata, raw)
        params = []
        if body_limit is not None and not metadata and not raw:
            fields = fields.replace(",body,", ",substr(body,1,?) AS body,")
            params.append(body_limit)
        params.extend((message["account_id"], message["thread_id"]))
        order = "date DESC,id DESC LIMIT ?" if limit else "date,id"
        if limit:
            params.append(limit)
        result = [self.public_message(row, raw, self.blobs) for row in self.rows(
            f"SELECT {fields} FROM messages WHERE account_id=? AND thread_id=? AND hidden=0 AND trashed=0 ORDER BY {order}",
            params)]
        return list(reversed(result)) if limit else result

    def message_headers(self, message_id):
        size = 65536
        while True:
            headers = self.blobs.head(message_id, size)
            for separator in (b"\r\n\r\n", b"\n\n"):
                if separator in headers:
                    return headers.split(separator, 1)[0] + separator
            if len(headers) < size:
                return headers
            if size >= 1048576:
                raise ValueError("Intestazioni del messaggio troppo grandi")
            size *= 2

    def patch_conversation(self, message_id, patch):
        with self.transaction():
            messages = self.conversation(message_id, metadata=True)
            for message in messages:
                self.patch_message(message["id"], patch)
            return bool(messages)

    def trash_conversation(self, message_id):
        with self.transaction():
            messages = self.conversation(message_id, metadata=True)
            for message in messages:
                self.execute("UPDATE messages SET trashed=1 WHERE id=?", (message["id"],))
                self.execute("DELETE FROM outbox WHERE message_id=?", (message["id"],))
                self.execute("INSERT INTO outbox VALUES(?,?,?,?,?,NULL)",
                             (uuid.uuid4().hex, message["id"], "trash", "true", time.time()))
            return bool(messages)

    def conversations(self, view="inbox", category=None, account=None, search="", limit=100,
                      before=None, chronological=False, thread=None, exclude_category=None):
        # Fetch only list metadata. Bodies and MIME blobs belong to the reader.
        clauses, params = ["hidden=0", "trashed=0"], []
        views = {"inbox": "archived=0 AND sent=0 AND (snoozed_until IS NULL OR snoozed_until<=?)",
                 "unread": "archived=0 AND sent=0 AND read=0 AND (snoozed_until IS NULL OR snoozed_until<=?)",
                 "starred": "starred=1", "archive": "archived=1 AND sent=0", "sent": "sent=1",
                 "snoozed": "snoozed_until>?"}
        if view in views:
            clauses.append(views[view])
            if view in {"inbox", "unread", "snoozed"}:
                params.append(time.time())
        if category:
            clauses.append("category=?")
            params.append(category)
        if exclude_category:
            clauses.append("category<>?")
            params.append(exclude_category)
        if account:
            clauses.append("account_id=?")
            params.append(account)
        if thread:
            clauses.append("COALESCE(thread_id,id)=?")
            params.append(thread)
        if search:
            clauses.append("(sender ILIKE ? OR sender_email ILIKE ? OR subject ILIKE ? OR body ILIKE ?)")
            params.extend([f"%{search}%"] * 4)
        cursor = " AND (date<? OR (date=? AND id<?))" if before else ""
        ordering = "date DESC,id DESC" if chronological else "pinned DESC,date DESC"
        if before:
            params.extend((before[0], before[0], before[1]))
        eligible = """WITH eligible AS (
            SELECT account_id,COALESCE(thread_id,id) AS thread FROM messages WHERE """ + " AND ".join(clauses) + """
            GROUP BY account_id,COALESCE(thread_id,id)
        ), ranked AS ("""
        if chronological and view == "all" and not any((category, account, search, thread)):
            # Walk messages newest first and keep those with no newer sibling: a page
            # stops after `limit` threads instead of ranking the whole archive.
            eligible = """WITH eligible AS (
                SELECT m.account_id,COALESCE(m.thread_id,m.id) AS thread FROM messages m
                WHERE m.hidden=0 AND m.trashed=0""" + cursor.replace("date", "m.date").replace("id<", "m.id<") + """
                AND NOT EXISTS (SELECT 1 FROM messages n WHERE n.account_id=m.account_id
                    AND COALESCE(n.thread_id,n.id)=COALESCE(m.thread_id,m.id) AND n.hidden=0 AND n.trashed=0
                    AND (n.date>m.date OR (n.date=m.date AND n.id<m.id)))
                ORDER BY m.date DESC,m.id DESC LIMIT ?
            ), ranked AS ("""
            params.append(limit)
            cursor = ""
        now = "EXTRACT(EPOCH FROM now())"
        rows = self.rows(eligible.replace("WITH eligible AS (", "WITH eligible AS MATERIALIZED (") + f"""
                SELECT m.id,m.account_id,m.thread_id,m.sender,m.sender_email,m.subject,m.preview,m.date,
                       m.read,m.content_version,MAX(m.starred) OVER w AS starred,m.archived,m.sent,m.category,
                       MAX(m.snoozed_until) OVER w AS snoozed_until,
                       MAX((m.sent=0 AND m.archived=0 AND (m.snoozed_until IS NULL OR m.snoozed_until<={now}))::int) OVER w AS has_inbox,
                       MAX((m.sent=0 AND m.archived=1)::int) OVER w AS has_archive,
                       MAX((m.sent=1)::int) OVER w AS has_sent,
                       SUM((m.sent=0)::int) OVER w AS received_count,
                       SUM((m.sent=0 AND m.archived=0 AND (m.snoozed_until IS NULL OR m.snoozed_until<={now}))::int) OVER w AS inbox_count,
                       SUM((m.sent=0 AND m.read=0 AND m.archived=0 AND (m.snoozed_until IS NULL OR m.snoozed_until<={now}))::int) OVER w AS inbox_unread_count,
                       MAX(m.pinned) OVER w AS pinned,COUNT(*) OVER w AS message_count,
                       SUM((m.read=0 AND m.sent=0)::int) OVER w AS unread_count,
                       COUNT(m.analysis) OVER w AS analyzed_count,
                       ROW_NUMBER() OVER (PARTITION BY m.account_id,COALESCE(m.thread_id,m.id) ORDER BY m.date DESC,m.id) AS rank
                FROM messages m
                JOIN eligible e ON m.account_id=e.account_id AND COALESCE(m.thread_id,m.id)=e.thread
                WHERE m.hidden=0 AND m.trashed=0
                WINDOW w AS (PARTITION BY m.account_id,COALESCE(m.thread_id,m.id))
            ) SELECT ranked.* FROM ranked WHERE ranked.rank=1""" + cursor + " ORDER BY " + ordering + " LIMIT ?", (*params, limit))
        for row in rows:
            row.pop("rank")
            for key in ("received_count", "inbox_count", "inbox_unread_count", "unread_count", "message_count",
                        "analyzed_count"):
                row[key] = int(row[key] or 0)
            row["read"] = int(not row["unread_count"])
            row["replied"] = bool(row["sent"])
        return rows

    def reconcile_flags(self, message_id, read, starred):
        with self.lock:
            pending = {r["kind"] for r in self.rows("SELECT kind FROM outbox WHERE message_id=?", (message_id,))}
            for key, value in (("read", read), ("starred", starred)):
                if key not in pending:
                    self.execute(f"UPDATE messages SET {key}=? WHERE id=?", (int(value), message_id))

    def rules(self):
        return [{"id": row["id"], **json.loads(row["data"])} for row in self.rows("SELECT * FROM rules ORDER BY seq")]

    def add_rule(self, data):
        rule_id = uuid.uuid4().hex
        self.execute("INSERT INTO rules(id,data) VALUES(?,?)", (rule_id, json.dumps(data)))
        return rule_id

    def close(self):
        with self._pool_lock:
            readers, self._readers, self._idle = self._readers, [], []
        for connection in readers:
            connection.close()
        self.db.close()
