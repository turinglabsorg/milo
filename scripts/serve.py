#!/usr/bin/env python3
"""Production entrypoint supervised by the owner's permanent Grog site."""
import os
import sys
from pathlib import Path

from milo.__main__ import main

root = Path(__file__).resolve().parent.parent
origin = os.environ.get("MILO_PUBLIC_URL", "https://milo.grooooog.space")
legacy = root / ".data/live"
archive = Path.home() / "Library/Application Support/Milo" if sys.platform == "darwin" else legacy
if (legacy / "mail.sqlite").exists():
    archive = legacy
data = os.environ.get("MILO_DATA", str(archive))
sys.argv = ["milo", "--host", "127.0.0.1", "--port", os.environ.get("PORT", "8025"),
            "--data", data, "--public-url", origin, "--secure-cookies", "--quiet-bootstrap"]
main()
