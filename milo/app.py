import asyncio
import email
import json
import time
import uuid
from contextlib import asynccontextmanager
from email import policy
from pathlib import Path
from urllib.parse import quote, urlsplit

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .ai import AI
from .demo import seed_demo
from .mail import SyncEngine, parse_message, safe_error, send_mail
from .models import AccountInput, AISettings, DraftInput, Login, MessagePatch, RuleInput
from .store import Store


def create_app(directory: Path, demo=False, ollama_url="http://127.0.0.1:11434", secure_cookies=False):
    store = Store(directory)
    ai = AI(store, ollama_url)
    engine = SyncEngine(store, ai)
    sync_lock = asyncio.Lock()
    stop_worker = asyncio.Event()
    attempts = {}
    sending = set()
    if demo:
        seed_demo(store)

    async def sync():
        async with sync_lock:
            return await asyncio.to_thread(engine.sync_all)

    async def worker():
        while not stop_worker.is_set():
            if not demo:
                await sync()
            try:
                await asyncio.wait_for(stop_worker.wait(), timeout=60)
            except TimeoutError:
                continue

    @asynccontextmanager
    async def lifespan(app):
        task = asyncio.create_task(worker())
        yield
        # Do not close SQLite while a sync thread is still using it.
        stop_worker.set()
        await task
        store.close()

    app = FastAPI(title="Milo", version="0.1.0", lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.store, app.state.engine, app.state.ai = store, engine, ai

    @app.middleware("http")
    async def guard(request: Request, call_next):
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin")
            if origin and urlsplit(origin).netloc != request.headers.get("host"):
                return Response(status_code=403)
            if request.headers.get("sec-fetch-site") == "cross-site":
                return Response(status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    def auth(request: Request):
        if not demo and not store.valid_session(request.cookies.get("milo_session")):
            raise HTTPException(401, "Accedi a Milo")

    def live():
        if demo:
            raise HTTPException(400, "Questa è una demo. Avvia Milo senza --demo per collegare account reali.")

    def message_or_404(message_id, raw=False):
        message = store.message(message_id, raw)
        if not message:
            raise HTTPException(404, "Email non trovata")
        return message

    @app.get("/api/status")
    def status(request: Request):
        authenticated = demo or store.valid_session(request.cookies.get("milo_session"))
        return {"service": "milo", "demo": demo, "initialized": bool(store.setting("password")), "authenticated": authenticated,
                "version": "0.1.0"}

    def issue_session(response):
        response.set_cookie("milo_session", store.new_session(), httponly=True, secure=secure_cookies,
                            samesite="strict", max_age=30 * 86400)
        return {"ok": True}

    @app.post("/api/setup")
    def setup(data: Login, response: Response):
        live()
        if not store.setup(data.password, data.bootstrap):
            raise HTTPException(403, "Codice di inizializzazione non valido o Milo già configurato")
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

    @app.get("/api/state", dependencies=[Depends(auth)])
    def state():
        inbox = store.rows("SELECT COUNT(*) AS count,SUM(read=0) AS unread FROM messages WHERE archived=0 AND sent=0 "
                           "AND (snoozed_until IS NULL OR snoozed_until<=?)", (time.time(),))[0]
        return {"accounts": store.accounts(), "ai": store.setting("ai"), "ai_error": store.setting("ai_error"),
                "rules": store.rules(), "pending": store.rows("SELECT kind,error,COUNT(*) AS count FROM outbox GROUP BY kind,error"),
                "counts": {"inbox": inbox["count"], "unread": inbox["unread"] or 0,
                           "starred": store.rows("SELECT COUNT(*) AS count FROM messages WHERE starred=1")[0]["count"],
                           "drafts": store.rows("SELECT COUNT(*) AS count FROM drafts")[0]["count"],
                           "snoozed": store.rows("SELECT COUNT(*) AS count FROM messages WHERE snoozed_until>?",
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

    @app.post("/api/sync", dependencies=[Depends(auth)])
    async def sync_now():
        if demo:
            return {"results": [], "demo": True}
        return {"results": await sync()}

    @app.get("/api/messages", dependencies=[Depends(auth)])
    def messages(view="inbox", category: str | None = None, account: str | None = None, search=""):
        return {"messages": store.messages(view, category, account, search[:300])}

    @app.get("/api/messages/{message_id}", dependencies=[Depends(auth)])
    def get_message(message_id: str):
        message = message_or_404(message_id)
        raw = store.message(message_id, raw=True)["raw"]
        mail = email.message_from_bytes(raw, policy=policy.default)
        message["attachments"] = [{"index": i, "name": part.get_filename() or "allegato",
                                    "type": part.get_content_type()}
                                   for i, part in enumerate(mail.walk()) if part.get_filename()]
        return message

    @app.get("/api/messages/{message_id}/attachments/{index}", dependencies=[Depends(auth)])
    def attachment(message_id: str, index: int):
        message = message_or_404(message_id, raw=True)
        parts = list(email.message_from_bytes(message["raw"], policy=policy.default).walk())
        if index < 0 or index >= len(parts) or not parts[index].get_filename():
            raise HTTPException(404, "Allegato non trovato")
        part = parts[index]
        return Response(part.get_payload(decode=True) or b"", media_type="application/octet-stream",
                        headers={"Content-Disposition": "attachment; filename*=UTF-8''" + quote(part.get_filename(), safe="")})

    @app.patch("/api/messages/{message_id}", dependencies=[Depends(auth)])
    def patch_message(message_id: str, data: MessagePatch):
        message = message_or_404(message_id)
        with engine.account_lock(message["account_id"]):
            patch = data.model_dump(exclude_unset=True)
            if any(v is None for k, v in patch.items() if k != "snoozed_until"):
                raise HTTPException(422, "Stato non valido")
            store.patch_message(message_id, patch)
            if demo:
                store.execute("DELETE FROM outbox WHERE message_id=?", (message_id,))
        return store.message(message_id)

    @app.put("/api/settings/ai", dependencies=[Depends(auth)])
    def settings_ai(data: AISettings):
        store.set_setting("ai", data.model_dump())
        return data

    @app.post("/api/messages/{message_id}/analyze", dependencies=[Depends(auth)])
    def analyze(message_id: str):
        live()
        message_or_404(message_id)
        try:
            return ai.analyze(message_id)
        except RuntimeError as exc:
            raise HTTPException(503, str(exc)) from exc

    @app.post("/api/recap", dependencies=[Depends(auth)])
    def recap():
        live()
        try:
            return ai.recap()
        except RuntimeError as exc:
            raise HTTPException(503, str(exc)) from exc

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
            draft = json.loads(rows[0]["data"])
            account = next((a for a in store.accounts(private=True) if a["id"] == draft["account_id"]), None)
            if not account:
                raise HTTPException(404, "Account non trovato")
            sending.add(draft_id)
        try:
            original = store.message(draft["reply_to_id"]) if draft.get("reply_to_id") else None
            mail = send_mail(account, draft, original)
            store.upsert_message(parse_message(mail.as_bytes(), account["id"], "Milo/Sent", "local", time.time_ns(),
                                               b"\\Seen", sent=True))
            store.execute("DELETE FROM drafts WHERE id=?", (draft_id,))
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
