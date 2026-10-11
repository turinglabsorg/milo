"""Opt-in live check: sends a fictional message, never the user's mail, to Ollama."""
import json
import os
import tempfile
from email.message import EmailMessage
from pathlib import Path

from milo.ai import AI
from milo.mail import parse_message
from milo.store import Store

with tempfile.TemporaryDirectory(prefix="milo-ai-check-") as directory:
    store = Store(Path(directory))
    account = store.add_account({"name": "Test", "email": "test@example.com", "username": "test",
        "password": "fake", "imap_host": "example.invalid", "imap_port": 993, "smtp_host": "example.invalid",
        "smtp_port": 465, "smtp_security": "tls", "color": "#afa4ff"})
    mail = EmailMessage()
    mail["From"] = "Giulia <giulia@example.com>"
    mail["To"] = "test@example.com"
    mail["Subject"] = "Revisione del progetto"
    mail.set_content("Ciao, puoi rivedere il documento entro domani? Mi serve il tuo feedback prima della riunione. Grazie!")
    message_id = store.upsert_message(parse_message(mail.as_bytes(), account, "INBOX", "1", 1))
    store.set_setting("ai", {"model": "mistral-large-4:cloud", "automatic": False, "cloud_consent": True})
    ai = AI(store, os.environ.get("MILO_OLLAMA_URL", "http://127.0.0.1:11434"))
    analysis = ai.analyze(message_id)
    print(json.dumps({"check": "analysis", "model": analysis["model"], "category": analysis["category"],
                      "summary": analysis["summary"]}, ensure_ascii=False), flush=True)
    recap = ai.recap()
    assert recap["message_ids"] == [message_id]
    print(json.dumps({"check": "recap", "priorities": len(recap["priorities"])}), flush=True)
    reply = ai.reply(message_id)
    assert reply["body"]
    print(json.dumps({"check": "reply", "characters": len(reply["body"])}), flush=True)
    store.close()
