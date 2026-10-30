#!/usr/bin/env python3
"""Grog serves the public landing. A separate loopback child owns the archive."""
import asyncio
import copy
import os
import subprocess
import sys
import urllib.request
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn

from milo.__main__ import PrivateAccessFormatter
from milo.private import private_config
from milo.public import create_public_app

ROOT = Path(__file__).resolve().parent.parent


def main():
    legacy = ROOT / ".data/live"
    container = os.environ.get("MILO_CONTAINER") == "1"
    if container and not Path("/.dockerenv").exists():
        raise SystemExit("Container mode requires the Docker deployment")
    archive = Path.home() / "Library/Application Support/Milo" if sys.platform == "darwin" else legacy
    if (legacy / "mail.sqlite").exists():
        archive = legacy
    archive = Path(os.environ.get("MILO_DATA", str(archive)))
    config_path = archive / "private-server.json"
    config = private_config(config_path) if config_path.exists() else None
    if container and not config:
        raise SystemExit("The container requires an existing owner-protected archive")
    peers = ["--proxy-peer", os.environ["MILO_PROXY_PEER"]] if container else []

    @asynccontextmanager
    async def lifespan(app):
        process = None
        monitor = None
        if config:
            process = subprocess.Popen([sys.executable, "-m", "milo", "--host", "0.0.0.0" if container else "127.0.0.1", "--port", "8029",
                                        "--data", str(archive), "--public-url",
                                        os.environ.get("MILO_PUBLIC_URL", "https://milo.grooooog.space"),
                                        "--secure-cookies", "--quiet-bootstrap", "--private-config", str(config_path), *peers],
                                       cwd=ROOT)

            async def watch():
                while process.poll() is None:
                    await asyncio.sleep(1)
                server.should_exit = True

            monitor = asyncio.create_task(watch())
        try:
            yield
        finally:
            if monitor:
                monitor.cancel()
                await asyncio.gather(monitor, return_exceptions=True)
            if process and process.poll() is None:
                process.terminate()
                await asyncio.to_thread(process.wait)

    def opened(token):
        try:
            urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:8029/internal/opened/{token}", method="POST"),
                                   timeout=5).close()
        except OSError:
            pass

    app = create_public_app(config["url"] if config else None, lifespan, opened if config else None)
    logging = copy.deepcopy(uvicorn.config.LOGGING_CONFIG)
    logging["formatters"]["access"]["()"] = PrivateAccessFormatter
    server = uvicorn.Server(uvicorn.Config(app, host="0.0.0.0" if container else "127.0.0.1", port=int(os.environ.get("PORT", "8025")),
                                          log_config=logging, proxy_headers=False))
    server.run()


if __name__ == "__main__":
    main()
