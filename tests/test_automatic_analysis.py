import time
from email import message_from_bytes, policy

import pytest
from test_mail import FakeIMAP, raw_mail

from milo.ai import AI
from milo.mail import SyncEngine, parse_message


def enable(store):
    store.set_setting("ai", {**store.setting("ai"), "automatic": True})


def add(store, account_id, uid, date, **flags):
    message = parse_message(raw_mail(msg_id=f"<auto-{uid}@example.com>"), account_id, "INBOX", "1", uid)
    return store.upsert_message({**message, "date": date, **flags})


def recording_ai(store, monkeypatch):
    ai = AI(store)
    calls = []

    def chat(prompt, schema):
        calls.append(prompt)
        return {"summary": "New mail", "category": "people", "priority": "normal", "action_items": []}

    monkeypatch.setattr(ai, "chat", chat)
    return ai, calls


def test_only_future_incoming_mail_is_automatically_analyzed(store, account_data, monkeypatch):
    account_id = store.add_account(account_data)
    existing = add(store, account_id, 1, time.time() + 3600)
    ai, calls = recording_ai(store, monkeypatch)
    engine = SyncEngine(store, ai)
    enable(store)
    since = store.setting("ai_automatic_boundary")["since"]
    old_backfill = add(store, account_id, 2, since - 86400)
    at_boundary = add(store, account_id, 3, since)
    incoming = add(store, account_id, 4, since + 1)
    ignored = [add(store, account_id, uid, since + 2, **flags) for uid, flags in [
        (5, {"sent": 1}), (6, {"hidden": 1}), (7, {"trashed": 1})]]

    engine.analyze_pending(account_id)
    engine.analyze_pending(account_id)

    assert len(calls) == 1
    assert store.message(incoming)["analysis"]["summary"] == "New mail"
    assert all(store.message(message_id)["analysis"] is None
               for message_id in [existing, old_backfill, at_boundary, *ignored])


def test_legacy_automatic_setting_starts_from_now(store, account_data, monkeypatch):
    account_id = store.add_account(account_data)
    existing = add(store, account_id, 1, time.time() + 3600)
    enable(store)
    ai, calls = recording_ai(store, monkeypatch)
    engine = SyncEngine(store, ai)
    engine.analyze_pending(account_id)
    assert calls == []
    assert store.message(existing)["analysis"] is None


def test_boundary_survives_restart_and_keeps_future_pending_mail(store, account_data, monkeypatch):
    account_id = store.add_account(account_data)
    ai, calls = recording_ai(store, monkeypatch)
    SyncEngine(store, ai)
    enable(store)
    boundary = store.setting("ai_automatic_boundary")
    incoming = add(store, account_id, 1, boundary["since"] + 1)

    restarted = SyncEngine(store, ai)
    assert store.setting("ai_automatic_boundary") == boundary
    restarted.analyze_pending(account_id)
    assert len(calls) == 1
    assert store.message(incoming)["analysis"] is not None


def test_disabling_automatic_analysis_stops_the_current_batch(store, account_data, monkeypatch):
    account_id = store.add_account(account_data)
    ai, calls = recording_ai(store, monkeypatch)
    engine = SyncEngine(store, ai)
    enable(store)
    since = store.setting("ai_automatic_boundary")["since"]
    for uid in range(1, 4):
        add(store, account_id, uid, since + uid)

    def disable_after_first(message_id, analysis):
        store.set_setting("ai", {**store.setting("ai"), "automatic": False})

    ai.on_analysis = disable_after_first
    engine.analyze_pending(account_id)
    assert len(calls) == 1
    assert store.rows("SELECT COUNT(analysis) AS count FROM messages")[0]["count"] == 1


def test_resetting_the_boundary_stops_the_old_batch(store, account_data, monkeypatch):
    account_id = store.add_account(account_data)
    ai, calls = recording_ai(store, monkeypatch)
    engine = SyncEngine(store, ai)
    enable(store)
    since = store.setting("ai_automatic_boundary")["since"]
    for uid in range(1, 4):
        add(store, account_id, uid, since + uid)
    ai.on_analysis = lambda *_: engine.reset_automatic_analysis()
    engine.analyze_pending(account_id)
    assert len(calls) == 1


def test_first_sync_imports_history_without_analyzing_it(store, account_data, monkeypatch):
    account_id = store.add_account(account_data)
    remote = FakeIMAP()
    monkeypatch.setattr("milo.mail.connect", lambda _: remote)
    ai, calls = recording_ai(store, monkeypatch)
    engine = SyncEngine(store, ai)
    enable(store)
    assert engine.sync_account(store.account(account_id))["ok"]
    assert len(store.messages()) == 1
    assert calls == []


def test_enabling_via_api_resets_boundary_but_other_settings_keep_it(logged_in, account_data, monkeypatch):
    client = logged_in
    store, engine = client.app.state.store, client.app.state.engine
    monkeypatch.setattr(engine, "sync_all", lambda: [])
    monkeypatch.setattr(client.app.state.recaps, "refresh", lambda: None)
    account_id = store.add_account(account_data)
    existing = add(store, account_id, 1, time.time() + 3600)
    settings = {"model": "local-model", "automatic": True, "cloud_consent": False}
    assert client.put("/api/settings/ai", json=settings).status_code == 200
    boundary = store.setting("ai_automatic_boundary")
    assert boundary["after_seq"] == store.rows("SELECT seq FROM messages WHERE id=?", (existing,))[0]["seq"]

    settings["model"] = "another-local-model"
    assert client.put("/api/settings/ai", json=settings).status_code == 200
    assert store.setting("ai_automatic_boundary") == boundary

    assert client.put("/api/settings/ai", json={**settings, "automatic": False}).status_code == 200
    paused_mail = add(store, account_id, 2, time.time() + 3600)
    assert client.put("/api/settings/ai", json=settings).status_code == 200
    resumed = store.setting("ai_automatic_boundary")
    assert resumed["after_seq"] > boundary["after_seq"]
    assert resumed["since"] >= boundary["since"]

    ai, calls = recording_ai(store, monkeypatch)
    engine.ai = ai
    engine.analyze_pending(account_id)
    assert calls == []
    assert store.message(paused_mail)["analysis"] is None


def test_manual_analysis_still_accepts_historical_mail(store, account_data, monkeypatch):
    account_id = store.add_account(account_data)
    historic = add(store, account_id, 1, time.time() - 86400 * 365)
    ai, calls = recording_ai(store, monkeypatch)
    SyncEngine(store, ai)
    assert ai.analyze(historic)["summary"] == "New mail"
    assert len(calls) == 1


def test_automatic_analysis_skips_notifications_but_keeps_newsletters(store, account_data, monkeypatch):
    account_id = store.add_account(account_data)
    ai, calls = recording_ai(store, monkeypatch)
    engine = SyncEngine(store, ai)
    enable(store)
    since = store.setting("ai_automatic_boundary")["since"]
    notice = add(store, account_id, 1, since + 1, category="updates")
    newsletter = add(store, account_id, 2, since + 2, category="newsletters")
    engine.analyze_pending(account_id)
    assert len(calls) == 1
    assert store.message(notice)["analysis"] is None
    assert store.message(newsletter)["analysis"] is not None


@pytest.mark.parametrize("sender,headers,category", [
    ("notifications@github.com", {}, "updates"),
    ("notifications@github.com", {"List-Id": "<repo.github.com>",
                                   "List-Unsubscribe": "<https://github.com/notifications>"}, "updates"),
    ("notifications@linear.app", {}, "updates"),
    ("no-reply@accounts.example.com", {}, "updates"),
    ("noreply+login@example.com", {}, "updates"),
    ("service@example.com", {"Auto-Submitted": "auto-generated"}, "updates"),
    ("person@example.com", {"Auto-Submitted": "no"}, "people"),
    ("anna@example.com", {}, "people"),
    ("noreply@news.example.com", {"List-Unsubscribe": "<mailto:unsubscribe@example.com>"}, "newsletters"),
])
def test_notification_classification_does_not_need_ai(sender, headers, category):
    mail = message_from_bytes(raw_mail(), policy=policy.default)
    mail.replace_header("From", sender)
    for key, value in headers.items():
        mail[key] = value
    assert parse_message(mail.as_bytes(), "account", "INBOX", "1", 1)["category"] == category


def test_recap_excludes_notification_threads_and_messages(store, account_data):
    account_id = store.add_account(account_data)
    notice = add(store, account_id, 1, time.time(), category="updates")
    incoming = add(store, account_id, 2, time.time(), category="people")
    source = AI(store).recap_source()
    assert [thread["message_id"] for thread in source] == [incoming]
    assert all(message["id"] != notice for thread in source for message in thread["messages"])


def test_every_reactivation_resets_the_boundary_even_outside_the_settings_api(store, account_data, monkeypatch):
    account_id = store.add_account(account_data)
    ai, calls = recording_ai(store, monkeypatch)
    engine = SyncEngine(store, ai)
    previous = store.setting("ai_automatic_boundary")
    waiting = add(store, account_id, 1, previous["since"] + 3600)
    enable(store)
    current = store.setting("ai_automatic_boundary")
    assert current["after_seq"] > previous["after_seq"]
    engine.analyze_pending(account_id)
    assert calls == [] and store.message(waiting)["analysis"] is None
