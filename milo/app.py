import asyncio
import email
import hashlib
import json
import time
import uuid
from contextlib import asynccontextmanager
from email import policy
from email.utils import getaddresses
from ipaddress import ip_address
from pathlib import Path
from urllib.parse import quote, urlsplit

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.gzip import GZipMiddleware

from .ai import AI
from .demo import seed_demo
from .google import Gmail, GoogleOAuth
from .mail import SyncEngine, parse_message, safe_error, send_mail
from .models import (
    AccountInput,
    AccountUpdate,
    AISettings,
    Appearance,
    DraftInput,
    GoogleStart,
    Identity,
    Login,
    MessagePatch,
    RuleInput,
    SetupGrant,
)
from .recap import RecapWorker
from .render import render_html
from .store import Store


def create_app(directory: Path, demo=False, ollama_url="http://127.0.0.1:11434", secure_cookies=False,
               public_url="http://127.0.0.1:8025", google_client=None, private_url=None, tailscale_owners=None,
               proxy_peers=()):
    owners = frozenset(tailscale_owners or ())
    trusted_peers = {"127.0.0.1", "::1"}
    for peer in proxy_peers:
        address = ip_address(peer)
        if not address.is_private or address.is_unspecified:
            raise ValueError("Only explicit private proxy addresses are supported")
        trusted_peers.add(str(address))
    if bool(private_url) != bool(owners):
        raise ValueError("Private access requires an HTTPS origin and an explicit owner allowlist")
    if private_url and (urlsplit(private_url).scheme != "https" or not secure_cookies):
        raise ValueError("Private access requires HTTPS and secure cookies")
    client_url = (private_url or public_url).rstrip("/")
    store = Store(directory)
    ai = AI(store, ollama_url)
    recaps = RecapWorker(store, ai)
    store.on_mail_change = recaps.wake
    engine = SyncEngine(store, ai)
    google = GoogleOAuth(store, public_url, google_client)
    sync_lock = asyncio.Lock()
    stop_worker = asyncio.Event()
    wake_worker = asyncio.Event()
    worker_loop = None
    attempts = {}
    sending = set()
    if demo:
        seed_demo(store)

    async def sync():
        async with sync_lock:
            return await asyncio.to_thread(engine.sync_all)

    async def worker():
        while not stop_worker.is_set():
            wake_worker.clear()
            if not demo:
                await sync()
                recaps.wake()
            try:
                await asyncio.wait_for(wake_worker.wait(), timeout=60)
            except TimeoutError:
                continue

    @asynccontextmanager
    async def lifespan(app):
        nonlocal worker_loop
        worker_loop = asyncio.get_running_loop()
        task = asyncio.create_task(worker())
        recap_task = asyncio.create_task(recaps.run()) if not demo else None
        yield
        # Do not close SQLite while a sync thread is still using it.
        stop_worker.set()
        wake_worker.set()
        recaps.stop()
        await task
        if recap_task:
            await recap_task
        store.close()

    def wake_sync():
        if worker_loop and not demo:
            worker_loop.call_soon_threadsafe(wake_worker.set)

    app = FastAPI(title="Milo", version="0.1.0", lifespan=lifespan, docs_url=None, redoc_url=None,
                  openapi_url=None)
    app.state.recaps = recaps
    app.state.store, app.state.engine, app.state.ai, app.state.google = store, engine, ai, google
    app.add_middleware(GZipMiddleware, minimum_size=1000, compresslevel=4)

    def owner(request):
        # Tailscale Serve strips supplied identity headers, then adds its own.
        # Docker publishes only host loopback ports; its exact gateway is explicit.
        # Uvicorn proxy_headers remains disabled for identity attestation.
        return bool(owners and request.client and request.client.host in trusted_peers
                    and request.headers.get("tailscale-user-login") in owners)

    @app.middleware("http")
    async def guard(request: Request, call_next):
        if owners:
            local_health = (request.method == "GET" and request.url.path == "/api/status"
                            and request.client and request.client.host in {"127.0.0.1", "::1"}
                            and urlsplit("http://" + request.headers.get("host", "")).hostname
                            in {"localhost", "127.0.0.1", "::1"})
            if (not owner(request) and not local_health) or request.url.path in {
                "/api/login", "/api/logout", "/api/setup", "/api/setup/authorize", "/api/setup/status"
            }:
                return Response(status_code=404, headers={"Cache-Control": "no-store"})
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin")
            expected = urlsplit(client_url).netloc if owners else request.headers.get("host")
            if origin and (urlsplit(origin).netloc != expected
                           or (owners and urlsplit(origin).scheme != urlsplit(client_url).scheme)):
                return Response(status_code=403)
            if request.headers.get("sec-fetch-site") == "cross-site":
                return Response(status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    def auth(request: Request):
        if not owner(request) and not demo and not store.valid_session(request.cookies.get("milo_session")):
            raise HTTPException(401, "Accedi a Milo")

    def live():
        if demo:
            raise HTTPException(400, "Questa è una demo. Avvia Milo senza --demo per collegare account reali.")

    def message_or_404(message_id, raw=False, metadata=False):
        message = store.message(message_id, raw, metadata)
        if not message:
            raise HTTPException(404, "Email non trovata")
        return message

    @app.get("/api/status")
    def status(request: Request, response: Response):
        trusted = owner(request)
        if trusted and not store.valid_session(request.cookies.get("milo_session")):
            issue_session(response)
        authenticated = trusted or (not owners and (demo or store.valid_session(request.cookies.get("milo_session"))))
        return {"service": "milo", "demo": demo, "initialized": bool(owners or store.setting("password")), "authenticated": authenticated,
                "access": "tailscale" if owners else "password",
                "version": "0.1.0"}

    def issue_session(response):
        response.set_cookie("milo_session", store.new_session(), httponly=True, secure=secure_cookies,
                            samesite="strict", max_age=30 * 86400)
        return {"ok": True}

    @app.post("/api/setup/authorize")
    def setup_authorize(data: SetupGrant, response: Response):
        live()
        if not store.setup_allowed(data.token):
            raise HTTPException(403, "Il collegamento di attivazione non è più valido. Riapri l'app Milo.")
        response.set_cookie("milo_setup", data.token, httponly=True, secure=secure_cookies,
                            samesite="strict", max_age=1800, path="/api/setup")
        return {"ok": True}

    @app.get("/api/setup/status")
    def setup_status(request: Request):
        return {"authorized": store.setup_allowed(request.cookies.get("milo_setup", ""))}

    @app.post("/api/setup")
    def setup(data: Login, request: Request, response: Response):
        live()
        if not store.setup(data.password, data.bootstrap or request.cookies.get("milo_setup", "")):
            raise HTTPException(403, "Riapri l'app Milo per configurare l'accesso, oppure accedi se è già configurato.")
        response.delete_cookie("milo_setup", path="/api/setup", secure=secure_cookies,
                               httponly=True, samesite="strict")
        return issue_session(response)

    @app.post("/api/login")
    def login(data: Login, request: Request, response: Response):
        address = request.client.host if request.client else "unknown"
        now = time.time()
        attempts[address] = [t for t in attempts.get(address, []) if t > now - 300]
        if len(attempts[address]) >= 8:
            raise HTTPException(429, "Troppi tentativi. Riprova tra cinque minuti.")
        attempts[address].append(now)
        if not store.login(data.password):
            raise HTTPException(401, "Passphrase non corretta")
        attempts.pop(address, None)
        return issue_session(response)

    @app.post("/api/logout", dependencies=[Depends(auth)])
    def logout(request: Request, response: Response):
        if request.cookies.get("milo_session"):
            store.logout(request.cookies["milo_session"])
        response.delete_cookie("milo_session")
        return {"ok": True}

    @app.put("/api/settings/google", dependencies=[Depends(auth)])
    def settings_google(data: dict):
        live()
        if len(json.dumps(data)) > 16000:
            raise HTTPException(422, "File OAuth troppo grande")
        try:
            google.configure(data)
        except (ValueError, TypeError, AttributeError) as exc:
            raise HTTPException(422, "Importa il JSON OAuth Google di tipo Applicazione web") from exc
        return google.status()

    @app.post("/api/oauth/google/start", dependencies=[Depends(auth)])
    def google_start(request: Request, response: Response, data: GoogleStart | None = None):
        live()
        try:
            url, browser = google.start(request.cookies.get("milo_session"), data.account_id if data else None)
        except RuntimeError as exc:
            raise HTTPException(400, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc
        # Google returns via a cross-site top-level navigation. Keep the main
        # session Strict; this short-lived Lax nonce binds only the OAuth flow.
        response.set_cookie("milo_oauth", browser, httponly=True, secure=secure_cookies,
                            samesite="lax", max_age=600, path="/api/oauth/google")
        return {"url": url}

    @app.get("/api/oauth/google/callback")
    def google_callback(request: Request, background: BackgroundTasks, state="", code="", error=""):
        live()
        try:
            account_id = google.finish(state, request.cookies.get("milo_oauth"), "" if error else code)
        except (ValueError, RuntimeError) as exc:
            response = RedirectResponse(client_url + "/#google_error=" + quote(str(exc), safe=""), 303)
        else:
            response = RedirectResponse(client_url + "/#google_connected=1", 303)
            issue_session(response)
            account = next(a for a in store.accounts(private=True) if a["id"] == account_id)
            background.add_task(engine.sync_account, account)
        response.delete_cookie("milo_oauth", path="/api/oauth/google")
        return response

    @app.get("/api/state", dependencies=[Depends(auth)])
    def state():
        inbox = store.rows("SELECT COUNT(DISTINCT account_id || ':' || COALESCE(thread_id,id)) AS count,SUM(read=0) AS unread FROM messages WHERE hidden=0 AND trashed=0 AND archived=0 AND sent=0 "
                           "AND (snoozed_until IS NULL OR snoozed_until<=?)", (time.time(),))[0]
        return {"accounts": store.accounts(), "ai": store.setting("ai"), "ai_error": store.setting("ai_error"),
                "identity": store.setting("identity") or Identity().model_dump(),
                "recap": {"generated_at": recaps.snapshot()["generated_at"],
                          "phase": recaps.snapshot()["status"]["phase"]},
                "appearance": store.setting("appearance") or {"theme": "system"}, "sync": engine.status(),
                "google": google.status(), "rules": store.rules(),
                "pending": store.rows("SELECT kind,error,COUNT(*) AS count FROM outbox GROUP BY kind,error"),
                "counts": {"inbox": inbox["count"], "unread": inbox["unread"] or 0,
                           "starred": store.rows("SELECT COUNT(*) AS count FROM messages WHERE hidden=0 AND trashed=0 AND starred=1")[0]["count"],
                           "drafts": store.rows("SELECT COUNT(*) AS count FROM drafts")[0]["count"],
                           "snoozed": store.rows("SELECT COUNT(*) AS count FROM messages WHERE hidden=0 AND trashed=0 AND snoozed_until>?",
                                                 (time.time(),))[0]["count"]}}

    @app.post("/api/accounts", dependencies=[Depends(auth)])
    def add_account(data: AccountInput, background: BackgroundTasks):
        live()
        if any(a["email"].casefold() == data.email.casefold() for a in store.accounts()):
            raise HTTPException(409, "Questo account è già collegato")
        account_id = store.add_account(data.model_dump())
        account = next(a for a in store.accounts(private=True) if a["id"] == account_id)
        background.add_task(engine.sync_account, account)
        return {"id": account_id}

    @app.patch("/api/accounts/{account_id}", dependencies=[Depends(auth)])
    def update_account(account_id: str, data: AccountUpdate, background: BackgroundTasks):
        live()
        patch = data.model_dump(exclude_unset=True)
        connection_fields = set(patch) - {"name", "enabled", "color"}
        lock = engine.account_lock(account_id) if connection_fields else store.lock
        with lock:
            previous = store.account(account_id)
            if not previous:
                raise HTTPException(404, "Account non trovato")
            if any(value is None for value in patch.values()):
                raise HTTPException(422, "Impostazioni account non valide")
            if previous["provider"] == "google" and set(patch) - {"name", "enabled", "color"}:
                raise HTTPException(422, "Per aggiornare l'accesso Google usa Ricollega")
            changed = {key for key, value in patch.items() if key == "password" or previous.get(key) != value}
            try:
                account = store.update_account(account_id, {key: patch[key] for key in changed})
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from exc
            connection = changed - {"name", "enabled", "color"}
            if account["enabled"] and (connection or ("enabled" in changed)):
                background.add_task(engine.sync_account, account)
        return account

    @app.post("/api/sync", dependencies=[Depends(auth)], status_code=202)
    async def sync_now(background: BackgroundTasks):
        if demo:
            return {"results": [], "demo": True}
        if not sync_lock.locked():
            background.add_task(sync)
        return {"accepted": True}

    @app.get("/api/messages", dependencies=[Depends(auth)])
    def messages(view="inbox", category: str | None = None, account: str | None = None, search=""):
        return {"messages": store.conversations(view, category, account, search[:300])}

    @app.get("/api/messages/{message_id}", dependencies=[Depends(auth)])
    def get_message(message_id: str, load_images: bool = False):
        message = message_or_404(message_id, raw=True)
        raw = message.pop("raw")
        mail = email.message_from_bytes(raw, policy=policy.default)
        if not message.get("content_version"):
            message["content_version"] = hashlib.sha256(raw).hexdigest()
            store.execute("UPDATE messages SET content_version=? WHERE id=? AND content_version IS NULL",
                          (message["content_version"], message_id))
        for header, field in (("To", "to_addresses"), ("Cc", "cc_addresses"), ("Reply-To", "reply_to_addresses")):
            message[field] = [{"name": name, "email": address} for name, address in getaddresses(mail.get_all(header, []))
                              if address and "@" in address and not any(char in address for char in "\r\n\x00")]
        message["body_loaded"] = True
        message.update(render_html(mail, message_id, load_images))
        message["attachments"] = [{"index": i, "name": part.get_filename() or "allegato",
                                    "type": part.get_content_type()}
                                   for i, part in enumerate(mail.walk()) if part.get_filename()]
        return message

    @app.get("/api/messages/{message_id}/attachments/{index}", dependencies=[Depends(auth)])
    def attachment(message_id: str, index: int):
        message = message_or_404(message_id, raw=True)
        parts = list(email.message_from_bytes(message["raw"], policy=policy.default).walk())
        if index < 0 or index >= len(parts) or not (parts[index].get_filename() or parts[index].get("Content-ID")):
            raise HTTPException(404, "Allegato non trovato")
        part = parts[index]
        inline = part.get_content_type() in {"image/png", "image/jpeg", "image/gif", "image/webp"}
        return Response(part.get_payload(decode=True) or b"", media_type=part.get_content_type() if inline else "application/octet-stream",
                        headers={"Content-Disposition": ("inline" if inline else "attachment") + "; filename*=UTF-8''" + quote(part.get_filename() or "immagine", safe="")})

    @app.get("/api/messages/{message_id}/thread", dependencies=[Depends(auth)])
    def get_thread(message_id: str, background: BackgroundTasks, load_images: bool = False, lazy: bool = False):
        message_or_404(message_id, metadata=True)
        messages = store.conversation(message_id, raw=not lazy, metadata=lazy)
        for message in messages:
            if lazy:
                message["body_loaded"] = False
                continue
            mail = email.message_from_bytes(message.pop("raw"), policy=policy.default)
            message.update(render_html(mail, message["id"], load_images))
            message["attachments"] = [{"index": i, "name": part.get_filename(), "type": part.get_content_type()}
                                      for i, part in enumerate(mail.walk()) if part.get_filename()]
        account = store.account(messages[0]["account_id"]) if messages else None
        progress = engine.thread_status(message_id)
        if not demo and account and account["provider"] == "google" and account["enabled"]:
            if not progress or progress.get("updated", 0) < time.time() - 30:
                progress = {"phase": "downloading"}
                background.add_task(engine.sync_thread, message_id)
        return {"messages": messages, "sync": progress}

    @app.patch("/api/messages/{message_id}/thread", dependencies=[Depends(auth)])
    def patch_thread(message_id: str, data: MessagePatch):
        message_or_404(message_id)
        patch = data.model_dump(exclude_unset=True)
        if any(v is None for k, v in patch.items() if k != "snoozed_until"):
            raise HTTPException(422, "Stato non valido")
        store.patch_conversation(message_id, patch)
        if set(patch) & {"read", "starred", "archived"}:
            wake_sync()
        return {"ok": True}

    @app.delete("/api/messages/{message_id}/thread", dependencies=[Depends(auth)], status_code=202)
    def trash_thread(message_id: str):
        message_or_404(message_id)
        store.trash_conversation(message_id)
        if demo:
            store.execute("DELETE FROM outbox WHERE message_id IN (SELECT id FROM messages WHERE trashed=1)")
        else:
            wake_sync()
        return {"accepted": True}

    @app.put("/api/settings/appearance", dependencies=[Depends(auth)])
    def appearance(data: Appearance):
        store.set_setting("appearance", data.model_dump())
        return data

    @app.patch("/api/messages/{message_id}", dependencies=[Depends(auth)])
    def patch_message(message_id: str, data: MessagePatch):
        message = message_or_404(message_id)
        account = store.account(message["account_id"])
        # Gmail identities survive label changes. Apply local edits immediately
        # while network sync runs; the outbox preserves later user operations.
        lock = store.lock if account["provider"] == "google" else engine.account_lock(message["account_id"])
        with lock:
            patch = data.model_dump(exclude_unset=True)
            if any(v is None for k, v in patch.items() if k != "snoozed_until"):
                raise HTTPException(422, "Stato non valido")
            if not store.patch_message(message_id, patch):
                raise HTTPException(404, "Email non trovata")
            if demo:
                store.execute("DELETE FROM outbox WHERE message_id=?", (message_id,))
        return store.message(message_id)

    @app.put("/api/settings/ai", dependencies=[Depends(auth)])
    def settings_ai(data: AISettings):
        store.set_setting("ai", data.model_dump())
        recaps.wake()
        return data

    @app.put("/api/settings/identity", dependencies=[Depends(auth)])
    def settings_identity(data: Identity):
        store.set_setting("identity", data.model_dump())
        recaps.wake()
        return data

    @app.post("/api/messages/{message_id}/analyze", dependencies=[Depends(auth)])
    def analyze(message_id: str):
        live()
        message_or_404(message_id)
        try:
            return ai.analyze(message_id)
        except RuntimeError as exc:
            raise HTTPException(503, str(exc)) from exc

    @app.get("/api/recap", dependencies=[Depends(auth)])
    @app.post("/api/recap", dependencies=[Depends(auth)])
    def recap():
        result = recaps.snapshot()
        result.pop("fingerprint", None)
        return result

    @app.post("/api/messages/{message_id}/reply", dependencies=[Depends(auth)])
    def ai_reply(message_id: str):
        live()
        message_or_404(message_id)
        try:
            return ai.reply(message_id)
        except RuntimeError as exc:
            raise HTTPException(503, str(exc)) from exc

    @app.post("/api/rules", dependencies=[Depends(auth)])
    def add_rule(data: RuleInput):
        rule_id = store.add_rule(data.model_dump())
        field = {"sender": "sender_email", "subject": "subject", "body": "body"}[data.field]
        # Literal substring semantics, shared with import and AI rule precedence.
        for row in store.rows(f"SELECT id,{field} FROM messages"):
            if data.contains.casefold() in row[field].casefold():
                store.execute("UPDATE messages SET category=? WHERE id=?", (data.category, row["id"]))
        return {"id": rule_id}

    @app.delete("/api/rules/{rule_id}", dependencies=[Depends(auth)])
    def delete_rule(rule_id: str):
        store.execute("DELETE FROM rules WHERE id=?", (rule_id,))
        return {"ok": True}

    @app.get("/api/drafts", dependencies=[Depends(auth)])
    def drafts():
        return {"drafts": [{**json.loads(row["data"]), "id": row["id"], "updated": row["updated"]}
                           for row in store.rows("SELECT * FROM drafts ORDER BY updated DESC")]}

    @app.put("/api/drafts", dependencies=[Depends(auth)])
    def save_draft(data: DraftInput):
        if not any(a["id"] == data.account_id for a in store.accounts()):
            raise HTTPException(404, "Account non trovato")
        draft_id = data.id or uuid.uuid4().hex
        with store.lock:
            existing = store.rows("SELECT data FROM drafts WHERE id=?", (draft_id,))
            if existing and data.revision and json.loads(existing[0]["data"]).get("revision", 0) > data.revision:
                raise HTTPException(409, "Questa bozza contiene modifiche più recenti. La tua copia resta nelle bozze in attesa.")
            store.execute("INSERT OR REPLACE INTO drafts VALUES(?,?,?)", (draft_id, data.model_dump_json(), time.time()))
        return {"id": draft_id}

    @app.delete("/api/drafts/{draft_id}", dependencies=[Depends(auth)])
    def delete_draft(draft_id: str):
        store.execute("DELETE FROM drafts WHERE id=?", (draft_id,))
        return {"ok": True}

    @app.post("/api/drafts/{draft_id}/send", dependencies=[Depends(auth)])
    def send(draft_id: str):
        live()
        # One explicit send at a time per draft, never automatically retried.
        with store.lock:
            if draft_id in sending:
                raise HTTPException(409, "Invio già in corso")
            rows = store.rows("SELECT data FROM drafts WHERE id=?", (draft_id,))
            if not rows:
                raise HTTPException(404, "Bozza non trovata")
            saved_data = rows[0]["data"]
            draft = json.loads(saved_data)
            account = store.account(draft["account_id"])
            if not account:
                raise HTTPException(404, "Account non trovato")
            sending.add(draft_id)
        try:
            original = store.message(draft["reply_to_id"]) if draft.get("reply_to_id") else None
            if account["provider"] == "google":
                client = Gmail(store, account["id"])
                try:
                    client.send(account, draft, original)
                finally:
                    client.close()
            else:
                with engine.account_lock(account["id"]):
                    account = store.account(account["id"], private=True)
                    mail = send_mail(account, draft, original)
                    store.upsert_message(parse_message(mail.as_bytes(), account["id"], "Milo/Sent", "local", time.time_ns(),
                                                       b"\\Seen", sent=True))
            # A second device may save a newer version during this explicit
            # send. Delete only the version that was actually submitted.
            store.execute("DELETE FROM drafts WHERE id=? AND data=?", (draft_id, saved_data))
            return {"ok": True}
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        except Exception as exc:
            raise HTTPException(502, safe_error(exc) + " L'invio non viene ripetuto automaticamente; "
                                "controlla la posta inviata prima di riprovare.") from exc
        finally:
            with store.lock:
                sending.discard(draft_id)

    source_web = Path(__file__).resolve().parent.parent / "web"
    web = source_web if source_web.exists() else Path(__file__).resolve().parent / "web"

    @app.get("/")
    def index():
        return FileResponse(web / "index.html")

    @app.get("/sw.js")
    def service_worker():
        return FileResponse(web / "sw.js", media_type="application/javascript", headers={"Service-Worker-Allowed": "/"})

    app.mount("/static", StaticFiles(directory=web), name="static")
    return app
