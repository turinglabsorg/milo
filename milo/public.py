"""Public landing and a fixed OAuth relay. This app never opens the mail archive."""
from pathlib import Path
from urllib.parse import urlencode, urlsplit

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, RedirectResponse, Response


def create_public_app(private_url=None, lifespan=None):
    if private_url:
        url = urlsplit(private_url)
        if (url.scheme != "https" or not url.hostname or not url.hostname.endswith(".ts.net")
                or url.username or url.password or url.query or url.fragment or url.path not in {"", "/"}):
            raise ValueError("OAuth relay requires a fixed private Tailscale HTTPS origin")
        private_url = private_url.rstrip("/")
    app = FastAPI(title="Milo", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    web = Path(__file__).resolve().parent.parent / "web"
    if not web.exists():
        web = Path(__file__).resolve().parent / "web"

    @app.middleware("http")
    async def headers(request, call_next):
        response = await call_next(request)
        response.headers.update({"Cache-Control": "no-store", "Referrer-Policy": "no-referrer",
                                 "X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY",
                                 "X-Milo-Surface": "public",
                                 "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; "
                                 "img-src 'self'; font-src 'self'; script-src 'self'; "
                                 "base-uri 'none'; form-action 'none'; frame-ancestors 'none'"})
        return response

    @app.get("/")
    def index():
        return FileResponse(web / "landing.html")

    @app.get("/assets/milo.svg")
    def icon():
        return FileResponse(web / "icon.svg")

    @app.get("/assets/Geist.woff2")
    def font():
        return FileResponse(web / "fonts/Geist.woff2")

    @app.get("/sw.js")
    def retire_old_shell():
        # Previously installed clients must stop caching the public mail UI.
        return Response("self.addEventListener('install',()=>self.skipWaiting());"
                        "self.addEventListener('activate',e=>e.waitUntil(Promise.all(["
                        "caches.keys().then(keys=>Promise.all(keys.filter(k=>k.startsWith('milo-')).map(k=>caches.delete(k)))),"
                        "self.registration.unregister()])));",
                        media_type="application/javascript", headers={"Service-Worker-Allowed": "/"})

    @app.get("/api/oauth/google/callback")
    def callback(state: str = Query('', max_length=512), code: str = Query('', max_length=8192),
                 error: str = Query('', max_length=256)):
        if not private_url or not state or not (code or error):
            return RedirectResponse("/", 303)
        params = {"state": state, **({"error": error} if error else {"code": code})}
        return RedirectResponse(private_url + "/api/oauth/google/callback?" + urlencode(params), 303)

    @app.api_route("/{path:path}", methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
    def unavailable(path):
        return Response(status_code=404)

    return app
