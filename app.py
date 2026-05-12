import os
import json
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

# ── Credentials (set these in Render's Environment tab) ──────────────────────
APP_ID         = os.environ.get("APP_ID")
APP_SECRET     = os.environ.get("APP_SECRET")
BASE_APP_TOKEN = os.environ.get("BASE_APP_TOKEN")

# ── Table map: add/edit your table names and IDs here ────────────────────────
TABLE_MAP = {
    "tổng quan đơn hàng":                "blkhARjQKxOu7I0K",
    "tổng quan tiếp nhận đơn hàng":      "blkRRV5owoRRwOjh",
    "tài liệu hướng dẫn sử dụng":        "ldxzHmUKmh6YJhQB",
    "danh mục vật tư":                   "tbldV58aMuimDFZJ",
    "danh mục khách hàng":               "tblGp113BFUBq4GY",
    "danh mục vai trò truy cập":         "tblbNPiAOJMclhyK",
    "đặt hàng":                          "tbl1i96WQXyBmx9U",
    "đơn xin giá tốt":                   "tblYP6yRNENOfuyy",
    "ql đơn xin giá tốt":                "tblxIRPJ2EShbbRn",
}

# ── Auth ──────────────────────────────────────────────────────────────────────
def get_tenant_token():
    resp = requests.post(
        "https://open.larksuite.com/open-apis/auth/v3/tenant_access_token/internal",
        json={"app_id": APP_ID, "app_secret": APP_SECRET}
    )
    return resp.json().get("tenant_access_token")

# ── Table routing ─────────────────────────────────────────────────────────────
def detect_table(user_text):
    text_lower = user_text.lower()
    for keyword, table_id in TABLE_MAP.items():
        if keyword in text_lower:
            return keyword, table_id
    return None, None

# ── Lark Base query ───────────────────────────────────────────────────────────
def query_table(table_id, token):
    url = (
        f"https://open.larksuite.com/open-apis/bitable/v1"
        f"/apps/{BASE_APP_TOKEN}/tables/{table_id}/records"
    )
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(url, headers=headers, params={"page_size": 10})
    data = resp.json()

    if data.get("code") != 0:
        return None, f"Lark Base error: {data.get('msg', 'unknown error')}"

    items = data.get("data", {}).get("items", [])
    return items, None

# ── Format records into readable text ─────────────────────────────────────────
def format_records(records, table_name):
    if not records:
        return f"No records found in the **{table_name}** table."

    lines = [f"Here are the results from the **{table_name}** table:\n"]
    for i, record in enumerate(records, 1):
        fields = record.get("fields", {})
        field_lines = "\n".join(f"  • {k}: {v}" for k, v in fields.items())
        lines.append(f"Record {i}:\n{field_lines}")

    return "\n\n".join(lines)

# ── Send reply to Lark ────────────────────────────────────────────────────────
def send_reply(message_id, text, token):
    url = f"https://open.larksuite.com/open-apis/im/v1/messages/{message_id}/reply"
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "content": json.dumps({"text": text}),
        "msg_type": "text"
    }
    resp = requests.post(url, headers=headers, json=payload)
    return resp.json()

# ── Webhook endpoint ──────────────────────────────────────────────────────────
@app.route("/webhook", methods=["POST"])
def webhook():
    # Log the raw incoming request
    raw = request.get_data(as_text=True)
    print("RAW BODY:", raw)
    print("HEADERS:", dict(request.headers))

    data = request.json
    print("PARSED JSON:", data)

    # Handle challenge - check all possible locations
    # Sometimes Lark wraps it under a different key
    if not data:
        return jsonify({"error": "no data"}), 200

    # Case 1: challenge at top level {"challenge": "..."}
    if "challenge" in data:
        challenge_val = data["challenge"]
        print("CHALLENGE FOUND (top level):", challenge_val)
        return jsonify({"challenge": challenge_val}), 200

    # Case 2: challenge nested under "event"
    if data.get("event", {}).get("challenge"):
        challenge_val = data["event"]["challenge"]
        print("CHALLENGE FOUND (nested):", challenge_val)
        return jsonify({"challenge": challenge_val}), 200

    # Normal message handling below...
    try:
        event    = data.get("event", {})
        msg      = event.get("message", {})
        msg_type = msg.get("message_type", "")

        if msg_type != "text":
            return jsonify({"status": "ignored"}), 200

        message_id  = msg.get("message_id")
        raw_content = msg.get("content", "{}")
        user_text   = json.loads(raw_content).get("text", "").strip()

        if user_text.startswith("@"):
            user_text = " ".join(user_text.split()[1:]).strip()

    except Exception as e:
        print(f"Error parsing message: {e}")
        return jsonify({"status": "error"}), 200

    if not user_text:
        return jsonify({"status": "empty"}), 200

    token = get_tenant_token()
    if not token:
        print("Failed to get tenant token")
        return jsonify({"status": "no_token"}), 200

    table_keyword, table_id = detect_table(user_text)

    if not table_id:
        available = ", ".join(TABLE_MAP.keys())
        send_reply(
            message_id,
            f"Tôi không chắc nên tra bảng nào.\n"
            f"Hãy thử nhắc đến một trong các chủ đề: {available}",
            token
        )
        return jsonify({"status": "no_table"}), 200

    records, error = query_table(table_id, token)

    if error:
        send_reply(message_id, f"Xin lỗi, có lỗi xảy ra: {error}", token)
        return jsonify({"status": "query_error"}), 200

    reply = format_records(records, table_keyword)
    send_reply(message_id, reply, token)

    return jsonify({"status": "ok"}), 200

# ── Health check (useful for Render + UptimeRobot) ────────────────────────────
@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
