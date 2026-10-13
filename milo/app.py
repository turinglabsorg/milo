import asyncio
import email
import hashlib
import json
import math
import time
import uuid
from contextlib import asynccontextmanager
from email import policy
from email.parser import BytesHeaderParser
from email.utils import getaddresses
from ipaddress import ip_address
from pathlib import Path
from urllib.parse import quote, urlsplit

import httpx
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.gzip import GZipMiddleware

from .ai import AI
from .demo import seed_demo
from .features import Features
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
    Question,
    RuleInput,
    ScheduleInput,
    ScreenerSettings,
    SenderAction,
    SenderPatch,
    SetupGrant,
    Signatures,
    Templates,
    TodoPatch,
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
    features = Features(store)
    ai = AI(store, ollama_url)
    ai.on_analysis = features.sync_todos
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

    def feature_tick(minute):
        for draft_id in features.due():
            try:
                deliver(draft_id)
            except HTTPException as exc:
                features.schedule_failed(draft_id, str(exc.detail))
        if minute:
            features.check_followups()
            features.enforce_blocked()
            if time.time() - (store.setting("blobs_swept") or 0) > 86400:
                store.sweep_blobs(stop_worker.is_set)
                store.set_setting("blobs_swept", time.time())

    async def feature_worker():
        last = 0
        while not stop_worker.is_set():
            minute = time.time() - last >= 60
            if minute:
                last = time.time()
            try:
                await asyncio.to_thread(feature_tick, minute)
            except Exception:
                pass
            try:
                await asyncio.wait_for(stop_worker.wait(), timeout=5)
            except TimeoutError:
                continue

    @asynccontextmanager
    async def lifespan(app):
        nonlocal worker_loop
        worker_loop = asyncio.get_running_loop()
        def background_migrations():
            # Fresh statistics keep conversation queries on indexes after bulk imports.
            store.execute("ANALYZE")
            features.backfill_todos(stop=stop_worker.is_set)
            for account in store.rows("SELECT id FROM accounts WHERE removing=1"):
                features.purge_account(account["id"], stop=stop_worker.is_set)

        previews = asyncio.create_task(asyncio.to_thread(background_migrations))
        feature_task = asyncio.create_task(feature_worker()) if not demo else None
        task = asyncio.create_task(worker())
        recap_task = asyncio.create_task(recaps.run()) if not demo else None
        yield
        # Do not close SQLite while a sync thread is still using it.
        stop_worker.set()
        wake_worker.set()
        recaps.stop()
        await task
        if feature_task:
            await feature_task
        await previews
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
    app.state.features, app.state.feature_tick = features, feature_tick
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
        now = time.time()
        screening = features.screening()
        # Group on the covering catalogue index; COUNT(DISTINCT expr) needs a temp B-tree per call.
        counts = store.rows("SELECT SUM(inbox) AS inbox,SUM(inbox*unread) AS unread,SUM(starred) AS starred,SUM(snoozed) AS snoozed "
                            "FROM (SELECT MAX((archived=0 AND sent=0 AND (snoozed_until IS NULL OR snoozed_until<=?))::int) AS inbox,"
                            "SUM((read=0 AND archived=0 AND sent=0 AND (snoozed_until IS NULL OR snoozed_until<=?))::int) AS unread,"
                            "MAX(starred) AS starred,MAX((snoozed_until>?)::int) AS snoozed FROM messages "
                            "WHERE hidden=0 AND trashed=0 GROUP BY account_id,COALESCE(thread_id,id))", (now, now, now))[0]
        return {"accounts": store.accounts(), "ai": store.setting("ai"), "ai_error": store.setting("ai_error"),
                "identity": store.setting("identity") or Identity().model_dump(),
                "recap": {"generated_at": recaps.snapshot()["generated_at"],
                          "phase": recaps.snapshot()["status"]["phase"]},
                "appearance": store.setting("appearance") or {"theme": "system"}, "sync": engine.status(),
                "google": google.status(), "rules": store.rules(),
                "pending": store.rows("SELECT kind,error,COUNT(*) AS count FROM outbox GROUP BY kind,error"),
                "signatures": store.setting("signatures") or {}, "templates": store.setting("templates") or [],
                "screener": {**features.screener(), "pending": [row["email"] for row in screening]},
                "vips": features.vips(),
                "counts": {"inbox": counts["inbox"] or 0, "unread": counts["unread"] or 0,
                           "starred": counts["starred"] or 0, "snoozed": counts["snoozed"] or 0,
                           "drafts": store.rows("SELECT COUNT(*) AS count FROM drafts")[0]["count"],
                           "todo": features.todo_count(), "screener": len(screening)}}

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

    @app.get("/api/client/messages", dependencies=[Depends(auth)])
    def client_messages(before_date: float | None = None, before_id: str = ""):
        if (before_date is None) != (not before_id) or len(before_id) > 128 or (before_date is not None and not math.isfinite(before_date)):
            raise HTTPException(422, "Cursore non valido")
        before = (before_date, before_id) if before_id else None
        messages = store.conversations(view="all", limit=201, before=before, chronological=True)
        more = len(messages) > 200
        messages = messages[:200]
        last = messages[-1] if messages else None
        return {"messages": messages, "next": {"before_date": last["date"], "before_id": last["id"]} if more else None}

    @app.get("/api/client/thread", dependencies=[Depends(auth)])
    def client_thread(account: str, thread: str):
        messages = store.conversations(view="all", account=account, thread=thread, limit=1)
        if not messages:
            raise HTTPException(404, "Conversazione non trovata")
        return {"message": messages[0]}

    @app.get("/api/messages/{message_id}/recipients", dependencies=[Depends(auth)])
    def message_recipients(message_id: str):
        message = message_or_404(message_id, metadata=True)
        try:
            headers = store.message_headers(message_id)
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        mail = BytesHeaderParser(policy=policy.default).parsebytes(headers)
        result = {key: message[key] for key in ("id", "account_id", "sender_email", "subject", "content_version")}
        for header, field in (("To", "to_addresses"), ("Cc", "cc_addresses"), ("Reply-To", "reply_to_addresses")):
            result[field] = [{"name": name, "email": address} for name, address in getaddresses(
                [str(value) for value in mail.get_all(header, [])]) if address]
        return result

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
        message["unsubscribe"] = None if message["sent"] else features.unsubscribe_options(store.message_headers(message_id))
        return message

    @app.get("/api/messages/{message_id}/attachments/{index}", dependencies=[Depends(auth)])
    def attachment(message_id: str, index: int, preview: bool = False):
        message = message_or_404(message_id, raw=True)
        parts = list(email.message_from_bytes(message["raw"], policy=policy.default).walk())
        if index < 0 or index >= len(parts) or not (parts[index].get_filename() or parts[index].get("Content-ID")):
            raise HTTPException(404, "Allegato non trovato")
        part = parts[index]
        inline = part.get_content_type() in {"image/png", "image/jpeg", "image/gif", "image/webp"} or (
            preview and part.get_content_type() == "application/pdf")
        return Response(part.get_payload(decode=True) or b"", media_type=part.get_content_type() if inline else "application/octet-stream",
                        headers={"Content-Disposition": ("inline" if inline else "attachment") + "; filename*=UTF-8''" + quote(part.get_filename() or "immagine", safe=""),
                                 "X-Content-Type-Options": "nosniff"})

    @app.get("/api/messages/{message_id}/thread", dependencies=[Depends(auth)])
    def get_thread(message_id: str, load_images: bool = False, lazy: bool = False):
        message_or_404(message_id, metadata=True)
        messages = store.conversation(message_id, raw=not lazy, metadata=lazy)
        if lazy and messages:
            source = next((message for message in reversed(messages) if not message["sent"]), messages[-1])
            try:
                source.update(message_recipients(source["id"]))
            except HTTPException:
                pass
        for message in messages:
            if lazy:
                message["body_loaded"] = False
                continue
            mail = email.message_from_bytes(message.pop("raw"), policy=policy.default)
            message.update(render_html(mail, message["id"], load_images))
            message["attachments"] = [{"index": i, "name": part.get_filename(), "type": part.get_content_type()}
                                      for i, part in enumerate(mail.walk()) if part.get_filename()]
        # Reads serve only the server archive. Provider synchronization is
        # exclusively the background worker's job; opening mail never fetches
        # from Google or IMAP.
        return {"messages": messages, "sync": {}}

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
        schedules = features.schedules()
        return {"drafts": [{**json.loads(row["data"]), "id": row["id"], "updated": row["updated"],
                            "scheduled": schedules.get(row["id"])}
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
            store.execute("INSERT INTO drafts VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data,updated=excluded.updated",
                          (draft_id, data.model_dump_json(), time.time()))
        return {"id": draft_id}

    @app.delete("/api/drafts/{draft_id}", dependencies=[Depends(auth)])
    def delete_draft(draft_id: str):
        store.execute("DELETE FROM drafts WHERE id=?", (draft_id,))
        return {"ok": True}

    def deliver(draft_id):
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
            # A send that started can no longer be undone.
            store.execute("UPDATE scheduled SET error='Invio in corso' WHERE draft_id=?", (draft_id,))
        try:
            original = store.message(draft["reply_to_id"]) if draft.get("reply_to_id") else None
            if account["provider"] == "google":
                client = Gmail(store, account["id"])
                try:
                    result = client.send(account, draft, original)
                finally:
                    client.close()
                rfc_message_id, thread_id = result.get("rfc_message_id"), result.get("threadId")
            else:
                with engine.account_lock(account["id"]):
                    account = store.account(account["id"], private=True)
                    mail = send_mail(account, draft, original)
                    parsed = parse_message(mail.as_bytes(), account["id"], "Milo/Sent", "local", time.time_ns(),
                                           b"\\Seen", sent=True)
                    store.upsert_message(parsed)
                rfc_message_id, thread_id = mail["Message-ID"], parsed["thread_id"]
            # A second device may save a newer version during this explicit
            # send. Delete only the version that was actually submitted.
            store.execute("DELETE FROM drafts WHERE id=? AND data=?", (draft_id, saved_data))
            features.sent(draft_id, account["id"], draft, rfc_message_id, thread_id)
            return {"ok": True}
        except ValueError as exc:
            store.execute("UPDATE scheduled SET error=? WHERE draft_id=?", (str(exc), draft_id))
            raise HTTPException(422, str(exc)) from exc
        except Exception as exc:
            message = safe_error(exc) + " L'invio non viene ripetuto automaticamente; controlla la posta inviata prima di riprovare."
            store.execute("UPDATE scheduled SET error=? WHERE draft_id=?", (message, draft_id))
            raise HTTPException(502, message) from exc
        finally:
            with store.lock:
                sending.discard(draft_id)

    @app.post("/api/drafts/{draft_id}/send", dependencies=[Depends(auth)])
    def send(draft_id: str):
        live()
        return deliver(draft_id)

    @app.put("/api/drafts/{draft_id}/schedule", dependencies=[Depends(auth)])
    def schedule_draft(draft_id: str, data: ScheduleInput):
        live()
        try:
            return features.schedule(draft_id, data.send_at, data.followup_days)
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.delete("/api/drafts/{draft_id}/schedule", dependencies=[Depends(auth)])
    def unschedule_draft(draft_id: str):
        with store.lock:
            if draft_id in sending or not features.unschedule(draft_id):
                raise HTTPException(409, "Il messaggio è già in invio e non può essere annullato")
        return {"ok": True}

    @app.get("/api/todos", dependencies=[Depends(auth)])
    def todos():
        return {"todos": features.todos()}

    @app.patch("/api/todos/{todo_id}", dependencies=[Depends(auth)])
    def patch_todo(todo_id: str, data: TodoPatch):
        if not features.set_todo(todo_id, data.done):
            raise HTTPException(404, "Attività non trovata")
        return {"ok": True}

    @app.get("/api/senders/newsletters", dependencies=[Depends(auth)])
    def newsletter_senders():
        return {"senders": features.newsletter_senders()}

    @app.get("/api/screener", dependencies=[Depends(auth)])
    def screener_list():
        return {"senders": features.screening(), **features.screener()}

    @app.put("/api/settings/screener", dependencies=[Depends(auth)])
    def screener_settings(data: ScreenerSettings):
        return features.set_screener(data.enabled)

    @app.patch("/api/senders/{email}", dependencies=[Depends(auth)])
    def patch_sender(email: str, data: SenderPatch):
        patch = data.model_dump(exclude_unset=True)
        try:
            result = features.set_sender(email, **patch)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        wake_sync()
        return result

    @app.post("/api/senders/{email}/action", dependencies=[Depends(auth)])
    def sender_action(email: str, data: SenderAction):
        count = features.sender_action(email, data.action)
        wake_sync()
        return {"conversations": count}

    @app.post("/api/messages/{message_id}/unsubscribe", dependencies=[Depends(auth)])
    def unsubscribe(message_id: str):
        live()
        message = message_or_404(message_id, metadata=True)
        options = features.unsubscribe_options(store.message_headers(message_id))
        if not options:
            raise HTTPException(404, "Questo mittente non offre una disiscrizione automatica")
        try:
            if options["one_click"]:
                features.one_click(options["url"])
                method = "one-click"
            elif options["mailto"]:
                draft = features.mailto_draft(options["mailto"], message["account_id"])
                draft_id = uuid.uuid4().hex
                store.execute("INSERT INTO drafts VALUES(?,?,?)", (draft_id, json.dumps({**draft, "id": draft_id}), time.time()))
                deliver(draft_id)
                method = "email"
            else:
                features.mark_unsubscribed(message["sender_email"])
                return {"method": "link", "url": options["url"]}
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        except (RuntimeError, httpx.HTTPError) as exc:
            raise HTTPException(502, str(exc) if isinstance(exc, RuntimeError) else "Il mittente non risponde. Riprova più tardi.") from exc
        features.mark_unsubscribed(message["sender_email"])
        return {"method": method}

    @app.put("/api/settings/signatures", dependencies=[Depends(auth)])
    def settings_signatures(data: Signatures):
        accounts = {account["id"] for account in store.accounts()}
        value = {key: text for key, text in data.signatures.items() if key in accounts}
        store.set_setting("signatures", value)
        return {"signatures": value}

    @app.put("/api/settings/templates", dependencies=[Depends(auth)])
    def settings_templates(data: Templates):
        value = [template.model_dump() for template in data.templates]
        store.set_setting("templates", value)
        return {"templates": value}

    @app.post("/api/messages/{message_id}/suggestions", dependencies=[Depends(auth)])
    def suggestions(message_id: str):
        live()
        message_or_404(message_id)
        try:
            return ai.suggestions(message_id)
        except RuntimeError as exc:
            raise HTTPException(503, str(exc)) from exc

    @app.post("/api/ask", dependencies=[Depends(auth)])
    def ask(data: Question):
        live()
        try:
            return ai.ask(data.question)
        except RuntimeError as exc:
            raise HTTPException(503, str(exc)) from exc

    @app.delete("/api/accounts/{account_id}", dependencies=[Depends(auth)], status_code=202)
    def remove_account(account_id: str, background: BackgroundTasks):
        live()
        if not store.account(account_id):
            raise HTTPException(404, "Account non trovato")
        store.execute("UPDATE accounts SET removing=1,enabled=0 WHERE id=?", (account_id,))
        background.add_task(features.purge_account, account_id, stop_worker.is_set)
        return {"accepted": True}

    @app.get("/api/backup", dependencies=[Depends(auth)])
    def backup():
        return Response(json.dumps(features.export(), ensure_ascii=False), media_type="application/json",
                        headers={"Content-Disposition": "attachment; filename=milo-configurazione.json",
                                 "Cache-Control": "no-store"})

    @app.post("/api/backup/restore", dependencies=[Depends(auth)])
    async def restore(request: Request):
        body = await request.body()
        if len(body) > 200_000_000:
            raise HTTPException(413, "File troppo grande")
        try:
            data = json.loads(body)
            return await asyncio.to_thread(features.restore, data)
        except (ValueError, KeyError, TypeError) as exc:
            raise HTTPException(422, str(exc) if isinstance(exc, ValueError) else "File di configurazione non valido") from exc

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
