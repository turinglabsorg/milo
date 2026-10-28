import pytest
from test_conversations import add


def test_explicit_limit_reads_all_conversations_without_gaps_or_duplicates(logged_in, account_data):
    store = logged_in.app.state.store
    account = store.add_account(account_data)
    expected = set()
    for index in range(113):
        thread = f"thread-{index}"
        add(store, account, index * 2 + 1, thread=thread, date=index // 3)
        expected.add(add(store, account, index * 2 + 2, sent=True, thread=thread, date=index // 3 + 1000))
    pinned = next(iter(expected))
    store.patch_conversation(pinned, {"pinned": True})
    legacy = logged_in.get("/api/messages", params={"view": "all"}).json()
    assert set(legacy) == {"messages"} and len(legacy["messages"]) == 100
    assert legacy["messages"][0]["id"] == pinned

    query = {"view": "all", "limit": 7, "account": account}
    seen = []
    pages = 0
    while query:
        response = logged_in.get("/api/messages", params=query)
        assert response.status_code == 200
        page = response.json()
        assert 0 < len(page["messages"]) <= 7
        assert all(not {"body", "raw", "html"} & row.keys() for row in page["messages"])
        seen.extend(row["id"] for row in page["messages"])
        query = page["next"]
        pages += 1
        assert pages < 20
    assert set(seen) == expected and len(seen) == len(expected)
    assert pages == 17


def test_following_page_preserves_all_filters_and_excludes_other_accounts(logged_in, account_data):
    store = logged_in.app.state.store
    account = store.add_account(account_data)
    other = store.add_account({**account_data, "email": "other@example.com"})
    matching = set()
    for index in range(8):
        message = add(store, other if index == 7 else account, index + 1,
                      sent=index != 6, thread=f"filtered-{index}", date=index)
        store.execute("UPDATE messages SET recipients=?,category=? WHERE id=?",
                      ("office@example.org" if index != 5 else "different@example.org", "work", message))
        if index < 3:
            matching.add(message)
        elif index in (3, 4):
            store.execute(f"UPDATE messages SET {'hidden' if index == 3 else 'trashed'}=1 WHERE id=?", (message,))
    filters = {"view": "sent", "category": "work", "account": account, "search": "OFFICE@example.org"}
    first = logged_in.get("/api/messages", params={**filters, "limit": 2}).json()
    assert len(first["messages"]) == 2
    assert all(first["next"][key] == value for key, value in filters.items())
    assert first["next"]["limit"] == 2
    second = logged_in.get("/api/messages", params=first["next"]).json()
    assert len(second["messages"]) == 1 and second["next"] is None
    assert {row["id"] for row in first["messages"] + second["messages"]} == matching


def test_cursor_remains_stable_when_new_conversations_arrive(logged_in, account_data):
    store = logged_in.app.state.store
    account = store.add_account(account_data)
    original = {add(store, account, index + 1, thread=f"initial-{index}", date=index) for index in range(5)}
    first = logged_in.get("/api/messages", params={"view": "all", "limit": 2}).json()
    newer = add(store, account, 99, thread="new-arrival", date=999)
    seen = [row["id"] for row in first["messages"]]
    query = first["next"]
    while query:
        page = logged_in.get("/api/messages", params=query).json()
        seen.extend(row["id"] for row in page["messages"])
        query = page["next"]
    assert set(seen) == original and len(seen) == 5 and newer not in seen
    refresh = logged_in.get("/api/messages", params={"view": "all", "limit": 1}).json()
    assert refresh["messages"][0]["id"] == newer


@pytest.mark.parametrize("query", [
    {"limit": 0}, {"limit": -1}, {"limit": 501}, {"limit": "invalid"},
    {"before_date": 1}, {"before_id": "id"},
    {"before_date": "nan", "before_id": "id"},
    {"before_date": "inf", "before_id": "id"},
    {"before_date": 1, "before_id": "x" * 129},
])
def test_invalid_pagination_is_rejected_instead_of_silently_using_the_first_page(logged_in, query):
    assert logged_in.get("/api/messages", params=query).status_code == 422
