import json
import time

from fastapi.testclient import TestClient
from test_features import add, setup_account

from milo.store import Store


def propose(client, account_data, items=None):
    store, account = setup_account(client, account_data)
    message = add(store, account, 1)
    analysis = {"summary": "Due richieste da valutare.", "priority": "high",
                "action_items": items or ["Inviare il preventivo", "Confermare la riunione"]}
    store.execute("UPDATE messages SET analysis=? WHERE id=?", (json.dumps(analysis), message))
    client.app.state.features.sync_todos(message, analysis)
    return store, message, analysis


def test_acceptance_is_individual_persistent_and_idempotent(logged_in, account_data):
    store, message, _ = propose(logged_in, account_data)
    pending = logged_in.get(f"/api/messages/{message}").json()["todos"]
    assert len(pending) == 2 and all(todo["accepted"] is None for todo in pending)
    assert logged_in.patch(f"/api/todos/{pending[0]['id']}", json={"done": True}).status_code == 404
    result = logged_in.post(f"/api/messages/{message}/todos", json={"text": pending[0]["text"]})
    assert result.status_code == 200 and result.json()["accepted"] is not None
    again = logged_in.post(f"/api/messages/{message}/todos", json={"text": pending[0]["text"]}).json()
    assert again == result.json()
    assert [todo["text"] for todo in logged_in.get("/api/todos").json()["todos"]] == [pending[0]["text"]]
    reopened = Store(store.directory)
    try:
        assert reopened.rows("SELECT COUNT(*) AS count FROM todos WHERE accepted IS NOT NULL")[0]["count"] == 1
    finally:
        reopened.close()


def test_accepted_tasks_survive_reanalysis_and_replies(logged_in, account_data):
    store, message, _ = propose(logged_in, account_data)
    accepted = logged_in.post(f"/api/messages/{message}/todos", json={"text": "Inviare il preventivo"}).json()
    analysis = {"priority": "low", "action_items": ["Un'altra proposta"]}
    logged_in.app.state.features.sync_todos(message, analysis)
    store.execute("UPDATE messages SET archived=1 WHERE id=?", (message,))
    account_id = store.accounts()[0]["id"]
    reply = add(store, account_id, 2, when=time.time() + 1)
    store.execute("UPDATE messages SET sent=1,thread_id=? WHERE id=?", (store.message(message)["thread_id"], reply))
    assert [todo["id"] for todo in logged_in.get("/api/todos").json()["todos"]] == [accepted["id"]]


def test_acceptance_validates_the_current_proposal_and_authentication(logged_in, account_data):
    store, message, _ = propose(logged_in, account_data)
    path = f"/api/messages/{message}/todos"
    assert logged_in.post(path, json={"text": "Invented action"}).status_code == 400
    assert logged_in.post(path, json={"text": ""}).status_code == 422
    assert logged_in.post('/api/messages/missing/todos', json={"text": "Action"}).status_code == 404
    visitor = TestClient(logged_in.app)
    assert visitor.post(path, json={"text": "Inviare il preventivo"}).status_code == 401
    store.execute("UPDATE messages SET sent=1 WHERE id=?", (message,))
    assert logged_in.post(path, json={"text": "Inviare il preventivo"}).status_code == 400


def test_existing_unaccepted_tasks_stay_out_of_the_list(logged_in, account_data):
    _, message, _ = propose(logged_in, account_data)
    assert logged_in.get("/api/todos").json()["todos"] == []
    assert logged_in.get("/api/state").json()["counts"]["todo"] == 0
    assert len(logged_in.get(f"/api/messages/{message}/thread?lazy=true").json()["messages"][0]["todos"]) == 2


def test_old_analysis_without_todo_rows_can_be_accepted_without_ai(logged_in, account_data):
    store, message, _ = propose(logged_in, account_data)
    store.execute("DELETE FROM todos WHERE message_id=?", (message,))
    response = logged_in.post(f"/api/messages/{message}/todos", json={"text": "Inviare il preventivo"})
    assert response.status_code == 200 and len(logged_in.get("/api/todos").json()["todos"]) == 1


def test_duplicate_and_empty_actions_are_not_reproposed(logged_in, account_data):
    store, message, _ = propose(logged_in, account_data, [" Chiamare ", "Chiamare", "", "Nessuna azione richiesta"])
    rows = store.rows("SELECT text FROM todos WHERE message_id=?", (message,))
    assert rows == [{"text": "Chiamare"}]
