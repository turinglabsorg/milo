import os
from pathlib import Path

import pytest
from playwright.sync_api import expect, sync_playwright


@pytest.mark.skipif(not os.environ.get("MILO_TEST_URL"), reason="Set MILO_TEST_URL to the isolated running demo")
@pytest.mark.parametrize("width,height", [(1440, 1000), (900, 900), (390, 844)])
def test_client_flows_and_responsive_layout(width, height):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": width, "height": height})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(os.environ["MILO_TEST_URL"])
        expect(page.locator(".message-row").first).to_be_visible()
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        Path("test-results").mkdir(exist_ok=True)
        page.screenshot(path=f"test-results/milo-{width}.png", full_page=True)
        page.locator(".message-row").first.click()
        expect(page.locator(".mail-body")).to_be_visible()
        page.get_by_role("button", name="Rispondi", exact=True).click()
        expect(page.locator("#compose-form")).to_be_visible()
        page.locator('[name="body"]').fill("A browser-tested draft")
        page.get_by_role("button", name="Salva bozza", exact=True).click()
        expect(page.locator("#toast")).to_contain_text("Bozza salvata")
        page.get_by_role("button", name="Chiudi", exact=True).click()
        if width <= 600:
            page.get_by_role("button", name="Apri menu").click()
        page.locator('[data-view="drafts"]').click()
        expect(page.locator(".draft-row").first).to_be_visible()
        page.locator(".draft-row").first.click()
        expect(page.locator('[name="body"]')).to_have_value("A browser-tested draft")
        page.get_by_role("button", name="Elimina bozza", exact=True).click()
        if width <= 600:
            page.get_by_role("button", name="Apri menu").click()
        page.locator('[data-view="inbox"]').click()
        page.get_by_role("button", name="Newsletter", exact=True).click()
        expect(page.locator(".message-row")).to_have_count(2)
        page.get_by_role("button", name="Tutte", exact=True).click()
        page.locator("#search-input").fill("weekend")
        expect(page.locator(".message-row")).to_have_count(1)
        page.locator(".message-row").click()
        expect(page.locator(".mail-content h2")).to_contain_text("Weekend")
        assert not errors
        browser.close()


@pytest.mark.skipif(not os.environ.get("MILO_LIVE_TEST_URL"), reason="Set URL and DATA for an isolated non-demo test service")
@pytest.mark.parametrize("width,height", [(1440, 1000), (900, 900), (390, 844)])
def test_real_service_onboarding_and_google_connection_ui(width, height):
    import json
    import sqlite3
    from urllib.parse import parse_qs, urlsplit

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": width, "height": height})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(os.environ["MILO_LIVE_TEST_URL"])
        expect(page.locator("#login-form")).to_be_visible()
        if page.locator('[name="bootstrap"]').count():
            with sqlite3.connect(Path(os.environ["MILO_LIVE_TEST_DATA"]) / "mail.sqlite") as db:
                bootstrap = json.loads(db.execute("SELECT value FROM settings WHERE key='bootstrap'").fetchone()[0])
            page.locator('[name="bootstrap"]').fill(bootstrap)
        page.locator('[name="password"]').fill("isolated browser test passphrase")
        page.locator('#login-form button[type="submit"]').click()
        expect(page.locator(".shell")).to_be_visible()
        expect(page.locator(".message-row")).to_have_count(0)
        page.evaluate("document.fonts.ready")
        assert page.evaluate("document.fonts.check('400 14px Geist')")
        assert page.evaluate("getComputedStyle(document.body).fontFamily").startswith("Geist")
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        if width <= 600:
            page.get_by_role("button", name="Apri menu").click()
        page.get_by_role("button", name="Aggiungi account").click()
        expect(page.get_by_role("dialog")).to_be_visible()
        if page.locator("#google-config-form").count():
            page.locator('input[type="file"]').set_input_files({"name": "test-client.json", "mimeType": "application/json",
                "buffer": json.dumps({"web": {"client_id": "browser-test.apps.googleusercontent.com",
                                               "client_secret": "isolated-test-secret"}}).encode()})
            page.get_by_role("button", name="Configura Google", exact=True).click()
        expect(page.get_by_role("button", name="Continua con Google")).to_be_enabled()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        Path("test-results").mkdir(exist_ok=True)
        page.screenshot(path=f"test-results/milo-google-{width}.png", full_page=True)
        # Intercept the outbound navigation: never authorize a test client or read real mail.
        page.route("https://accounts.google.com/**", lambda route: route.fulfill(body="OAuth navigation intercepted"))
        page.get_by_role("button", name="Continua con Google").click()
        page.wait_for_url("https://accounts.google.com/**")
        params = parse_qs(urlsplit(page.url).query)
        assert params["access_type"] == ["offline"]
        assert params["code_challenge_method"] == ["S256"]
        assert not errors
        browser.close()
