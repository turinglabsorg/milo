"""Validate the owner's local deployment configuration, never publish its values."""
import json
import os
from pathlib import Path
from urllib.parse import urlsplit


def private_config(path: Path):
    if path.is_symlink() or path.stat().st_uid != os.getuid() or path.stat().st_mode & 0o077:
        raise ValueError("Private configuration must belong to this user and have mode 0600")
    config = json.loads(path.read_text())
    url = urlsplit(config["url"])
    if (url.scheme != "https" or not url.hostname or not url.hostname.endswith(".ts.net")
            or url.username or url.password or url.query or url.fragment or url.path not in {"", "/"}
            or url.port != 8443):
        raise ValueError("Private Milo requires a Tailscale HTTPS origin on port 8443")
    owners = config.get("owners")
    if not isinstance(owners, list) or not owners or any(not isinstance(owner, str) or not owner for owner in owners):
        raise ValueError("Private Milo requires an explicit owner allowlist")
    return {"url": config["url"].rstrip("/"), "owners": owners}
