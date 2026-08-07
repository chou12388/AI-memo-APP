from flask import Flask, jsonify, render_template, request, redirect, url_for
import sqlite3
import os
import unicodedata
import json
import requests
from datetime import date
from google import genai
from google.genai import types

app = Flask(__name__)
# Keep every rendered HTML page in UTF-8.  Although Flask normally chooses UTF-8
# automatically, setting it explicitly prevents browsers from guessing a legacy
# encoding and displaying Japanese AI output as mojibake.
app.config["JSON_AS_ASCII"] = False


@app.after_request
def force_utf8_html(response):
    if response.mimetype == "text/html":
        response.charset = "utf-8"
    return response

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "memo.db")

# Gemini no longer enables gemini-2.5-flash for new API users.  Allow an
# environment override while using the current Flash model by default.
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash").strip()


def get_gemini_client(api_key):
    """Create a client from the key supplied for this request only."""
    if not api_key:
        raise RuntimeError("A Gemini API key is required for this request")
    return genai.Client(api_key=api_key)


AI_MODELS = {
    "gemini": {
        "gemini-3.6-flash", "gemini-3.5-flash", "gemini-3.5-flash-lite",
        "gemini-3.1-flash-lite", "gemini-3.1-pro-preview",
        "gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.5-pro",
    },
    # OpenAI API models offered by the model picker.  Keep this allow-list on
    # the server as well as in the browser so a submitted form cannot request
    # an arbitrary model with the user's key.
    "openai": {
        "gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna",
        "gpt-5.5", "gpt-5.4", "gpt-5.4-mini", "gpt-5.4-nano",
        "gpt-5", "gpt-5-mini",
    },
    "openrouter": {"openrouter/free"},
    "anthropic": {
        "claude-fable-5", "claude-opus-5", "claude-sonnet-5",
        "claude-haiku-4-5-20251001", "claude-sonnet-4-20250514",
    },
}


def generate_todo_text(provider, model, api_key, prompt):
    """Call the selected provider without retaining the user's API key."""
    if provider not in AI_MODELS or model not in AI_MODELS[provider]:
        raise ValueError("Unsupported AI provider or model")
    if not api_key:
        raise ValueError("An API key is required")
    if provider == "gemini":
        response = get_gemini_client(api_key).models.generate_content(
            model=model, contents=prompt,
            config=types.GenerateContentConfig(temperature=0.2, http_options=types.HttpOptions(timeout=60_000)),
        )
        return response.text
    if provider == "openai":
        response = requests.post("https://api.openai.com/v1/responses", headers={"Authorization": f"Bearer {api_key}"}, json={"model": model, "input": prompt}, timeout=60)
        response.raise_for_status()
        return "".join(part.get("text", "") for item in response.json().get("output", []) for part in item.get("content", []) if part.get("type") == "output_text")
    if provider == "openrouter":
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": model, "messages": [{"role": "user", "content": prompt}]},
            timeout=60,
        )
        response.raise_for_status()
        return response.json().get("choices", [{}])[0].get("message", {}).get("content", "")
    response = requests.post("https://api.anthropic.com/v1/messages", headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"}, json={"model": model, "max_tokens": 1024, "messages": [{"role": "user", "content": prompt}]}, timeout=60)
    response.raise_for_status()
    return "".join(part.get("text", "") for part in response.json().get("content", []) if part.get("type") == "text")


def ai_error_message(error):
    """Turn provider failures into safe, user-actionable messages."""
    detail = str(error).lower()
    if "429" in detail or "resource_exhausted" in detail or "rate limit" in detail:
        return "429：無料枠の回数・速度制限です。少し待ってから再試行してください。"
    if "401" in detail or "403" in detail or "authentication" in detail or "permission" in detail:
        return "401/403：API Key、プロジェクト権限、請求設定を確認してください。"
    if "404" in detail or "not_found" in detail or "model not found" in detail:
        return "404：選択したモデルを利用できません。別のモデルを選んでください。"
    if "timeout" in detail:
        return "タイムアウト：通信または AI の応答が遅すぎます。もう一度お試しください。"
    if "connect" in detail or "network" in detail or "connection" in detail:
        return "ネットワーク接続エラー：プロキシ、VPN、またはインターネット接続を確認してください。"
    return "接続に失敗しました。AI 設定、残高、ネットワークを確認してください。"


@app.post("/test_ai")
def test_ai_connection():
    """Test a user-provided provider key without persisting it."""
    provider = request.form.get("provider", "gemini")
    model = request.form.get("model", "")
    api_key = request.form.get("api_key", "").strip()
    try:
        result = generate_todo_text(provider, model, api_key, "Reply with exactly: OK")
        if not result:
            raise RuntimeError("The provider returned an empty response")
        return jsonify(ok=True, message=f"{provider} / {model} に接続できました。")
    except requests.HTTPError as error:
        status = error.response.status_code if error.response is not None else ""
        return jsonify(ok=False, error=f"API エラー ({status})。Key、モデル、利用可能な残高を確認してください。"), 400
    except Exception as error:
        app.logger.exception("AI connection test failed")
        return jsonify(ok=False, error=ai_error_message(error)), 400


def normalize_ai_text(text):
    """Keep Gemini output readable when an upstream response was decoded twice."""
    text = unicodedata.normalize("NFC", text or "")
    try:
        # Typical mojibake, e.g. "ã¡ã¢", is UTF-8 bytes read as Latin-1.
        return text.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS memos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            date TEXT,
            content TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

#  首页：新增注册
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        date = request.form.get("date", "").strip()
        content = request.form.get("content", "").strip()

        if not title or not date or not content:
            return render_template("error.html")

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO memos (title, date, content) VALUES (?, ?, ?)", (title, date, content))
        conn.commit()
        conn.close()
        return redirect(url_for("view_list"))
        
    return render_template("form.html")

# 2. 列表页：支持搜索与排序
@app.route("/list", methods=["GET"])
def view_list():
    search_query = request.args.get("q", "").strip()
    sort_type = request.args.get("sort", "id_asc").strip()
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    sort_sql_dict = {
        "id_asc": "ORDER BY id ASC",
        "date_desc": "ORDER BY date DESC",
        "date_asc": "ORDER BY date ASC",
        "title_asc": "ORDER BY title ASC"
    }
    order_by_clause = sort_sql_dict.get(sort_type, "ORDER BY id ASC")
    
    if search_query:
        cursor.execute(f"SELECT id, title, date FROM memos WHERE title LIKE ? {order_by_clause}", (f"%{search_query}%",))
    else:
        cursor.execute(f"SELECT id, title, date FROM memos {order_by_clause}")
        
    memos = cursor.fetchall()
    conn.close()
    return render_template("list.html", memos=memos, search_query=search_query, current_sort=sort_type)

#  详细页
@app.route("/detail/<int:memo_id>")
def view_detail(memo_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, date, content FROM memos WHERE id = ?", (memo_id,))
    memo = cursor.fetchone()
    conn.close()
    
    if memo is None:
        return "メモが見つかりません。", 404
        
    return render_template("detail.html", memo=memo)

# 编辑与更新
@app.route("/edit/<int:memo_id>", methods=["GET", "POST"])
def edit_memo(memo_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        date = request.form.get("date", "").strip()
        content = request.form.get("content", "").strip()
        
        if not title or not date or not content:
            conn.close()
            return render_template("error.html")
            
        cursor.execute("UPDATE memos SET title = ?, date = ?, content = ? WHERE id = ?", (title, date, content, memo_id))
        conn.commit()
        conn.close()
        return redirect(url_for("view_detail", memo_id=memo_id))
    else:
        cursor.execute("SELECT id, title, date, content FROM memos WHERE id = ?", (memo_id,))
        memo = cursor.fetchone()
        conn.close()
        return render_template("edit.html", memo=memo)

# 删除功能
@app.route("/delete/<int:memo_id>")
def delete_memo(memo_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM memos WHERE id = ?", (memo_id,))

    # SQLite AUTOINCREMENT intentionally does not reuse deleted IDs.  Once the
    # list is completely empty, reset its sequence so the next new memo starts
    # at ID 1 again.  Never renumber a non-empty list: detail/edit links rely
    # on those IDs remaining stable.
    cursor.execute("SELECT COUNT(*) FROM memos")
    if cursor.fetchone()[0] == 0:
        cursor.execute("DELETE FROM sqlite_sequence WHERE name = ?", ("memos",))

    conn.commit()
    conn.close()
    return redirect(url_for("view_list"))


@app.post("/voice_note")
def create_voice_note():
    """Turn browser-transcribed speech into a memo with the selected AI provider."""
    transcript = request.form.get("transcript", "").strip()
    provider = request.form.get("provider", "").strip()
    model = request.form.get("model", "").strip()
    api_key = request.form.get("api_key", "").strip()
    language = request.form.get("language", "ja-JP")
    if not transcript:
        return jsonify(error="音声認識のテキストが見つかりません。"), 400

    prompt = f"""
    You are a memo assistant. The following text was transcribed from a {language} voice note.
    Turn it into one concise memo. Return ONLY valid JSON, without Markdown, in exactly this shape:
    {{"title":"short title","date":"YYYY-MM-DD","content":"clean transcript and useful details"}}

    Today's date is {date.today().isoformat()}. Resolve relative dates such as tomorrow or next Friday using this date.
    If no date is spoken, use today's date. The title and content MUST use the language of the transcribed text.
    For ja-JP, write the title and content in Japanese. For zh-CN, write them in Simplified Chinese.
    Never use English for the title unless the transcribed text is English. Do not invent facts.

    Transcribed text:
    {transcript}
    """
    try:
        raw_response = generate_todo_text(provider, model, api_key, prompt)
        draft = json.loads(raw_response.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip())
        title = str(draft.get("title", "")).strip()[:100]
        content = str(draft.get("content", "")).strip()[:10000]
        memo_date = str(draft.get("date", date.today().isoformat())).strip()
        date.fromisoformat(memo_date)
        if not title or not content:
            raise ValueError("Gemini returned an incomplete memo draft")
        return jsonify(title=title, date=memo_date, content=content)
    except Exception:
        app.logger.exception("AI voice memo generation failed")
        return jsonify(error="音声メモを作成できませんでした。もう一度お試しください。"), 502

#  AI 生成 ToDo 列表
@app.route("/todo_list", methods=["GET", "POST"])
def view_todo_list():
    if request.method == "GET":
        return redirect(url_for("view_list"))

    api_key = request.form.get("api_key", "").strip()
    provider = request.form.get("provider", "gemini")
    model = request.form.get("model", GEMINI_MODEL)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # 条件 ⑤⑥：从DB取得所有的备忘录内容（使用 fetchall）
    cursor.execute("SELECT content FROM memos")
    rows = cursor.fetchall()
    conn.close()
    
    # 拼接所有备忘录内容，准备发送给 Gemini API
    all_contents = "\n".join([row[0] for row in rows if row[0]])
    
    if not all_contents:
        ai_response_text = "メモがありません。まずはメモを登録してください。"
    else:
        # 把所有备忘录内容发送给 Gemini API，让它找出需要做的事情并生成 ToDo 列表
        prompt = f"""
        以下はユーザーが作成したメモのテキスト一覧です。
        この中から「やらないといけないこと（タスク・ToDo）」が書いてありそうな内容だけを探し出して、分かりやすい日本語の「ToDoリスト」にまとめて出力してください。
        
        【メモ内容】
        {all_contents}
        """
        
        try:
            ai_response_text = generate_todo_text(provider, model, api_key, prompt)
            if not ai_response_text:
                raise RuntimeError("Gemini returned an empty response")
            ai_response_text = normalize_ai_text(ai_response_text)
        except Exception:
            # Keep provider details in the server log for diagnosis, but do not
            # expose internal errors or credentials in the browser.
            app.logger.exception("Gemini ToDo generation failed")
            ai_response_text = "AIリストを作成できませんでした。APIキーとネットワーク接続を確認して、もう一度お試しください。"

    # 将 AI 生成的列表传递给 todo_list.html 展示
    return render_template("todo_list.html", todo_content=ai_response_text)

if __name__ == "__main__":
    app.run(debug=True)
