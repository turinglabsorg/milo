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
