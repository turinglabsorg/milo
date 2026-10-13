"""Google authorization and native Gmail synchronization.

Only the service owns Google tokens. Browser clients receive a Milo session.
"""
import base64
import json
import secrets
import time
from pathlib import Path
from urllib.parse import quote, urlsplit

import requests
from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import AuthorizedSession
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from oauthlib.oauth2 import OAuth2Error

from .mail import build_message, parse_message

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]
GMAIL_API = "https://gmail.googleapis.com/gmail/v1/users/me/"
HIDDEN_LABELS = {"TRASH", "SPAM", "DRAFT"}


def gmail_error(response):
    # Use structured reasons only; Google's free-form message can contain
    # account identifiers, URLs and request data.
    try:
        error = response.json().get("error", {})
        reasons = {item.get("reason") for group in ("errors", "details")
                   for item in error.get(group, []) if isinstance(item, dict)}
    except (ValueError, TypeError, AttributeError):
        reasons = set()
    if reasons & {"insufficientPermissions", "ACCESS_TOKEN_SCOPE_INSUFFICIENT"}:
        return "Manca il permesso Gmail. Ricollega la casella e consenti di leggere e gestire le email."
    if reasons & {"accessNotConfigured", "SERVICE_DISABLED"}:
        return "Gmail API è disabilitata nel progetto del client OAuth. Abilitala in Google Cloud."
    if "domainPolicy" in reasons:
        return "L’amministratore Google Workspace blocca Milo. Deve autorizzare l’app per questa casella."
    if response.status_code == 429 or reasons & {"rateLimitExceeded", "userRateLimitExceeded", "dailyLimitExceeded", "quotaExceeded"}:
        return "Google ha limitato temporaneamente le richieste. Milo riproverà la sincronizzazione."
    return "Google ha rifiutato questa operazione Gmail. Controlla i permessi della casella nelle impostazioni."


def decode_raw(raw):
    return base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))


class GoogleOAuth:
    def __init__(self, store, public_url, client_file=None):
        self.store = store
        parsed = urlsplit(public_url)
        if (parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1"})
                or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment
                or parsed.path not in {"", "/"}):
            raise ValueError("MILO_PUBLIC_URL deve essere un'origine HTTPS o localhost")
        self.public_url = public_url.rstrip("/")
        self.redirect_uri = self.public_url + "/api/oauth/google/callback"
        if client_file:
            self.configure(json.loads(Path(client_file).read_text()))

    def configure(self, data):
        config = data.get("web", data)
        client_id, client_secret = config.get("client_id", ""), config.get("client_secret", "")
        if (not isinstance(client_id, str) or not client_id.endswith(".apps.googleusercontent.com")
                or len(client_id) > 300 or not isinstance(client_secret, str) or not 5 <= len(client_secret) <= 1000):
            raise ValueError("Importa le credenziali OAuth Google di tipo Applicazione web")
        # Never trust auth/token URLs from an imported file.
        settings = {"client_id": client_id, "client_secret": client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token", "redirect_uris": [self.redirect_uri]}
        self.store.set_setting("google_client", self.store.encrypt_json({"web": settings}))

    def status(self):
        return {"configured": bool(self.store.setting("google_client")), "redirect_uri": self.redirect_uri}

    def config(self):
        encrypted = self.store.setting("google_client")
        if not encrypted:
            raise RuntimeError("Configura il client OAuth Google nelle impostazioni di Milo")
        return self.store.decrypt_json(encrypted)

    def flow(self, **kwargs):
        flow = Flow.from_client_config(self.config(), scopes=SCOPES, **kwargs)
        flow.redirect_uri = self.redirect_uri
        return flow

    def start(self, session, account_id=None):
        expected = None
        if account_id:
            account = self.store.account(account_id)
            if not account or account["provider"] != "google":
                raise ValueError("Account Google non trovato")
            expected = account["email"]
        flow = self.flow(autogenerate_code_verifier=True)
        options = {"login_hint": expected} if expected else {}
        url, state = flow.authorization_url(access_type="offline", prompt="consent select_account", **options)
        browser = secrets.token_urlsafe(32)
        self.store.begin_oauth(state, {"browser": browser, "session": session, "verifier": flow.code_verifier,
                                      "expected_email": expected})
        return url, browser

    def finish(self, state, browser, code):
        pending = self.store.consume_oauth(state, browser)
        if not pending or not self.store.valid_session(pending["session"]):
            raise ValueError("Autorizzazione scaduta o browser diverso. Riprova a collegare Google.")
        if not code:
            raise ValueError("Autorizzazione Google annullata")
        flow = self.flow(state=state, code_verifier=pending["verifier"])
        try:
            flow.fetch_token(code=code, timeout=30)
            granted = set(flow.credentials.granted_scopes or flow.credentials.scopes or [])
            if not set(SCOPES).issubset(granted):
                raise ValueError("Google non ha concesso l'accesso alla casella. Seleziona il permesso Gmail.")
            with AuthorizedSession(flow.credentials) as session:
                response = session.get(GMAIL_API + "profile", timeout=30)
                response.raise_for_status()
                address = response.json()["emailAddress"]
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code in {403, 429}:
                raise RuntimeError(gmail_error(exc.response)) from exc
            raise RuntimeError("Google non ha completato il collegamento. Controlla client OAuth, Gmail API e consenso.") from exc
        except (requests.RequestException, OAuth2Error, GoogleAuthError, KeyError, Warning) as exc:
            raise RuntimeError("Google non ha completato il collegamento. Controlla client OAuth, Gmail API e consenso.") from exc
        if not isinstance(address, str) or "@" not in address:
            raise RuntimeError("Google non ha restituito un indirizzo valido")
        if pending.get("expected_email") and address.casefold() != pending["expected_email"].casefold():
            raise ValueError("Hai scelto una casella diversa. Riprova selezionando " + pending["expected_email"] + ".")
        if not self.store.valid_session(pending["session"]):
            raise ValueError("La sessione Milo è stata revocata. Accedi e ricollega Google.")
        return self.store.google_account(address, json.loads(flow.credentials.to_json()))


class Gmail:
    def __init__(self, store, account_id, progress=None):
        self.store, self.account_id = store, account_id
        self.progress = progress or (lambda phase, count: None)
        self.downloaded = 0
        rows = store.rows("SELECT secret FROM accounts WHERE id=? AND provider='google'", (account_id,))
        if not rows:
            raise RuntimeError("Account Google non trovato")
        self.saved_secret = rows[0]["secret"]
        self.credentials = Credentials.from_authorized_user_info(store.decrypt_json(self.saved_secret))
        self.session = AuthorizedSession(self.credentials, max_refresh_attempts=1)
        self.last_token = self.credentials.token

    def close(self):
        self.session.close()

    def request(self, method, path, **kwargs):
        try:
            response = self.session.request(method, GMAIL_API + path, timeout=30, **kwargs)
            if self.credentials.token != self.last_token:
                # A reconnect can replace credentials while this request is in
                # flight. Never overwrite that new grant with an older refresh.
                saved = self.store.save_google_credentials(self.account_id, json.loads(self.credentials.to_json()),
                                                           self.saved_secret)
                if saved:
                    self.saved_secret = saved
                self.last_token = self.credentials.token
            if response.status_code == 404:
                return None
            if response.status_code in {403, 429}:
                raise RuntimeError(gmail_error(response))
            response.raise_for_status()
            return response.json()
        except GoogleAuthError as exc:
            raise RuntimeError("Accesso Google scaduto o revocato. Ricollega la casella nelle impostazioni.") from exc
        except requests.RequestException as exc:
            raise RuntimeError("Gmail non raggiungibile. La sincronizzazione verrà riprovata.") from exc

    def sync(self):
        self.flush_changes()
        state = self.store.rows("SELECT * FROM gmail_sync WHERE account_id=?", (self.account_id,))
        if not state:
            self.reset_scan()
        added = self.backfill()
        added += self.history()
        return {"account_id": self.account_id, "added": added, "ok": True}

    def reset_scan(self):
        profile = self.request("GET", "profile")
        if not profile or not profile.get("historyId"):
            raise RuntimeError("Gmail non ha restituito lo stato della casella")
        with self.store.lock, self.store.db:
            self.store.db.execute("DELETE FROM gmail_scan WHERE account_id=?", (self.account_id,))
            self.store.db.execute("INSERT OR REPLACE INTO gmail_sync VALUES(?,?,NULL,NULL,0)",
                                  (self.account_id, profile["historyId"]))

    def backfill(self):
        state = self.store.rows("SELECT * FROM gmail_sync WHERE account_id=?", (self.account_id,))[0]
        if state["backfill_complete"]:
            return 0
        params = {"maxResults": 100, "q": "-in:drafts", "includeSpamTrash": "false"}
        if state["backfill_page"]:
            params["pageToken"] = state["backfill_page"]
        page = self.request("GET", "messages", params=params)
        if page is None:
            raise RuntimeError("Impossibile leggere la casella Gmail")
        fetched = []
        for item in page.get("messages", []):
            self.progress("downloading", self.downloaded)
            if fetched:
                time.sleep(0.25)
            fetched.append((item["id"], self.fetch_remote(item["id"])))
        added = 0
        with self.store.transaction():
            for remote_id, remote in fetched:
                added += self.apply_remote(remote_id, remote)
            next_page = page.get("nextPageToken")
            # Commit the cursor only after the entire page has been stored. A failed
            # request retries the page idempotently instead of skipping messages.
            self.store.execute("UPDATE gmail_sync SET backfill_page=?,backfill_complete=? WHERE account_id=?",
                               (next_page, int(not next_page), self.account_id))
            if not next_page:
                self.store.execute("DELETE FROM messages WHERE account_id=? AND provider_id IS NOT NULL AND "
                                   "provider_id NOT IN (SELECT provider_id FROM gmail_scan WHERE account_id=?)",
                                   (self.account_id, self.account_id))
        return added

    def history(self):
        state = self.store.rows("SELECT * FROM gmail_sync WHERE account_id=?", (self.account_id,))[0]
        params = {"startHistoryId": state["history_id"], "maxResults": 100}
        if state["history_page"]:
            params["pageToken"] = state["history_page"]
        page = self.request("GET", "history", params=params)
        if page is None:
            # Gmail expires history cursors. Start a fresh full scan, retaining
            # cached mail until that scan succeeds rather than emptying the inbox.
            self.reset_scan()
            return 0
        changed, deleted = set(), set()
        for record in page.get("history", []):
            for item in record.get("messagesDeleted", []):
                deleted.add(item["message"]["id"])
            for key in ("messagesAdded", "labelsAdded", "labelsRemoved"):
                changed.update(item["message"]["id"] for item in record.get(key, []))
        fetched = []
        for remote_id in changed - deleted:
            if fetched:
                time.sleep(0.25)
            fetched.append((remote_id, self.fetch_remote(remote_id)))
        added = 0
        with self.store.transaction():
            for remote_id, remote in fetched:
                added += self.apply_remote(remote_id, remote)
            for remote_id in deleted:
                self.remove_message(remote_id)
            next_page = page.get("nextPageToken")
            if next_page:
                self.store.execute("UPDATE gmail_sync SET history_page=? WHERE account_id=?", (next_page, self.account_id))
            else:
                history_id = page.get("historyId", state["history_id"])
                self.store.execute("UPDATE gmail_sync SET history_id=?,history_page=NULL WHERE account_id=?",
                                   (history_id, self.account_id))
        return added

    def fetch_remote(self, remote_id):
        return self.request("GET", "messages/" + quote(remote_id, safe=""), params={"format": "raw"})

    def apply_remote(self, remote_id, remote):
        if remote is None:
            self.remove_message(remote_id)
            return 0
        added = self.store_message(remote)
        self.downloaded += 1
        self.progress("downloading", self.downloaded)
        return added

    def fetch_message(self, remote_id):
        self.progress("downloading", self.downloaded)
        return self.apply_remote(remote_id, self.fetch_remote(remote_id))

    def store_message(self, remote):
        remote_id = remote["id"]
        labels = set(remote.get("labelIds", []))
        raw = decode_raw(remote["raw"])
        if len(raw) > 100 * 1024 * 1024:
            raise RuntimeError("Messaggio Gmail oltre il limite attuale di 100 MB")
        flags = (b"\\Seen" if "UNREAD" not in labels else b"") + (b" \\Flagged" if "STARRED" in labels else b"")
        data = parse_message(raw, self.account_id, "Gmail", "gmail:"+remote_id, 0, flags,
                             sent="SENT" in labels, archived="INBOX" not in labels and "SENT" not in labels)
        data.update(provider_id=remote_id, thread_id=remote.get("threadId"), labels=json.dumps(sorted(labels)),
                    hidden=int(bool(labels & HIDDEN_LABELS)))
        if remote.get("internalDate"):
            data["date"] = int(remote["internalDate"]) / 1000
        with self.store.lock:
            existing = self.store.rows("SELECT id FROM messages WHERE account_id=? AND provider_id=?",
                                       (self.account_id, remote_id))
            if existing:
                message_id = existing[0]["id"]
                pending = {op["kind"] for op in self.store.rows("SELECT kind FROM outbox WHERE message_id=?", (message_id,))}
                for key in ("read", "starred", "archived", "sent", "hidden", "labels", "thread_id"):
                    if key not in pending and not (key == "hidden" and "trash" in pending):
                        self.store.execute(f"UPDATE messages SET {key}=? WHERE id=?", (data[key], message_id))
            else:
                self.store.upsert_message(data)
            self.store.execute("INSERT OR IGNORE INTO gmail_scan VALUES(?,?)", (self.account_id, remote_id))
            return int(not existing)

    def remove_message(self, remote_id):
        self.store.execute("DELETE FROM messages WHERE account_id=? AND provider_id=?", (self.account_id, remote_id))
        self.store.execute("DELETE FROM gmail_scan WHERE account_id=? AND provider_id=?", (self.account_id, remote_id))

    def flush_changes(self):
        self.progress("applying", self.downloaded)
        pending = self.store.rows("SELECT o.*,m.provider_id FROM outbox o JOIN messages m ON m.id=o.message_id "
                                  "WHERE m.account_id=? ORDER BY o.created", (self.account_id,))
        for operation in pending:
            value = json.loads(operation["value"])
            kind = operation["kind"]
            try:
                if kind == "trash":
                    result = self.request("POST", "messages/" + quote(operation["provider_id"], safe="") + "/trash")
                else:
                    label = {"read": "UNREAD", "starred": "STARRED", "archived": "INBOX"}[kind]
                    add = value if kind == "starred" else not value
                    result = self.request("POST", "messages/" + quote(operation["provider_id"], safe="") + "/modify",
                                          json={"addLabelIds": [label] if add else [], "removeLabelIds": [] if add else [label]})
                if result is None:
                    self.remove_message(operation["provider_id"])
                else:
                    self.store.execute("DELETE FROM outbox WHERE id=?", (operation["id"],))
            except RuntimeError as exc:
                self.store.execute("UPDATE outbox SET error=? WHERE id=?", (str(exc), operation["id"]))

    def send(self, account, draft, original=None):
        mail = build_message(account, draft, original)
        raw = base64.urlsafe_b64encode(mail.as_bytes()).decode()
        payload = {"raw": raw}
        if original and original.get("thread_id") and original.get("account_id") == self.account_id:
            payload["threadId"] = original["thread_id"]
        result = self.request("POST", "messages/send", json=payload)
        if not result or not result.get("id"):
            raise RuntimeError("Google non ha confermato l'invio. Controlla la posta inviata prima di riprovare.")
        self.store_message({**result, "raw": raw, "labelIds": result.get("labelIds", ["SENT"]),
                            "internalDate": str(int(time.time()*1000))})
        return result
