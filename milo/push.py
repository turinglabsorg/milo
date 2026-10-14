"""Apple Push Notifications for new mail.

The APNs key is a mode-0600 file in the archive; it is read here and never logged.
Only recent mail from people or VIP senders notifies, so backfills never flood the phone.
"""
import base64
import json
import os
import threading
import time
from pathlib import Path

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

RECENT = 3600
HOSTS = {"production": "https://api.push.apple.com", "sandbox": "https://api.sandbox.push.apple.com"}


def b64(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


class Push:
    def __init__(self, store, key_file=None, key_id=None, team_id=None, topic=None, transport=None):
        self.store = store
        self.key_file = Path(key_file) if key_file else None
        self.key_id, self.team_id, self.topic = key_id, team_id, topic
        self.transport = transport
        self._token = (0, "")
        self._queue = []
        self._lock = threading.Lock()

    @classmethod
    def from_environment(cls, store):
        archive = store.directory
        return cls(store, os.environ.get("MILO_APNS_KEY_FILE") or (archive / "apns.p8"),
                   os.environ.get("MILO_APNS_KEY_ID"), os.environ.get("MILO_APNS_TEAM_ID"),
                   os.environ.get("MILO_APNS_TOPIC", "io.meaningtech.milo"))

    @property
    def configured(self):
        return bool(self.key_id and self.team_id and self.topic and self.key_file and self.key_file.exists())

    # Devices

    def register(self, token, environment):
        if not token or len(token) > 200 or not all(c in "0123456789abcdefABCDEF" for c in token):
            raise ValueError("Token del dispositivo non valido")
        if environment not in HOSTS:
            raise ValueError("Ambiente non valido")
        self.store.execute("INSERT INTO devices VALUES(?,?,?,?) ON CONFLICT(token) DO UPDATE SET "
                           "environment=excluded.environment,last_seen=excluded.last_seen",
                           (token.lower(), environment, time.time(), time.time()))

    def unregister(self, token):
        self.store.execute("DELETE FROM devices WHERE token=?", (token.lower(),))

    # New mail

    def message_added(self, data):
        """Called by the store after a new message row; cheap, never blocks the sync writer."""
        if data.get("sent") or data.get("hidden") or data.get("archived"):
            return
        if (data.get("date") or 0) < time.time() - RECENT:
            return
        with self._lock:
            self._queue.append({key: data.get(key) for key in
                                ("id", "account_id", "thread_id", "sender", "sender_email", "subject", "category")})

    def eligible(self, items):
        senders = {row["email"]: row for row in self.store.rows("SELECT email,status,vip FROM senders")}
        screener = self.store.setting("screener") or {}
        result = []
        for item in items:
            email = (item.get("sender_email") or "").lower()
            sender = senders.get(email) or {}
            if sender.get("status") == "blocked":
                continue
            if screener.get("enabled") and sender.get("status") != "approved" and not sender.get("vip"):
                continue
            if item.get("category") == "people" or sender.get("vip"):
                result.append(item)
        return result

    def flush(self):
        with self._lock:
            items, self._queue = self._queue, []
        items = self.eligible(items)
        if not items or not self.configured:
            return 0
        devices = self.store.rows("SELECT token,environment FROM devices")
        if not devices:
            return 0
        payloads = [self.payload(item) for item in items[:3]]
        if len(items) > 3:
            payloads.append({"aps": {"alert": {"title": "Milo", "body": f"Altre {len(items) - 3} email nuove"},
                                     "sound": "default"}})
        sent = 0
        for device in devices:
            for payload in payloads:
                status = self.send(device["token"], device["environment"], payload)
                if status == 200:
                    sent += 1
                elif status == 410 or status == 400:
                    # Unregistered or bad token: the app was removed or reinstalled.
                    self.unregister(device["token"])
                    break
        return sent

    @staticmethod
    def payload(item):
        return {"aps": {"alert": {"title": item.get("sender") or item.get("sender_email") or "Nuova email",
                                  "body": item.get("subject") or "(senza oggetto)"},
                        "sound": "default", "thread-id": f"{item.get('account_id')}:{item.get('thread_id') or item.get('id')}"},
                "message_id": item.get("id"), "account_id": item.get("account_id"), "thread_id": item.get("thread_id")}

    # APNs transport

    def token(self):
        """Provider token, reused for 50 minutes (APNs rejects refreshing more than every 20)."""
        issued, value = self._token
        if time.time() - issued < 3000:
            return value
        key = serialization.load_pem_private_key(self.key_file.read_bytes(), password=None)
        header = b64(json.dumps({"alg": "ES256", "kid": self.key_id}).encode())
        claims = b64(json.dumps({"iss": self.team_id, "iat": int(time.time())}).encode())
        r, s = decode_dss_signature(key.sign(f"{header}.{claims}".encode(), ec.ECDSA(hashes.SHA256())))
        signature = b64(r.to_bytes(32, "big") + s.to_bytes(32, "big"))
        self._token = (time.time(), f"{header}.{claims}.{signature}")
        return self._token[1]

    def send(self, device_token, environment, payload):
        headers = {"authorization": "bearer " + self.token(), "apns-topic": self.topic,
                   "apns-push-type": "alert", "apns-priority": "10"}
        url = f"{HOSTS[environment]}/3/device/{device_token}"
        try:
            if self.transport:
                return self.transport(url, headers, payload)
            with httpx.Client(http2=True, timeout=15) as client:
                return client.post(url, headers=headers, json=payload).status_code
        except httpx.HTTPError:
            return 0
