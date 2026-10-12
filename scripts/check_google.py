#!/usr/bin/env python3
"""Owner-authorized, read-only Gmail diagnosis. Never print tokens or mail data."""
import json
import sys
from pathlib import Path

from milo.google import GMAIL_API, Gmail
from milo.store import Store


def main():
    root = Path(__file__).resolve().parent.parent
    directory = Path.home() / "Library/Application Support/Milo" if sys.platform == "darwin" else root / ".data/live"
    if not (directory / "mail.sqlite").exists():
        raise SystemExit("Milo archive not found")
    store = Store(directory)
    try:
        for index, account in enumerate(store.accounts()):
            if account["provider"] != "google":
                continue
            client = Gmail(store, account["id"])
            try:
                for endpoint in ("profile", "messages"):
                    response = client.session.get(GMAIL_API + endpoint,
                        params={"maxResults": 1} if endpoint == "messages" else None, timeout=20)
                    error = response.json().get("error", {})
                    reasons = [item.get("reason") for field in ("errors", "details")
                               for item in error.get(field, []) if isinstance(item, dict)]
                    # Only fixed endpoint labels, HTTP codes and structured reasons.
                    print(json.dumps({"account": index + 1, "endpoint": endpoint,
                                      "http": response.status_code, "reasons": reasons}))
            except Exception as error:
                print(json.dumps({"account": index + 1, "error_type": type(error).__name__}))
            finally:
                client.close()
    finally:
        store.close()


if __name__ == "__main__":
    main()
