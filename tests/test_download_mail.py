import threading
import time
from pathlib import Path

from playwright.sync_api import expect, sync_playwright
from test_conversations import add
from test_responsive_inbox import service


def test_entry_reload_button_and_foreground_check_providers_immediately(tmp_path):
    context = {"calls": 0}

    def prepare(app, received, sent):
        context["bootstrap"] = app.state.store.bootstrap
        account = app.state.store.accounts()[0]["id"]

        def sync():
            context["calls"] += 1
            number = context["calls"]
            # The first pass belongs to the server's startup worker.
            if number > 1:
                add(app.state.store, account, 100 + number, thread=f"arrival-{number}", date=time.time())
            return []

        app.state.engine.sync_all = sync

    with service(tmp_path, prepare, live=True) as (url, sent), sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(service_workers="block")
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        assert page.request.post(url + "/api/setup", data={
            "password": "isolated test password", "bootstrap": context["bootstrap"]}).ok
        assert context["calls"] == 1
        with page.expect_response(lambda response: response.url.endswith("/api/sync")
                                  and response.request.method == "POST", timeout=5000):
            page.goto(url)
        expect(page.locator(".message-row")).to_have_count(3)
        assert context["calls"] == 2

        button = page.get_by_role("button", name="Scarica posta ora", exact=True)
        with page.expect_response("**/api/sync", timeout=5000):
            button.click()
        expect(page.locator(".message-row")).to_have_count(4)
        assert context["calls"] == 3

        with page.expect_response("**/api/sync", timeout=5000):
            page.reload()
        expect(page.locator(".message-row")).to_have_count(5)
        assert context["calls"] == 4

        # macOS forwards applicationDidBecomeActive to this event in WKWebView.
        page.wait_for_timeout(1600)
        with page.expect_response("**/api/sync", timeout=5000):
            page.evaluate("window.dispatchEvent(new Event('milo-download-mail'))")
        expect(page.locator(".message-row")).to_have_count(6)
        assert context["calls"] == 5
        page.wait_for_timeout(1600)
        with page.expect_response("**/api/sync", timeout=5000):
            page.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
        expect(page.locator(".message-row")).to_have_count(7)
        assert context["calls"] == 6
        assert not errors
        Path("test-results").mkdir(exist_ok=True)
        page.screenshot(path="test-results/download-mail-now.png")
        browser.close()


def test_cached_entry_checks_mail_even_while_status_is_slow(tmp_path):
    with service(tmp_path) as (url, sent), sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(service_workers="block")
        page.goto(url)
        expect(page.locator(".message-row")).to_have_count(2)
        page.wait_for_function("""async()=>{
            const {deviceCache}=await import('/static/cache.js');
            return !!(await deviceCache.get('api:/status')) && !!(await deviceCache.get('api:/state'));
        }""")
        held = []
        page.route("**/api/status", lambda route: held.append(route))
        with page.expect_response("**/api/sync", timeout=5000):
            page.reload(wait_until="domcontentloaded")
        expect(page.locator(".message-row")).to_have_count(2, timeout=1000)
        for route in held:
            route.continue_()
        page.unroute("**/api/status")
        browser.close()


def test_download_ack_is_fast_and_concurrent_clicks_do_not_queue_syncs(tmp_path):
    context = {}
    entered, release = threading.Event(), threading.Event()

    def prepare(app, received, sent):
        context["bootstrap"] = app.state.store.bootstrap
        context["engine"] = app.state.engine

    with service(tmp_path, prepare, live=True) as (url, sent), sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(service_workers="block")
        assert page.request.post(url + "/api/setup", data={
            "password": "isolated test password", "bootstrap": context["bootstrap"]}).ok
        with page.expect_response("**/api/sync", timeout=5000):
            page.goto(url)
        expect(page.locator(".message-row")).to_have_count(2)
        calls = []

        def slow_sync():
            calls.append(True)
            entered.set()
            release.wait(10)
            return []

        context["engine"].sync_all = slow_sync
        try:
            with page.expect_response("**/api/sync", timeout=2000) as response:
                page.get_by_role("button", name="Scarica posta ora", exact=True).click()
            assert response.value.status == 202
            assert entered.wait(2)
            page.get_by_role("button", name="Scarica posta ora", exact=True).click()
            expect(page.locator(".message-row")).to_have_count(2)
            page.locator("#search-input").fill("Still responsive")
            expect(page.locator("#search-input")).to_have_value("Still responsive")
            assert calls == [True]
        finally:
            release.set()
            browser.close()
