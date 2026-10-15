import json
import os
from pathlib import Path

import pytest
from playwright.sync_api import expect, sync_playwright
from test_responsive_inbox import service


@pytest.mark.parametrize("width,height,theme", [(1440, 1000, "light"), (390, 844, "dark")])
def test_proposals_enter_the_menu_only_after_acceptance(tmp_path, width, height, theme):
    context = {}

    def prepare(app, received, sent):
        store = app.state.store
        message = store.rows("SELECT id FROM messages WHERE thread_id='other'")[0]["id"]
        analysis = {"summary": "Anna chiede un preventivo e una conferma per la riunione.", "priority": "high",
                    "action_items": ["Inviare il preventivo ad Anna", "Confermare la riunione di venerdì"]}
        store.execute("UPDATE messages SET analysis=?,subject='Preventivo e riunione' WHERE id=?",
                      (json.dumps(analysis), message))
        app.state.features.sync_todos(message, analysis)
        store.set_setting("appearance", {"theme": theme})
        context.update(bootstrap=store.bootstrap, message=message)

    with service(tmp_path, prepare, live=True) as (url, _), sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": height}, service_workers="block")
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        assert page.request.post(url + "/api/setup", data={"password": "isolated approval test password",
                                                           "bootstrap": context["bootstrap"]}).status == 200
        page.goto(url)
        page.locator(f'[data-message="{context["message"]}"]').click()
        expect(page.get_by_text("Da fare proposti", exact=True)).to_be_visible()
        expect(page.get_by_role("button", name="Accetta da fare", exact=True)).to_have_count(2)
        assert page.request.get(url + "/api/todos").json()["todos"] == []
        output = Path(os.environ.get("MILO_TEST_ARTIFACTS", "test-results"))
        output.mkdir(exist_ok=True)
        page.screenshot(path=str(output / f"todo-proposals-{width}.png"))

        page.get_by_role("button", name="Accetta da fare", exact=True).first.click()
        expect(page.locator(".proposal-status")).to_have_text("Nei da fare")
        expect(page.get_by_role("button", name="Accetta da fare", exact=True)).to_have_count(1)
        assert [todo["text"] for todo in page.request.get(url + "/api/todos").json()["todos"]] == ["Inviare il preventivo ad Anna"]
        page.reload()
        page.locator(f'[data-message="{context["message"]}"]').click()
        expect(page.locator(".proposal-status")).to_have_text("Nei da fare")
        expect(page.get_by_role("button", name="Accetta da fare", exact=True)).to_have_count(1)
        assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
        page.screenshot(path=str(output / f"todo-accepted-{width}.png"))
        if width <= 900:
            page.get_by_role("button", name="Torna alla lista").click()
        if width <= 600:
            page.get_by_role("button", name="Apri menu").click()
        page.locator('[data-view="todo"]').click()
        expect(page.locator(".todo-text")).to_have_text(["Inviare il preventivo ad Anna"])
        page.screenshot(path=str(output / f"todo-menu-{width}.png"))
        assert not errors
        browser.close()
