import base64
import json
import time

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
from test_features import add, setup_account

from milo.push import Push

TOKEN = "a" * 64


def unb64(value):
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def configure(client, tmp_path, statuses=None):
    key = ec.generate_private_key(ec.SECP256R1())
    path = tmp_path / "apns.p8"
    path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                       serialization.NoEncryption()))
    sent = []

    def transport(url, headers, payload):
        sent.append((url, headers, payload))
        return (statuses or {}).get(url.rsplit("/", 1)[1], 200)

    push = client.app.state.push
    push.key_file, push.key_id, push.team_id, push.topic, push.transport = path, "KEY1234567", "TEAM123456", \
        "io.meaningtech.milo", transport
    return push, key, sent


def test_devices_register_and_new_people_mail_notifies(logged_in, account_data, tmp_path):
    store, account_id = setup_account(logged_in, account_data)
    push, key, sent = configure(logged_in, tmp_path)
    assert logged_in.post("/api/devices", json={"token": TOKEN, "environment": "production"}).json() == {"ok": True, "push": True}
    assert logged_in.post("/api/devices", json={"token": "not-hex" * 6}).status_code == 422
    add(store, account_id, 1, subject="Pranzo domani?", sender="Anna <anna@example.com>", when=time.time())
    logged_in.app.state.feature_tick(False)
    assert len(sent) == 1
    url, headers, payload = sent[0]
    assert url == "https://api.push.apple.com/3/device/" + TOKEN
    assert headers["apns-topic"] == "io.meaningtech.milo" and headers["apns-push-type"] == "alert"
    assert payload["aps"]["alert"] == {"title": "Anna", "body": "Pranzo domani?"}
    header, claims, signature = headers["authorization"].split()[1].split(".")
    assert json.loads(unb64(header)) == {"alg": "ES256", "kid": "KEY1234567"}
    assert json.loads(unb64(claims))["iss"] == "TEAM123456"
    raw = unb64(signature)
    key.public_key().verify(encode_dss_signature(int.from_bytes(raw[:32], "big"), int.from_bytes(raw[32:], "big")),
                            f"{header}.{claims}".encode(), ec.ECDSA(hashes.SHA256()))


def test_backfill_newsletters_blocked_and_screened_senders_stay_quiet(logged_in, account_data, tmp_path):
    store, account_id = setup_account(logged_in, account_data)
    push, _, sent = configure(logged_in, tmp_path)
    push.register(TOKEN, "production")
    add(store, account_id, 1, msg_id="<old@x>", when=time.time() - 86400)
    add(store, account_id, 2, msg_id="<news@x>", sender="News <news@brand.example>", category="newsletters", when=time.time())
    logged_in.patch("/api/senders/spam@example.com", json={"status": "blocked"})
    add(store, account_id, 3, msg_id="<spam@x>", sender="Spam <spam@example.com>", when=time.time())
    logged_in.app.state.feature_tick(False)
    assert sent == []
    logged_in.patch("/api/senders/news@brand.example", json={"vip": True})
    add(store, account_id, 4, msg_id="<news2@x>", sender="News <news@brand.example>", category="newsletters", when=time.time())
    logged_in.app.state.feature_tick(False)
    assert len(sent) == 1


def test_many_new_mails_are_grouped_and_dead_tokens_removed(logged_in, account_data, tmp_path):
    store, account_id = setup_account(logged_in, account_data)
    dead = "b" * 64
    push, _, sent = configure(logged_in, tmp_path, statuses={dead: 410})
    push.register(TOKEN, "sandbox")
    push.register(dead, "production")
    for uid in range(5):
        add(store, account_id, uid, msg_id=f"<m{uid}@x>", subject=f"Email {uid}", sender=f"P{uid} <p{uid}@example.com>",
            when=time.time())
    logged_in.app.state.feature_tick(False)
    live = [payload for url, _, payload in sent if url.endswith(TOKEN)]
    assert len(live) == 4 and live[-1]["aps"]["alert"]["body"] == "Altre 2 email nuove"
    assert sent[0][0].startswith("https://api.sandbox.push.apple.com") or any("sandbox" in url for url, _, _ in sent)
    assert [row["token"] for row in store.rows("SELECT token FROM devices")] == [TOKEN]


def test_unconfigured_push_sends_nothing(logged_in, account_data):
    store, account_id = setup_account(logged_in, account_data)
    logged_in.app.state.push.register(TOKEN, "production")
    add(store, account_id, 1, when=time.time())
    logged_in.app.state.feature_tick(False)
    assert logged_in.post("/api/devices", json={"token": TOKEN}).json()["push"] is False
