import socket
import threading
import time

import httpx
import uvicorn

from milo.app import create_app


def test_event_stream_announces_visible_changes(tmp_path, monkeypatch):
    monkeypatch.setattr("milo.app.EVENT_COALESCE", 0.01)
    app = create_app(tmp_path / "data", demo=True)
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning",
                                           timeout_graceful_shutdown=1))
    thread = threading.Thread(target=server.run)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started and time.monotonic() < deadline:
            time.sleep(0.05)
        store = app.state.store
        with httpx.stream("GET", f"http://127.0.0.1:{port}/api/events", timeout=10) as response:
            assert response.headers["content-type"].startswith("text/event-stream")
            assert "content-encoding" not in response.headers
            lines = response.iter_lines()
            assert next(line for line in lines if line.startswith("event:")) == "event: hello"
            time.sleep(0.2)  # let startup work settle
            # Sessions are invisible to the mailbox: they never wake clients.
            store.new_session()
            store.execute("UPDATE messages SET read=1")
            event = next(line for line in lines if line.startswith("event:"))
            assert event == "event: change"
    finally:
        server.should_exit = True
        thread.join(10)
    assert not thread.is_alive()


def test_only_list_visible_writes_wake_clients(store):
    seen = []
    store.on_change = lambda: seen.append(1)
    store.new_session()
    assert seen == []
    store.execute("UPDATE messages SET read=1")
    assert seen == [1]
    with store.transaction():
        store.execute("UPDATE messages SET read=0")
        store.execute("DELETE FROM drafts")
        assert seen == [1]
    assert seen == [1, 1]
