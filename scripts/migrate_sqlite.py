#!/usr/bin/env python3
"""Move a SQLite archive into PostgreSQL, with original MIME as compressed files.

Run with Milo stopped. The SQLite file is only read; it stays in place as a fallback.
Usage: migrate_sqlite.py ARCHIVE_DIR POSTGRES_URL
"""
import hashlib
import sqlite3
import sys
import time
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from milo.store import SCHEMA, Blobs, preview_text  # noqa: E402

TABLES = {
    "settings": ["key", "value"],
    "sessions": ["token", "expires"],
    "drafts": ["id", "data", "updated"],
    "oauth_states": ["state", "data", "expires"],
    "gmail_sync": ["account_id", "history_id", "history_page", "backfill_page", "backfill_complete"],
    "gmail_scan": ["account_id", "provider_id"],
    "outbox": ["id", "message_id", "kind", "value", "created", "error"],
    "scheduled": ["draft_id", "send_at", "followup_days", "error", "created"],
    "senders": ["email", "status", "vip", "unsubscribed", "updated"],
    "followups": ["id", "account_id", "rfc_message_id", "thread_id", "subject", "recipients", "created", "due", "resolved"],
}
ACCOUNT = ["id", "name", "email", "username", "secret", "imap_host", "imap_port", "smtp_host", "smtp_port",
           "smtp_security", "color", "last_sync", "error", "provider", "enabled", "removing"]
MESSAGE = ["id", "account_id", "folder", "uidvalidity", "uid", "message_id", "sender", "sender_email", "recipients",
           "subject", "body", "preview", "date", "read", "starred", "archived", "sent", "category", "snoozed_until",
           "analysis", "provider_id", "thread_id", "labels", "hidden", "pinned", "trashed", "content_version"]


def text(value):
    return value.replace("\x00", "") if isinstance(value, str) else value


def columns(source, table):
    return {row[1] for row in source.execute(f"PRAGMA table_xinfo({table})")}


def copy(source, target, table, names, order="rowid"):
    present = columns(source, table)
    if not present:
        return 0
    names = [name for name in names if name in present]
    rows = [tuple(text(value) for value in row) for row in
            source.execute(f"SELECT {','.join(names)} FROM {table} ORDER BY {order}")]
    if rows:
        with target.cursor() as cursor:
            cursor.executemany(f"INSERT INTO {table}({','.join(names)}) VALUES({','.join(['%s'] * len(names))}) "
                               "ON CONFLICT DO NOTHING", rows)
    return len(rows)


def main():
    archive, url = Path(sys.argv[1]), sys.argv[2]
    source = sqlite3.connect(f"file:{archive / 'mail.sqlite'}?mode=ro", uri=True)
    blobs = Blobs(archive / "blobs")
    target = psycopg.connect(url, autocommit=True)
    target.execute(SCHEMA)
    if target.execute("SELECT COUNT(*) FROM messages").fetchone()[0]:
        raise SystemExit("PostgreSQL already contains messages: refusing to migrate twice.")
    started = time.time()
    counts = {"accounts": copy(source, target, "accounts", ACCOUNT)}
    raw_table = bool(columns(source, "message_raw"))
    raw = "COALESCE((SELECT r.raw FROM message_raw r WHERE r.id=m.id),m.raw)" if raw_table else "m.raw"
    present = columns(source, "messages")
    fields = [name for name in MESSAGE if name in present]
    stored = list(dict.fromkeys([*fields, "content_version", "preview"]))
    selected = ",".join(f"m.{name}" for name in fields)
    last, moved, missing = 0, 0, 0
    while True:
        rows = source.execute(f"SELECT m.rowid,{selected},{raw} FROM messages m WHERE m.rowid>? ORDER BY m.rowid LIMIT 500",
                              (last,)).fetchall()
        if not rows:
            break
        batch = []
        for row in rows:
            values, original = list(row[1:-1]), row[-1]
            record = dict(zip(fields, values))
            record.setdefault("content_version", None)
            if original:
                blobs.put(record["id"], original)
                record["content_version"] = record["content_version"] or hashlib.sha256(original).hexdigest()
            else:
                missing += 1
            if record.get("preview") is None:
                record["preview"] = preview_text(record.get("body"))
            batch.append(tuple(text(record[name]) for name in stored))
        with target.cursor() as cursor:
            cursor.executemany(f"INSERT INTO messages({','.join(stored)}) VALUES({','.join(['%s'] * len(stored))})", batch)
        last, moved = rows[-1][0], moved + len(rows)
        if moved % 5000 < 500:
            print(f"messages {moved} {time.time() - started:.0f}s", flush=True)
    counts["messages"] = moved
    counts["rules"] = copy(source, target, "rules", ["id", "data"])
    counts["todos"] = copy(source, target, "todos", ["id", "message_id", "text", "priority", "kind", "created", "done"])
    for table, names in TABLES.items():
        counts[table] = copy(source, target, table, names)
    for table, count in counts.items():
        stored = target.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        if stored != count:
            raise SystemExit(f"{table}: copied {count} but PostgreSQL holds {stored}")
    sample = source.execute(f"SELECT m.id,{raw} FROM messages m ORDER BY random() LIMIT 50").fetchall()
    identical = all(blobs.get(message_id) == original for message_id, original in sample if original)
    target.execute("ANALYZE")
    print({**counts, "without_original": missing, "sample_identical": identical,
           "seconds": round(time.time() - started)}, flush=True)
    if not identical:
        raise SystemExit("Stored originals differ from SQLite")


if __name__ == "__main__":
    main()
