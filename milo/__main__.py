import argparse
import os
from pathlib import Path

import uvicorn

from .app import create_app


def main():
    parser = argparse.ArgumentParser(description="Milo — email, with room to think")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8025, type=int)
    parser.add_argument("--data", type=Path)
    parser.add_argument("--demo", action="store_true", help="Isolated demo with fictional messages")
    parser.add_argument("--secure-cookies", action="store_true", help="Required behind an HTTPS proxy")
    args = parser.parse_args()
    root = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share")))
    data = args.data or root / ("milo-demo" if args.demo else "milo")
    app = create_app(data, args.demo, os.environ.get("MILO_OLLAMA_URL", "http://127.0.0.1:11434"), args.secure_cookies)
    print(f"\nMilo → http://{args.host}:{args.port}", flush=True)
    if not args.demo and app.state.store.bootstrap:
        print(f"Codice di inizializzazione (solo primo avvio): {app.state.store.bootstrap}", flush=True)
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
