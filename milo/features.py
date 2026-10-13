import ipaddress
import json
import socket
import time
import uuid
from email import policy
from email.parser import BytesHeaderParser
from urllib.parse import parse_qs, unquote, urlsplit

import httpx

TODO_WINDOW = 30 * 86400
PRIORITY = {"high": 0, "normal": 1, "low": 2}


def public_https(url):
    """Unsubscribe links come from untrusted mail: only public HTTPS hosts on the default port."""
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname or parts.port not in (None, 443) or parts.username:
        return False
    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(parts.hostname, 443, proto=socket.IPPROTO_TCP)}
    except OSError:
        return False
    return bool(addresses) and all(ipaddress.ip_address(address.split("%")[0]).is_global for address in addresses)


class Features:
    def __init__(self, store):
        self.store = store
        self._screening = (0, [])
        self._contacts = (0, set())
        with store.lock:
            store.db.executescript("""
                CREATE TABLE IF NOT EXISTS scheduled(
                    draft_id TEXT PRIMARY KEY, send_at REAL NOT NULL, followup_days INTEGER,
                    error TEXT, created REAL);
                CREATE TABLE IF NOT EXISTS senders(
                    email TEXT PRIMARY KEY, status TEXT, vip INTEGER NOT NULL DEFAULT 0,
                    unsubscribed REAL, updated REAL);
                CREATE TABLE IF NOT EXISTS todos(
                    id TEXT PRIMARY KEY, message_id TEXT NOT NULL, text TEXT NOT NULL, priority TEXT,
                    kind TEXT NOT NULL DEFAULT 'action', created REAL, done REAL);
                CREATE INDEX IF NOT EXISTS todos_open ON todos(done, message_id);
                CREATE INDEX IF NOT EXISTS todos_message ON todos(message_id);
                CREATE TABLE IF NOT EXISTS followups(
                    id TEXT PRIMARY KEY, account_id TEXT NOT NULL, rfc_message_id TEXT, thread_id TEXT,
                    subject TEXT, recipients TEXT, created REAL, due REAL, resolved REAL);
                CREATE INDEX IF NOT EXISTS followups_open ON followups(resolved, due);
            """)

    # Scheduled sending and undo

    def schedule(self, draft_id, send_at, followup_days=None):
        if not self.store.rows("SELECT id FROM drafts WHERE id=?", (draft_id,)):
            raise LookupError("Bozza non trovata")
        if not time.time() - 60 <= send_at <= time.time() + 366 * 86400:
            raise ValueError("Scegli una data entro un anno")
        self.store.execute("INSERT OR REPLACE INTO scheduled VALUES(?,?,?,NULL,?)",
                           (draft_id, send_at, followup_days, time.time()))
        return {"draft_id": draft_id, "send_at": send_at, "followup_days": followup_days}

    def unschedule(self, draft_id):
        return bool(self.store.execute("DELETE FROM scheduled WHERE draft_id=? AND error IS NULL", (draft_id,)).rowcount)

    def schedules(self):
        return {row["draft_id"]: row for row in self.store.rows("SELECT * FROM scheduled")}

    def due(self):
        return [row["draft_id"] for row in self.store.rows(
            "SELECT draft_id FROM scheduled WHERE send_at<=? AND error IS NULL ORDER BY send_at", (time.time(),))]

    def schedule_failed(self, draft_id, error):
        self.store.execute("UPDATE scheduled SET error=? WHERE draft_id=?", (error[:300], draft_id))

    def sent(self, draft_id, account_id, draft, rfc_message_id, thread_id):
        followup = self.store.rows("SELECT followup_days FROM scheduled WHERE draft_id=?", (draft_id,))
        days = (followup[0]["followup_days"] if followup else None) or draft.get("followup_days")
        self.store.execute("DELETE FROM scheduled WHERE draft_id=?", (draft_id,))
        if days and rfc_message_id:
            self.store.execute("INSERT INTO followups VALUES(?,?,?,?,?,?,?,?,NULL)",
                               (uuid.uuid4().hex, account_id, rfc_message_id, thread_id, draft.get("subject", ""),
                                ", ".join(v for v in (draft.get("to"), draft.get("cc")) if v), time.time(),
                                time.time() + int(days) * 86400))

    # Follow-up reminders

    def check_followups(self):
        for row in self.store.rows("SELECT * FROM followups WHERE resolved IS NULL"):
            sent = self.store.rows("SELECT id,thread_id FROM messages WHERE account_id=? AND message_id=? "
                                   "ORDER BY sent DESC LIMIT 1", (row["account_id"], row["rfc_message_id"]))
            thread = row["thread_id"] or (sent[0]["thread_id"] if sent else None)
            if thread and thread != row["thread_id"]:
                self.store.execute("UPDATE followups SET thread_id=? WHERE id=?", (thread, row["id"]))
            answered = thread and self.store.rows(
                "SELECT 1 FROM messages WHERE account_id=? AND thread_id=? AND sent=0 AND trashed=0 AND date>? LIMIT 1",
                (row["account_id"], thread, row["created"]))
            if answered:
                self.store.execute("UPDATE followups SET resolved=? WHERE id=?", (time.time(), row["id"]))
            elif row["due"] <= time.time() and sent:
                with self.store.transaction():
                    self.store.execute("INSERT INTO todos VALUES(?,?,?,?,?,?,NULL)",
                                       (uuid.uuid4().hex, sent[0]["id"], "Nessuna risposta: " + (row["subject"] or "senza oggetto"),
                                        "high", "followup", time.time()))
                    self.store.execute("UPDATE followups SET resolved=? WHERE id=?", (time.time(), row["id"]))

    # To-do list from AI action items

    def sync_todos(self, message_id, analysis):
        items = [item.strip() for item in (analysis or {}).get("action_items", []) if isinstance(item, str) and item.strip()]
        priority = (analysis or {}).get("priority", "normal")
        with self.store.transaction():
            done = {row["text"] for row in self.store.rows(
                "SELECT text FROM todos WHERE message_id=? AND kind='action' AND done IS NOT NULL", (message_id,))}
            self.store.execute("DELETE FROM todos WHERE message_id=? AND kind='action' AND done IS NULL", (message_id,))
            for item in items:
                if item not in done:
                    self.store.execute("INSERT INTO todos VALUES(?,?,?,?,'action',?,NULL)",
                                       (uuid.uuid4().hex, message_id, item[:500], priority, time.time()))

    def backfill_todos(self, stop=lambda: False):
        if self.store.setting("todos_backfilled"):
            return
        rows = self.store.rows(
            "SELECT id,analysis FROM messages INDEXED BY messages_analyzed WHERE analysis IS NOT NULL AND hidden=0 "
            "AND trashed=0 AND sent=0 AND date>? AND id NOT IN (SELECT message_id FROM todos)", (time.time() - TODO_WINDOW,))
        for row in rows:
            if stop():
                return
            try:
                self.sync_todos(row["id"], json.loads(row["analysis"]))
            except ValueError:
                continue
        self.store.set_setting("todos_backfilled", True)

    def todos(self):
        rows = self.store.rows(
            "SELECT t.id,t.message_id,t.text,t.priority,t.kind,t.created,m.sender,m.sender_email,m.subject,m.date,"
            "m.account_id,m.thread_id FROM todos t JOIN messages m ON m.id=t.message_id "
            "WHERE t.done IS NULL AND m.trashed=0 AND m.hidden=0 ORDER BY t.rowid DESC LIMIT 300")
        # Newest first overall; items of one message keep the order the analysis gave them.
        return sorted(reversed(rows), key=lambda row: (PRIORITY.get(row["priority"], 1), -(row["date"] or 0)))

    def todo_count(self):
        return self.store.rows("SELECT COUNT(*) AS count FROM todos t JOIN messages m ON m.id=t.message_id "
                               "WHERE t.done IS NULL AND m.trashed=0 AND m.hidden=0")[0]["count"]

    def set_todo(self, todo_id, done):
        return bool(self.store.execute("UPDATE todos SET done=? WHERE id=?",
                                       (time.time() if done else None, todo_id)).rowcount)

    # Senders: VIP, screener, block, newsletters

    def set_sender(self, email, status=..., vip=...):
        email = email.strip().lower()
        if "@" not in email or len(email) > 254:
            raise ValueError("Indirizzo non valido")
        with self.store.transaction():
            self.store.execute("INSERT OR IGNORE INTO senders(email,updated) VALUES(?,?)", (email, time.time()))
            if status is not ...:
                self.store.execute("UPDATE senders SET status=?,updated=? WHERE email=?", (status, time.time(), email))
            if vip is not ...:
                self.store.execute("UPDATE senders SET vip=?,updated=? WHERE email=?", (int(bool(vip)), time.time(), email))
        self._screening = (0, [])
        if status == "blocked":
            self.sender_action(email, "archive")
        return self.store.rows("SELECT * FROM senders WHERE email=?", (email,))[0]

    def vips(self):
        return [row["email"] for row in self.store.rows("SELECT email FROM senders WHERE vip=1")]

    def sender_threads(self, email):
        seen, ids = set(), []
        for row in self.store.rows(
                "SELECT id,account_id,COALESCE(thread_id,id) AS thread FROM messages INDEXED BY messages_client_catalogue "
                "WHERE hidden=0 AND trashed=0 AND sent=0 AND archived=0 AND lower(sender_email)=?", (email.lower(),)):
            if (row["account_id"], row["thread"]) not in seen:
                seen.add((row["account_id"], row["thread"]))
                ids.append(row["id"])
        return ids

    def sender_action(self, email, action):
        ids = self.sender_threads(email)
        for message_id in ids:
            if action == "trash":
                self.store.trash_conversation(message_id)
            else:
                self.store.patch_conversation(message_id, {"archived": True} if action == "archive" else {"read": True})
        return len(ids)

    def enforce_blocked(self):
        return sum(self.sender_action(row["email"], "archive")
                   for row in self.store.rows("SELECT email FROM senders WHERE status='blocked'"))

    def newsletter_senders(self):
        rows = self.store.rows(
            "SELECT lower(sender_email) AS email,MAX(sender) AS name,COUNT(DISTINCT account_id||':'||COALESCE(thread_id,id)) AS threads,"
            "SUM(read=0) AS unread,SUM(archived=0) AS inbox,MAX(date) AS last,MAX(id) AS sample_id "
            "FROM messages INDEXED BY messages_client_catalogue WHERE hidden=0 AND trashed=0 AND sent=0 "
            "AND category='newsletters' GROUP BY lower(sender_email) ORDER BY threads DESC LIMIT 300")
        known = {row["email"]: row for row in self.store.rows("SELECT * FROM senders")}
        for row in rows:
            row["unsubscribed"] = (known.get(row["email"]) or {}).get("unsubscribed")
            row["status"] = (known.get(row["email"]) or {}).get("status")
        return rows

    def screener(self):
        return self.store.setting("screener") or {"enabled": False, "since": None}

    def set_screener(self, enabled):
        current = self.screener()
        value = {"enabled": bool(enabled), "since": current.get("since") if current.get("enabled") else time.time()}
        if not enabled:
            value["since"] = None
        self.store.set_setting("screener", value)
        self._screening = (0, [])
        return value

    def contacts(self):
        if time.time() - self._contacts[0] < 300:
            return self._contacts[1]
        addresses = set()
        for row in self.store.rows("SELECT recipients FROM messages WHERE sent=1 AND recipients IS NOT NULL"):
            for part in (row["recipients"] or "").replace(";", ",").split(","):
                part = part.strip().lower()
                if "<" in part:
                    part = part.split("<", 1)[1].split(">", 1)[0]
                if "@" in part:
                    addresses.add(part.strip())
        addresses.update(account["email"].lower() for account in self.store.accounts())
        self._contacts = (time.time(), addresses)
        return addresses

    def screening(self):
        """Unknown senders whose first mail arrived after the screener was enabled."""
        settings = self.screener()
        if not settings.get("enabled") or not settings.get("since"):
            return []
        if time.time() - self._screening[0] < 30:
            return self._screening[1]
        decided = {row["email"] for row in self.store.rows("SELECT email FROM senders WHERE status IS NOT NULL")}
        contacts = self.contacts()
        rows = self.store.rows(
            "SELECT lower(sender_email) AS email,MAX(sender) AS name,MIN(date) AS first,COUNT(*) AS count,MAX(id) AS sample_id "
            "FROM messages INDEXED BY messages_client_catalogue WHERE hidden=0 AND trashed=0 AND sent=0 AND archived=0 "
            "GROUP BY lower(sender_email) HAVING MIN(date)>=?", (settings["since"],))
        result = [row for row in rows if row["email"] not in decided and row["email"] not in contacts][:200]
        self._screening = (time.time(), result)
        return result

    # Unsubscribe

    def unsubscribe_options(self, headers):
        mail = BytesHeaderParser(policy=policy.compat32).parsebytes(headers)
        value = " ".join(str(item) for item in mail.get_all("List-Unsubscribe", []))
        links = [part.strip().strip("<>").strip() for part in value.split(",") if part.strip()]
        one_click = "list-unsubscribe=one-click" in " ".join(
            str(item) for item in mail.get_all("List-Unsubscribe-Post", [])).lower().replace(" ", "")
        https = next((link for link in links if link.lower().startswith("https://")), None)
        mailto = next((link for link in links if link.lower().startswith("mailto:")), None)
        if not (https or mailto):
            return None
        return {"one_click": bool(https and one_click), "url": https, "mailto": mailto}

    def mailto_draft(self, mailto, account_id):
        parts = urlsplit(mailto)
        query = parse_qs(parts.query)
        address = unquote(parts.path)
        if "@" not in address or any(c in address for c in "\r\n,;"):
            raise ValueError("Indirizzo di disiscrizione non valido")
        return {"account_id": account_id, "to": address, "cc": "",
                "subject": (query.get("subject") or ["unsubscribe"])[0][:200],
                "body": (query.get("body") or ["unsubscribe"])[0][:2000], "mode": "new"}

    def one_click(self, url):
        if not public_https(url):
            raise ValueError("Il link di disiscrizione non è sicuro")
        response = httpx.post(url, data={"List-Unsubscribe": "One-Click"}, timeout=15, follow_redirects=False,
                              headers={"User-Agent": "Milo"})
        if response.status_code >= 400:
            raise RuntimeError("Il mittente ha rifiutato la richiesta di disiscrizione")

    def mark_unsubscribed(self, email):
        email = email.strip().lower()
        self.store.execute("INSERT OR IGNORE INTO senders(email,updated) VALUES(?,?)", (email, time.time()))
        self.store.execute("UPDATE senders SET unsubscribed=?,updated=? WHERE email=?", (time.time(), time.time(), email))

    # Configuration export and restore. Mail itself comes back from the providers.

    def export(self):
        accounts = {account["id"]: account for account in self.store.accounts()}
        def email_of(account_id):
            return (accounts.get(account_id) or {}).get("email")

        settings = {key: self.store.setting(key) for key in
                    ("identity", "ai", "appearance", "signatures", "templates", "screener")}
        messages = [{"account": email_of(row["account_id"]), "message_id": row["message_id"], "category": row["category"],
                     "analysis": json.loads(row["analysis"]) if row["analysis"] else None,
                     "pinned": row["pinned"], "snoozed_until": row["snoozed_until"]}
                    for row in self.store.rows(
                        "SELECT account_id,message_id,category,analysis,pinned,snoozed_until FROM messages "
                        "WHERE message_id IS NOT NULL AND message_id!='' AND (analysis IS NOT NULL OR pinned=1 "
                        "OR snoozed_until IS NOT NULL)")]
        todos = [{"account": email_of(row["account_id"]), "message_id": row["rfc"], "text": row["text"],
                  "priority": row["priority"], "kind": row["kind"], "created": row["created"], "done": row["done"]}
                 for row in self.store.rows(
                     "SELECT t.*,m.account_id,m.message_id AS rfc FROM todos t JOIN messages m ON m.id=t.message_id")]
        drafts = []
        for row in self.store.rows("SELECT * FROM drafts"):
            data = json.loads(row["data"])
            drafts.append({**data, "id": row["id"], "account": email_of(data.get("account_id"))})
        return {"format": "milo-configuration", "version": 1, "exported_at": time.time(),
                "accounts": [{key: account.get(key) for key in ("name", "email", "provider", "color", "imap_host",
                                                                "imap_port", "smtp_host", "smtp_port", "smtp_security")}
                             for account in accounts.values()],
                "settings": {key: value for key, value in settings.items() if value is not None},
                "rules": self.store.rules(), "senders": self.store.rows("SELECT * FROM senders"),
                "drafts": drafts, "messages": messages, "todos": todos}

    def restore(self, data):
        if data.get("format") != "milo-configuration" or data.get("version") != 1:
            raise ValueError("Questo file non è una configurazione di Milo")
        accounts = {account["email"].lower(): account["id"] for account in self.store.accounts()}
        counts = {"settings": 0, "rules": 0, "senders": 0, "drafts": 0, "messages": 0, "todos": 0}
        for key, value in (data.get("settings") or {}).items():
            if key in {"identity", "ai", "appearance", "signatures", "templates", "screener"} and isinstance(value, dict | list):
                self.store.set_setting(key, value)
                counts["settings"] += 1
        existing_rules = {(rule["field"], rule["contains"].casefold()) for rule in self.store.rules()}
        for rule in data.get("rules") or []:
            if (rule.get("field"), str(rule.get("contains", "")).casefold()) not in existing_rules:
                self.store.add_rule({key: rule[key] for key in ("name", "field", "contains", "category")})
                counts["rules"] += 1
        for sender in data.get("senders") or []:
            self.store.execute("INSERT OR REPLACE INTO senders VALUES(?,?,?,?,?)",
                               (str(sender["email"]).lower(), sender.get("status"), int(bool(sender.get("vip"))),
                                sender.get("unsubscribed"), sender.get("updated") or time.time()))
            counts["senders"] += 1
        for draft in data.get("drafts") or []:
            account_id = accounts.get(str(draft.get("account") or "").lower())
            if not account_id or self.store.rows("SELECT 1 FROM drafts WHERE id=?", (draft["id"],)):
                continue
            body = {key: draft.get(key) for key in ("to", "cc", "subject", "body", "reply_to_id", "context_message_id",
                                                     "mode", "revision")}
            self.store.execute("INSERT INTO drafts VALUES(?,?,?)",
                               (draft["id"], json.dumps({**body, "id": draft["id"], "account_id": account_id}), time.time()))
            counts["drafts"] += 1
        def local(entry):
            account_id = accounts.get(str(entry.get("account") or "").lower())
            if not account_id or not entry.get("message_id"):
                return None
            rows = self.store.rows("SELECT id FROM messages WHERE account_id=? AND message_id=? LIMIT 1",
                                   (account_id, entry["message_id"]))
            return rows[0]["id"] if rows else None
        for entry in data.get("messages") or []:
            message_id = local(entry)
            if message_id:
                self.store.execute("UPDATE messages SET category=?,analysis=COALESCE(?,analysis),pinned=?,snoozed_until=? WHERE id=?",
                                   (entry.get("category") or "people",
                                    json.dumps(entry["analysis"]) if entry.get("analysis") else None,
                                    int(bool(entry.get("pinned"))), entry.get("snoozed_until"), message_id))
                counts["messages"] += 1
        for entry in data.get("todos") or []:
            message_id = local(entry)
            if message_id and not self.store.rows("SELECT 1 FROM todos WHERE message_id=? AND text=?", (message_id, entry["text"])):
                self.store.execute("INSERT INTO todos VALUES(?,?,?,?,?,?,?)",
                                   (uuid.uuid4().hex, message_id, entry["text"], entry.get("priority"),
                                    entry.get("kind") or "action", entry.get("created") or time.time(), entry.get("done")))
                counts["todos"] += 1
        self._screening = (0, [])
        return counts

    # Account removal runs in paced background batches: a large mailbox frees gigabytes.

    def purge_account(self, account_id, stop=lambda: False):
        while not stop():
            started = time.monotonic()
            with self.store.transaction():
                deleted = self.store.execute(
                    "DELETE FROM messages WHERE rowid IN (SELECT rowid FROM messages WHERE account_id=? LIMIT 200)",
                    (account_id,)).rowcount
            if not deleted:
                break
            time.sleep(max(0.05, 2 * (time.monotonic() - started)))
        if stop():
            return False
        with self.store.transaction():
            drafts = [row["id"] for row in self.store.rows("SELECT id,data FROM drafts")
                      if json.loads(row["data"]).get("account_id") == account_id]
            for draft_id in drafts:
                self.store.execute("DELETE FROM drafts WHERE id=?", (draft_id,))
                self.store.execute("DELETE FROM scheduled WHERE draft_id=?", (draft_id,))
            for table in ("gmail_sync", "gmail_scan", "followups"):
                self.store.execute(f"DELETE FROM {table} WHERE account_id=?", (account_id,))
            self.store.execute("DELETE FROM todos WHERE message_id NOT IN (SELECT id FROM messages)")
            self.store.execute("DELETE FROM accounts WHERE id=?", (account_id,))
        return True
