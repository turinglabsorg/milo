import asyncio
import hashlib
import json
import time
from datetime import datetime, timezone


class RecapWorker:
    def __init__(self, store, ai, interval=15, debounce=2):
        self.store, self.ai = store, ai
        self.interval, self.debounce = interval, debounce
        self.event = asyncio.Event()
        self.shutdown = asyncio.Event()
        self.stopping = False
        self.loop = None
        self.retry_after = 0
        self.failed_fingerprint = None

    def wake(self):
        if self.loop and not self.stopping:
            self.loop.call_soon_threadsafe(self.event.set)

    def stop(self):
        self.stopping = True
        self.wake()
        self.event.set()
        self.shutdown.set()

    def snapshot(self):
        cached = self.store.setting("recap") or {}
        return {"overview": "", "priorities": [], "message_ids": [], "generated_at": None,
                **cached, "status": self.store.setting("recap_status") or {"phase": "pending"}}

    def refresh(self):
        if not self.ai.permitted():
            self.store.set_setting("recap_status", {"phase": "disabled"})
            return
        source = self.ai.recap_source()
        fingerprint = hashlib.sha256(json.dumps(
            {"source": sorted(source, key=lambda thread: thread["message_id"]), "identity": self.ai.owner_context(), "model": self.store.setting("ai")["model"],
             "day": datetime.now(timezone.utc).date().isoformat()},
            ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        cached = self.store.setting("recap")
        if cached and cached.get("fingerprint") == fingerprint:
            self.store.set_setting("recap_status", {"phase": "ready"})
            return
        if self.failed_fingerprint == fingerprint and time.time() < self.retry_after:
            return
        self.store.set_setting("recap_status", {"phase": "updating"})
        try:
            result = self.ai.recap(source)
            self.store.set_setting("recap", {**result, "generated_at": time.time(), "fingerprint": fingerprint})
            self.store.set_setting("recap_status", {"phase": "ready"})
            self.failed_fingerprint = None
        except Exception:
            self.failed_fingerprint = fingerprint
            self.retry_after = time.time() + 60
            self.store.set_setting("recap_status", {"phase": "error", "error":
                "Le email restano disponibili. Milo riproverà ad aggiornare il recap in background."})

    async def run(self):
        self.loop = asyncio.get_running_loop()
        self.event.set()
        while not self.stopping:
            try:
                await asyncio.wait_for(self.event.wait(), timeout=self.interval)
            except TimeoutError:
                pass
            self.event.clear()
            if self.stopping:
                break
            try:
                await asyncio.wait_for(self.shutdown.wait(), timeout=self.debounce)
            except TimeoutError:
                pass
            if not self.stopping:
                await asyncio.to_thread(self.refresh)
        self.loop = None
