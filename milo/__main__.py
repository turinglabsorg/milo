import argparse
import copy
import os
from pathlib import Path

import uvicorn

from .app import create_app
from .private import private_config


class PrivateAccessFormatter(uvicorn.logging.AccessFormatter):
    """Authorization codes and other query parameters must never enter logs."""

    def formatMessage(self, record):
        record = copy.copy(record)
        args = list(record.args)
        if len(args) == 5:
            args[2] = args[2].split("?", 1)[0]
            record.args = tuple(args)
        return super().formatMessage(record)


def main():
    parser = argparse.ArgumentParser(description="Milo — email, with room to think")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8025, type=int)
    parser.add_argument("--data", type=Path)
    parser.add_argument("--demo", action="store_true", help="Isolated demo with fictional messages")
    parser.add_argument("--secure-cookies", action="store_true", help="Required behind an HTTPS proxy")
    parser.add_argument("--quiet-bootstrap", action="store_true", help="Keep first-start codes out of service logs")
    parser.add_argument("--public-url", default=os.environ.get("MILO_PUBLIC_URL"), help="Stable HTTPS origin for Google OAuth")
    parser.add_argument("--google-client", type=Path, default=os.environ.get("MILO_GOOGLE_CLIENT"), help="Google web client JSON")
    parser.add_argument("--private-config", type=Path, help="Owner-only Tailscale access configuration (0600)")
    parser.add_argument("--proxy-peer", action="append", default=[], help="Explicit loopback-published Docker gateway")
    args = parser.parse_args()
    config = private_config(args.private_config) if args.private_config else None
    container = os.environ.get("MILO_CONTAINER") == "1" and Path("/.dockerenv").exists()
    if args.proxy_peer and not container:
        parser.error("Additional proxy peers are available only in the loopback-published Docker deployment")
    if config and args.host not in {"127.0.0.1", "::1"} and not (container and args.proxy_peer):
        parser.error("A Tailscale-authenticated backend must listen only on loopback")
    if config and (not args.secure_cookies or args.demo):
        parser.error("Private production access requires secure cookies and a real archive")
    root = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share")))
    data = args.data or root / ("milo-demo" if args.demo else "milo")
    public_url = args.public_url or f"http://127.0.0.1:{args.port}"
    if public_url.startswith("https://") and not args.secure_cookies:
        parser.error("An HTTPS public URL requires --secure-cookies")
    app = create_app(data, args.demo, os.environ.get("MILO_OLLAMA_URL", "http://127.0.0.1:11434"),
                     args.secure_cookies, public_url, args.google_client,
                     config["url"] if config else None, config["owners"] if config else None, args.proxy_peer)
    print(f"\nMilo → http://{args.host}:{args.port}", flush=True)
    if not args.demo and app.state.store.bootstrap and not args.quiet_bootstrap:
        print("Apri Milo dall'app installata per scegliere la tua password.", flush=True)
    logging = copy.deepcopy(uvicorn.config.LOGGING_CONFIG)
    logging["formatters"]["access"]["()"] = PrivateAccessFormatter
    uvicorn.run(app, host=args.host, port=args.port, log_config=logging, proxy_headers=not bool(config))


if __name__ == "__main__":
    main()
