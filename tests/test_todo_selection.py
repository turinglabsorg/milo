"""Selecting every to-do marks them done, and Milo's reply bubble stays as short as the question."""

from playwright.sync_api import expect, sync_playwright
from test_responsive_inbox import service


def test_select_all_todos_marks_them_done_and_the_reply_bubble_hugs_the_text(tmp_path):
    holder = {}

    def prepare(app, _received, _sent):
        unanswered = app.state.store.rows("SELECT id FROM messages WHERE thread_id='other'")[0]["id"]
        app.state.features.sync_todos(unanswered, {"action_items": ["Chiamare Anna", "Inviare il file"]})
        holder["bootstrap"] = app.state.store.bootstrap

    with service(tmp_path, prepare, live=True) as (url, _sent), sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 800}, service_workers="block")
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        assert page.request.post(url + "/api/setup", data={"password": "isolated test password",
                                                           "bootstrap": holder["bootstrap"]}).status == 200
        page.goto(url, wait_until="networkidle")
        page.locator('.nav-button[data-view="todo"]').click()
        expect(page.locator(".todo-text")).to_have_count(2)
        assert sorted(page.locator(".todo-text").all_text_contents()) == ["Chiamare Anna", "Inviare il file"]
        page.get_by_role("button", name="Seleziona tutte").click()
        expect(page.locator(".bulk-bar strong")).to_have_text("2 selezionate")
        expect(page.locator(".todo-row.multi")).to_have_count(2)
        page.get_by_role("button", name="Fatte").click()
        expect(page.locator(".todo-row")).to_have_count(0)
        expect(page.locator("#toast")).to_contain_text("2 cose da fare segnate come fatte.")
        heights = page.evaluate("""() => {
            const host = document.createElement('div');
            host.innerHTML = `<div class="ask-turn"><p class="ask-question">Ciao</p><div class="ask-answer"><p>Ciao</p></div><div class="ask-sources"><button><strong>Marco</strong><span>Contratto</span><time>ieri</time></button></div></div>`;
            host.style.cssText = 'position:fixed;left:0;top:0;width:360px';
            document.body.append(host);
            const question = host.querySelector('.ask-question').getBoundingClientRect().height;
            const answer = host.querySelector('.ask-answer').getBoundingClientRect().height;
            const sources = host.querySelector('.ask-sources').getBoundingClientRect().height;
            host.remove();
            return {question, answer, sources};
        }""")
        assert heights["answer"] <= heights["question"] + 2
        assert heights["sources"] > 0
        assert errors == []
        browser.close()
