import sqlite3

import pytest

import memo_app.app as memo_module


@pytest.fixture()
def client(tmp_path, monkeypatch):
    database = tmp_path / "memo.db"
    monkeypatch.setattr(memo_module, "DB_PATH", str(database))
    memo_module.init_db()
    memo_module.app.config.update(TESTING=True, SECRET_KEY="test-secret")
    return memo_module.app.test_client()


def create_memo(client, title="テストメモ", memo_date="2026-08-13", content="面接用の架空メモ"):
    return client.post("/", data={"title": title, "date": memo_date, "content": content})


def test_primary_pages_and_create(client):
    assert client.get("/").status_code == 200
    response = create_memo(client)
    assert response.status_code == 302
    page = client.get("/list")
    assert page.status_code == 200
    assert "テストメモ".encode() in page.data


def test_search_sort_edit_and_detail(client):
    create_memo(client, "買い物", "2026-08-14", "牛乳を買う")
    create_memo(client, "会議", "2026-08-15", "資料を準備する")
    assert "会議".encode() in client.get("/list?q=会議").data
    assert client.get("/list?sort=date_desc").status_code == 200
    response = client.post("/edit/1", data={"title": "買い物更新", "date": "2026-08-16", "content": "牛乳とパン"}, follow_redirects=True)
    assert "買い物更新".encode() in response.data
    assert client.get("/detail/999").status_code == 404


def test_delete_requires_post_and_csrf(client):
    create_memo(client)
    assert client.get("/delete/1").status_code == 405
    assert client.post("/delete/1").status_code == 400
    detail = client.get("/detail/1")
    with client.session_transaction() as session:
        token = session["csrf_token"]
    response = client.post("/delete/1", data={"csrf_token": token}, follow_redirects=True)
    assert response.status_code == 200
    assert client.get("/detail/1").status_code == 404
    with sqlite3.connect(memo_module.DB_PATH) as connection:
        assert connection.execute("select count(*) from memos").fetchone()[0] == 0


def test_todo_without_memos_does_not_call_ai(client):
    response = client.post("/todo_list", data={"provider": "openrouter", "model": "openrouter/free", "api_key": "test"})
    assert response.status_code == 200
    assert "メモがありません".encode() in response.data


def test_ai_model_allowlist():
    assert memo_module.GEMINI_MODEL == "gemini-2.5-flash"
    assert "openrouter/free" in memo_module.AI_MODELS["openrouter"]
    assert "gpt-5.6-sol" not in memo_module.AI_MODELS["openai"]
    assert "claude-fable-5" not in memo_module.AI_MODELS["anthropic"]
