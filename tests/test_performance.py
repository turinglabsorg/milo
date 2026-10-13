"""Regression budgets on a real local HTTP service with a sizeable test archive."""
import json
from pathlib import Path
from statistics import median
from time import perf_counter

import httpx
from playwright.sync_api import expect, sync_playwright
from test_responsive_inbox import service


def test_large_archive_api_and_client_latency(tmp_path):
    count = 21000
    app_store=[]

    def prepare(app, received, sent):
        store = app.state.store
        app_store.append(store)
        account = store.accounts()[0]['id']
        raw = b'Content-Type: text/plain; charset=utf-8\r\n\r\nStored message text.'
        store.executemany('INSERT INTO messages(id,account_id,folder,uidvalidity,uid,message_id,thread_id,'
                          'sender,sender_email,recipients,subject,body,preview,date,read) '
                          'VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                          [(f'perf-{i}', account, 'INBOX', 'perf', i, f'<perf-{i}@example.com>', f'perf-thread-{i//3}',
                            'Test sender', 'sender@example.com', 'you@example.com', f'Project {i//3}',
                            'Stored message text. ' * 200, 'Stored message text.', i + 1000, 1)
                           for i in range(count)])
        for i in range(count - 300, count):
            store.set_raw(f'perf-{i}', raw)
        store.execute('ANALYZE')

    with service(tmp_path, prepare) as (url, sent), httpx.Client(base_url=url) as client, sync_playwright() as p:
        snapshot_start = perf_counter()
        snapshot = client.get('/api/client/messages')
        snapshot_ms = (perf_counter() - snapshot_start) * 1000
        assert snapshot.status_code == 200 and len(snapshot.json()['messages']) == 200
        assert snapshot_ms < 300, f'Catalogue page: {snapshot_ms:.1f}ms'
        durations = []
        for _ in range(20):
            start = perf_counter()
            response = client.get('/api/messages')
            durations.append((perf_counter() - start) * 1000)
            assert response.status_code == 200
        rows = response.json()['messages']
        assert len(rows) == 100 and len(response.content) < 100000
        p95 = sorted(durations)[-2]
        assert p95 < 300, f'List API p95: {p95:.1f}ms'
        browser = p.chromium.launch()
        page = browser.new_page(viewport={'width': 1440, 'height': 1000})
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        start = perf_counter()
        page.goto(url)
        expect(page.locator('.message-row')).to_have_count(100)
        startup = (perf_counter() - start) * 1000
        assert startup < 2000, f'Visible inbox: {startup:.1f}ms'
        readers = []
        for message in rows[:5]:
            start = perf_counter()
            page.locator(f'[data-message="{message["id"]}"]').click()
            expect(page.locator('.mail-content h2')).to_have_text(message['subject'])
            expect(page.locator('.thread-message')).to_have_count(3 if message['message_count'] == 3 else 1)
            expect(page.locator('.skeleton-group.reader')).to_have_count(0)
            readers.append((perf_counter() - start) * 1000)
        assert max(readers) < 1000, f'Slowest reader: {max(readers):.1f}ms'
        page.get_by_role('button', name='Rispondi', exact=True).click()
        field = page.locator('[name="body"]')
        field.fill('A large draft. ' * 14000)
        start = perf_counter()
        field.press('Control+End')
        field.press_sequentially('Typed without waiting for the server')
        typing = (perf_counter() - start) * 1000
        assert typing < 1000, f'35 keystrokes: {typing:.1f}ms'
        assert field.input_value().endswith('Typed without waiting for the server')
        assert not errors
        report = {'test_messages': count, 'list_p50_ms': round(median(durations), 1), 'list_p95_ms': round(p95, 1),
                  'inbox_visible_ms': round(startup, 1), 'reader_max_ms': round(max(readers), 1),
                  'large_draft_typing_ms': round(typing, 1), 'list_bytes': len(response.content), 'catalogue_page_ms': round(snapshot_ms,1)}
        Path('test-results').mkdir(exist_ok=True)
        Path('test-results/performance.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report))
        browser.close()
