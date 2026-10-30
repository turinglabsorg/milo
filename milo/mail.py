import email
import hashlib
import imaplib
import json
import os
import re
import smtplib
import ssl
import threading
import time
from datetime import datetime
from email import policy
from email.message import EmailMessage
from email.utils import getaddresses, make_msgid, parsedate_to_datetime
from html import escape
from html.parser import HTMLParser
from zoneinfo import ZoneInfo

from .store import preview_text


class PlainHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts, self.hidden = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "head"}:
            self.hidden += 1
        if tag in {"p", "br", "div", "li", "tr"} and not self.hidden:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style", "head"}:
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def parse_message(raw, account_id, folder, uidvalidity, uid, flags=b"", sent=False, archived=False):
    mail = email.message_from_bytes(raw, policy=policy.default)
    sender = getaddresses([str(mail.get("From", ""))])
    name, address = sender[0] if sender else ("", "")
    part = mail.get_body(preferencelist=("plain", "html"))
    body = ""
    if part:
        try:
            body = part.get_content()
        except (LookupError, UnicodeError):
            body = (part.get_payload(decode=True) or b"").decode("utf-8", errors="replace")
        if part.get_content_type() == "text/html":
            parser = PlainHTML()
            parser.feed(body)
            body = "".join(parser.parts)
    try:
        date = parsedate_to_datetime(str(mail.get("Date"))).timestamp()
    except (TypeError, ValueError, OverflowError):
        date = time.time()
    category = "newsletters" if mail.get("List-Unsubscribe") or mail.get("List-Id") else "people"
    automatic = str(mail.get("Auto-Submitted", "no")).strip().lower().split(";", 1)[0]
    local_part = address.partition("@")[0].lower()
    service_alert = re.fullmatch(r"(?:notifications?|alerts?|mailer-daemon|postmaster)(?:[+._-].*)?", local_part)
    no_reply = re.fullmatch(r"(?:no[-_.]?reply|do[-_.]?not[-_.]?reply)(?:[+._-].*)?", local_part)
    if service_alert or (category == "people" and (automatic not in {"", "no"} or no_reply)):
        category = "updates"
    references = re.findall(r"<[^>]+>", str(mail.get("References", "")) or str(mail.get("In-Reply-To", "")))
    root = references[0] if references else str(mail.get("Message-ID", ""))
    return {"account_id": account_id, "folder": folder, "uidvalidity": str(uidvalidity), "uid": int(uid),
            "message_id": str(mail.get("Message-ID", "")), "sender": name or address,
            "sender_email": address, "recipients": str(mail.get("To", "")),
            "subject": str(mail.get("Subject", "(Senza oggetto)")), "body": body[:200000],
            "preview": preview_text(body), "date": date,
            "read": int(b"\\Seen" in flags), "starred": int(b"\\Flagged" in flags),
            "sent": int(sent), "archived": int(archived), "category": category, "raw": raw,
            "thread_id": "rfc822:" + hashlib.sha256(root.encode()).hexdigest() if root else None}


def check(status, message="Operazione IMAP rifiutata"):
    if status != "OK":
        raise RuntimeError(message)


def connect(account):
    client = imaplib.IMAP4_SSL(account["imap_host"], account["imap_port"],
                              ssl_context=ssl.create_default_context(), timeout=20)
    try:
        check(client.login(account["username"], account["password"])[0], "Accesso IMAP rifiutato")
        status, data = client.capability()
        if status == "OK" and data and data[-1]:
            client.capabilities = tuple(data[-1].decode().upper().split())
    except Exception:
        client.shutdown()
        raise
    return client


def folders(client):
    result = [{"name": "INBOX", "sent": False, "archived": False, "trash": False}]
    status, listing = client.list()
    check(status)
    for line in listing or []:
        if not isinstance(line, bytes):
            continue
        match = re.match(rb'\((.*?)\)\s+(?:"(?:\\.|[^"\\])*"|NIL)\s+(.+)$', line)
        if not match:
            continue
        flags, name = match.groups()
        if name.startswith(b'"') and name.endswith(b'"'):
            name = re.sub(rb'\\(.)', rb'\1', name[1:-1])
        name = name.decode("ascii", errors="replace")
        sent = b"\\sent" in flags.lower() or name.lower() in {"sent", "sent messages", "sent items"}
        archived = b"\\archive" in flags.lower() or name.lower() in {"archive", "archives"}
        trash = b"\\trash" in flags.lower() or name.lower() in {"trash", "deleted messages", "deleted items"}
        if (sent or archived or trash) and name.upper() != "INBOX":
            result.append({"name": name, "sent": sent, "archived": archived, "trash": trash})
    return result


def select_folder(client, name):
    check(client.select('"' + name.replace('\\', '\\\\').replace('"', '\\"') + '"')[0],
          "Impossibile aprire la cartella")
    validity = client.response("UIDVALIDITY")[1]
    if not validity or not validity[0]:
        raise RuntimeError("Il server non ha restituito UIDVALIDITY")
    return validity[0].decode()


class SyncEngine:
    def __init__(self, store, ai=None):
        self.store, self.ai = store, ai
        self._locks = {}
        self._guard = threading.Lock()
        self._progress = {}
        self._rate_limited_until = {}
        with self.store.transaction():
            if self.store.setting("ai_automatic_boundary") is None:
                self.reset_automatic_analysis()

    def reset_automatic_analysis(self):
        self.store.reset_automatic_analysis()

    def report(self, account_id, phase, downloaded=None):
        with self._guard:
            current = self._progress.get(account_id, {"downloaded": 0})
            self._progress[account_id] = {**current, "account_id": account_id, "phase": phase,
                                          "updated": time.time()}
            if downloaded is not None:
                self._progress[account_id]["downloaded"] = downloaded

    def status(self):
        with self._guard:
            return [dict(progress) for progress in self._progress.values()]

    def account_lock(self, account_id):
        with self._guard:
            return self._locks.setdefault(account_id, threading.Lock())

    def sync_all(self):
        return [self.sync_account(account) for account in self.store.accounts() if account["enabled"]]

    def sync_account(self, account):
        account_id = account["id"]
        with self.account_lock(account_id):
            # A queued worker may hold a snapshot from before a credential edit
            # or pause. Re-read only this account after acquiring its lock.
            current = self.store.account(account_id, private=True)
            if not current or not current["enabled"]:
                return {"account_id": account_id, "ok": True, "paused": True, "added": 0}
            if self._rate_limited_until.get(account_id, 0) > time.time():
                return {"account_id": account_id, "ok": True, "paused": True, "added": 0}
            self.report(account_id, "connecting")
            result = self._sync_google(current) if current["provider"] == "google" else self._sync_imap(current)
            self.report(account_id, "ready" if result["ok"] else "error")
        if result["ok"]:
            self.analyze_pending(account_id)
        return result

    def _sync_imap(self, account):
        account_id = account["id"]
        client = None
        try:
            client = connect(account)
            remote_folders = folders(client)
            self.flush_changes(client, account, remote_folders)
            added = []
            for folder in remote_folders:
                if folder.get("trash"):
                    continue
                added.extend(self.sync_folder(client, account, folder))
            self.store.execute("UPDATE accounts SET last_sync=?,error=NULL WHERE id=?", (time.time(), account_id))
            return {"account_id": account_id, "added": len(added), "ok": True}
        except Exception as exc:
            error = safe_error(exc)
            self.store.execute("UPDATE accounts SET error=? WHERE id=?", (error, account_id))
            return {"account_id": account_id, "ok": False, "error": error}
        finally:
            if client:
                try:
                    client.logout()
                except Exception:
                    pass

    def analyze_pending(self, account_id):
        if self.ai and self.store.setting("ai").get("automatic"):
            boundary = self.store.setting("ai_automatic_boundary")
            for row in self.store.rows("SELECT id FROM messages WHERE account_id=? AND hidden=0 AND analysis IS NULL AND sent=0 "
                                       "AND trashed=0 AND category<>'updates' AND date>? AND seq>? ORDER BY date DESC LIMIT 10",
                                       (account_id, boundary["since"], boundary["after_seq"])):
                if (not self.store.setting("ai").get("automatic")
                        or self.store.setting("ai_automatic_boundary") != boundary):
                    break
                account = self.store.account(account_id)
                if not account or not account["enabled"]:
                    break
                try:
                    self.ai.analyze(row["id"])
                except Exception as exc:
                    self.store.set_setting("ai_error", safe_error(exc))
                    break

    def _sync_google(self, account):
        from .google import Gmail, RateLimitError

        account_id = account["id"]
        client = None
        try:
            # Report a cumulative count: per-pass counts would appear to go
            # backwards between passes, which reads as lost progress.
            base = self._progress.get(account_id, {}).get("downloaded", 0)
            client = Gmail(self.store, account_id, lambda phase, count: self.report(account_id, phase, base + count))
            result = client.sync()
            self.store.execute("UPDATE accounts SET last_sync=?,error=NULL WHERE id=?", (time.time(), account_id))
            return result
        except RateLimitError as exc:
            # Back off for five minutes instead of hammering Google every pass.
            self._rate_limited_until[account_id] = time.time() + 300
            error = safe_error(exc)
            self.store.execute("UPDATE accounts SET error=? WHERE id=?", (error, account_id))
            return {"account_id": account_id, "ok": False, "error": error}
        except Exception as exc:
            error = safe_error(exc)
            self.store.execute("UPDATE accounts SET error=? WHERE id=?", (error, account_id))
            return {"account_id": account_id, "ok": False, "error": error}
        finally:
            if client:
                client.close()

    def sync_folder(self, client, account, folder):
        name = folder["name"]
        validity = select_folder(client, name)
        # A changed UIDVALIDITY invalidates identities and their queued operations.
        self.store.execute("DELETE FROM messages WHERE account_id=? AND folder=? AND uidvalidity!=?",
                           (account["id"], name, validity))
        status, data = client.uid("SEARCH", None, "ALL")
        check(status)
        remote_uids = {int(uid) for uid in (data[0] or b"").split()}
        existing = self.store.rows("SELECT id,uid FROM messages WHERE account_id=? AND folder=? AND uidvalidity=?",
                                   (account["id"], name, validity))
        by_uid = {row["uid"]: row["id"] for row in existing}
        for uid in by_uid.keys() - remote_uids:
            self.store.execute("DELETE FROM messages WHERE id=?", (by_uid[uid],))
        added = []
        # Newest first, then backfill in bounded batches without losing older mail.
        new_uids = sorted(remote_uids - by_uid.keys(), reverse=True)
        batch_size = 500
        for batch_start in range(0, len(new_uids), batch_size):
            self.report(account["id"], "downloading")
            uid_batch = new_uids[batch_start:batch_start + batch_size]
            uids_str = ",".join(str(uid) for uid in uid_batch)
            status, parts = client.uid("FETCH", uids_str, "(UID FLAGS BODY.PEEK[])")
            check(status)
            # Parse outside the writer lock, then commit in short chunks so
            # readers and local edits never queue behind a large download.
            parsed_batch = []
            for part in parts or []:
                if isinstance(part, tuple) and isinstance(part[1], bytes):
                    header_info = part[0].decode("utf-8", "replace") if isinstance(part[0], bytes) else str(part[0])
                    uid_match = re.search(r"UID (\d+)", header_info)
                    if not uid_match:
                        continue
                    if len(part[1]) > 25 * 1024 * 1024:
                        raise RuntimeError("Messaggio oltre il limite di 25 MB")
                    parsed_batch.append(parse_message(part[1], account["id"], name, validity, int(uid_match.group(1)),
                                                      part[0], folder["sent"], folder["archived"]))
            for chunk_start in range(0, len(parsed_batch), 25):
                with self.store.transaction():
                    for parsed in parsed_batch[chunk_start:chunk_start + 25]:
                        message_id = self.store.upsert_message(parsed)
                        if parsed["message_id"]:
                            key = self.moved_key(account["id"], parsed["message_id"])
                            moved = self.store.setting(key)
                            if moved:
                                self.store.execute("UPDATE messages SET category=?,analysis=?,snoozed_until=? WHERE id=?",
                                    (moved["category"], json.dumps(moved["analysis"]) if moved["analysis"] else None,
                                     moved["snoozed_until"], message_id))
                                self.store.execute("DELETE FROM settings WHERE key=?", (key,))
                            if folder["sent"]:
                                self.store.execute("DELETE FROM messages WHERE account_id=? AND folder='Milo/Sent' "
                                                   "AND message_id=?", (account["id"], parsed["message_id"]))
                        added.append(message_id)
                        with self._guard:
                            self._progress[account["id"]]["downloaded"] += 1
        known = sorted(remote_uids & by_uid.keys())
        for start in range(0, len(known), 100):
            uids = ",".join(str(uid) for uid in known[start:start + 100])
            status, parts = client.uid("FETCH", uids, "(UID FLAGS)")
            check(status)
            with self.store.transaction():
                for part in parts or []:
                    if not isinstance(part, bytes):
                        continue
                    match = re.search(rb"UID (\d+)", part)
                    if match and int(match[1]) in by_uid:
                        self.store.reconcile_flags(by_uid[int(match[1])], b"\\Seen" in part, b"\\Flagged" in part)
        return added

    def flush_changes(self, client, account, remote_folders):
        pending = self.store.rows("SELECT o.*,m.folder,m.uid,m.uidvalidity FROM outbox o JOIN messages m "
                                  "ON m.id=o.message_id WHERE m.account_id=? ORDER BY o.created", (account["id"],))
        for operation in pending:
            try:
                validity = select_folder(client, operation["folder"])
                if validity != operation["uidvalidity"]:
                    self.store.execute("DELETE FROM outbox WHERE id=?", (operation["id"],))
                    continue
                kind, value = operation["kind"], json.loads(operation["value"])
                if kind in {"archived", "trash"}:
                    target = (next((f["name"] for f in remote_folders if f.get("trash")), None) if kind == "trash"
                              else next((f["name"] for f in remote_folders if f["archived"]), None) if value else "INBOX")
                    if not target:
                        raise RuntimeError("Il server non espone una cartella " + ("Cestino" if kind == "trash" else "Archivio"))
                    if target == operation["folder"]:
                        self.store.execute("DELETE FROM outbox WHERE id=?", (operation["id"],))
                        continue
                    uid = str(operation["uid"])
                    target_quoted = '"' + target.replace('\\', '\\\\').replace('"', '\\"') + '"'
                    if "MOVE" in client.capabilities:
                        check(client.uid("MOVE", uid, target_quoted)[0])
                    else:
                        check(client.uid("COPY", uid, target_quoted)[0])
                        check(client.uid("STORE", uid, "+FLAGS.SILENT", "(\\Deleted)")[0])
                        check((client.uid("EXPUNGE", uid) if "UIDPLUS" in client.capabilities else client.expunge())[0])
                    # Destination is reimported with the server-assigned UID on this sync.
                    # Keep local intelligence attached via Message-ID on the destination.
                    source = self.store.message(operation["message_id"])
                    if kind != "trash" and source["message_id"]:
                        self.store.set_setting(self.moved_key(account["id"], source["message_id"]),
                                               {k: source[k] for k in ("category", "analysis", "snoozed_until")})
                else:
                    flag = "\\Seen" if kind == "read" else "\\Flagged"
                    check(client.uid("STORE", str(operation["uid"]), "+FLAGS.SILENT" if value else "-FLAGS.SILENT",
                                     f"({flag})")[0])
                self.store.execute("DELETE FROM outbox WHERE id=?", (operation["id"],))
            except Exception as exc:
                self.store.execute("UPDATE outbox SET error=? WHERE id=?", (safe_error(exc), operation["id"]))

    @staticmethod
    def moved_key(account_id, message_id):
        return "moved:" + account_id + ":" + hashlib.sha256(message_id.encode()).hexdigest()


def safe_error(exc):
    if isinstance(exc, (imaplib.IMAP4.error, smtplib.SMTPAuthenticationError)):
        return "Accesso rifiutato dal provider. Controlla utente e password per app."
    if isinstance(exc, (TimeoutError, OSError)):
        return "Server non raggiungibile. La sincronizzazione verrà riprovata."
    if isinstance(exc, RuntimeError):
        return str(exc)[:250]
    return "Operazione non riuscita. Controlla la configurazione del provider."


def recipient_headers(draft):
    # Completion leaves a comma ready for the next person; it is not a recipient.
    headers = [(draft.get(field) or "").rstrip(" ,\t") for field in ("to", "cc")]
    if any(c in value for value in headers for c in "\r\n\0"):
        raise ValueError("Inserisci destinatari validi")
    recipients = getaddresses([value for value in headers if value])
    if not recipients or any("@" not in address for _, address in recipients):
        raise ValueError("Inserisci destinatari validi")
    return headers


def build_message(account, draft, original=None, attachments=()):
    to, cc = recipient_headers(draft)
    message = EmailMessage()
    message["From"] = account["email"]
    message["To"] = to
    if cc:
        message["Cc"] = cc
    message["Subject"] = draft["subject"]
    message["Message-ID"] = make_msgid()
    message["Date"] = email.utils.formatdate(localtime=True)
    if original and original.get("message_id"):
        message["In-Reply-To"] = original["message_id"]
        message["References"] = original["message_id"]
    quote = reply_quote(draft, original)
    message.set_content(draft["body"] + quote)
    if draft.get("html"):
        message.add_alternative(html_with_quote(draft["html"], quote) if quote else draft["html"], subtype="html")
    for attachment in attachments:
        maintype, _, subtype = attachment["type"].partition("/")
        message.add_attachment(attachment["data"], maintype=maintype, subtype=subtype, filename=attachment["name"])
    return message


DAYS = ("lun", "mar", "mer", "gio", "ven", "sab", "dom")
MONTHS = ("gen", "feb", "mar", "apr", "mag", "giu", "lug", "ago", "set", "ott", "nov", "dic")
QUOTE_HEADER = re.compile(r"^(?:Il giorno .{0,300}ha scritto:|On .{0,300}wrote:)\s*$", re.M)


def reply_quote(draft, original):
    """The quoted original below a reply, unless the writer already quoted it."""
    if not original or draft.get("mode") == "forward" or QUOTE_HEADER.search(draft["body"]):
        return ""
    text = (original.get("body") or "").strip()
    if not text:
        return ""
    when = datetime.fromtimestamp(original["date"], ZoneInfo(os.environ.get("MILO_TIMEZONE", "Europe/Rome")))
    stamp = f"{DAYS[when.weekday()]} {when.day} {MONTHS[when.month - 1]} {when.year} alle {when:%H:%M}"
    sender = original.get("sender") or ""
    address = original.get("sender_email") or ""
    who = f"{sender} <{address}>" if sender and sender != address else address or sender
    quoted = "\n".join(">" + (" " + line if line else "") for line in text.splitlines())
    return f"\n\nIl giorno {stamp} {who} ha scritto:\n{quoted}\n"


def send_mail(account, draft, original=None, attachments=()):
    message = build_message(account, draft, original, attachments)
    recipients = list(dict.fromkeys(address for _, address in getaddresses(
        [str(message[header]) for header in ("To", "Cc") if message[header]])))
    context = ssl.create_default_context()
    if account["smtp_security"] == "tls":
        client = smtplib.SMTP_SSL(account["smtp_host"], account["smtp_port"], timeout=20, context=context)
    else:
        client = smtplib.SMTP(account["smtp_host"], account["smtp_port"], timeout=20)
    with client:
        client.ehlo()
        if account["smtp_security"] == "starttls":
            client.starttls(context=context)
            client.ehlo()
        client.login(account["username"], account["password"])
        refused = client.send_message(message, from_addr=account["email"], to_addrs=recipients)
        if refused:
            raise RuntimeError("Invio parziale: alcuni destinatari sono stati rifiutati. Verifica prima di reinviare.")
    return message


def html_with_quote(html, quote):
    """The plain-text quote as an HTML blockquote, placed before the closing body tag when present."""
    header, _, quoted = quote.strip("\n").partition("\n")
    lines = [line[2:] if line.startswith("> ") else line[1:] for line in quoted.splitlines()]
    block = (f'<br><div>{escape(header)}</div><blockquote style="margin:0 0 0 .8ex;border-left:1px solid #ccc;'
             f'padding-left:1ex">{"<br>".join(escape(line) for line in lines)}</blockquote>')
    match = re.search(r"</body\s*>", html, re.I)
    return html[:match.start()] + block + html[match.start():] if match else html + block


PIXEL_PATH = "/o/"
PIXEL_TOKEN = re.compile(r"[A-Za-z0-9_-]{24}")


def text_html(text):
    """Plain text as simple HTML paragraphs, for messages that need an HTML part."""
    blocks = re.split(r"\n{2,}", text or "")
    return "".join(f"<p>{escape(block).replace(chr(10), '<br>') or '<br>'}</p>" for block in blocks) or "<p><br></p>"


def html_with_pixel(html, url):
    """A 1x1 open-tracking image at the end of the HTML body."""
    image = f'<img src="{escape(url)}" width="1" height="1" alt="" style="display:block;width:1px;height:1px;border:0">'
    match = re.search(r"</body\s*>", html, re.I)
    return html[:match.start()] + image + html[match.start():] if match else html + image


def html_with_signature(html, signature, url, width, height):
    """Replace the composer's text signature with the tracked signature image, or append it."""
    image = (f'<img src="{escape(url)}" width="{width}" height="{height}" alt="{escape(" · ".join(signature.split(chr(10))))}" '
             'style="display:block;border:0;border-radius:12px">')
    lines = [line.rstrip() for line in signature.strip().splitlines()]
    pattern = (r"<p>\s*--(?:\s|&nbsp;|\u00a0)*<br\s*/?>\s*"
               + r"\s*<br\s*/?>\s*".join(re.escape(escape(line, quote=False)) for line in lines)
               + r"\s*(?:<br\s*/?>\s*)?</p>")
    block = f"<p>-- <br>{image}</p>"
    replaced, count = re.subn(pattern, lambda _: block, html, count=1)
    if count:
        return replaced
    match = re.search(r"</body\s*>", html, re.I)
    return html[:match.start()] + block + html[match.start():] if match else html + block
