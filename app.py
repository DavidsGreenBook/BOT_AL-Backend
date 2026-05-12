import os
import json
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

# ── Credentials (set these in Render's Environment tab) ──────────────────────
APP_ID          = os.environ.get("cli_aa886af21e399ed4")
APP_SECRET      = os.environ.get("WwEw66biXlxhQ3CCu9eScerUX6KMZboq")
BASE_APP_TOKEN  = os.environ.get("JAIQbyZD3aVQEisHC2zlfSDOgJc")

# ── Table map: add/edit your table names and IDs here ────────────────────────
TABLE_MAP = {
    "Tổng quan đơn hàng":   "blkhARjQKxOu7I0K",
    "Tổng quan Tiếp nhận đơn hàng":  "blkRRV5owoRRwOjh",
    "Tài liệu hướng dẫn sử dụng": "ldxzHmUKmh6YJhQB",
    "Danh mục vật tư":   "tbldV58aMuimDFZJ&view=vewggpSSC7",
    "Danh mục khách hàng":  "tblGp113BFUBq4GY&view=vewo75BSeI",
    "Danh mục vai trò truy cập": "tblbNPiAOJMclhyK&view=vewhF9LjCO",
    "Đặt hàng":     "tbl1i96WQXyBmx9U&view=vewITlqAp9",	
    "1.1 Đơn xin giá tốt":   "tblYP6yRNENOfuyy&view=vewH6ORQ7y",
    "1.2 QL Đơn xin giá tốt":  "tblxIRPJ2EShbbRn&view=vewiXd6Ic7",	
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
    data = request.json

    # 1. Handle Lark's URL verification challenge
    if "challenge" in data:
        return jsonify({"challenge": data["challenge"]})

    # 2. Extract the message
    try:
        event   = data.get("event", {})
        msg     = event.get("message", {})
        msg_type = msg.get("message_type", "")

        # Only handle text messages
        if msg_type != "text":
            return jsonify({"code": 0})

        message_id  = msg.get("message_id")
        raw_content = msg.get("content", "{}")
        user_text   = json.loads(raw_content).get("text", "").strip()

        # Strip @mention tags if the bot was @mentioned in the group
        # Lark wraps mentions like: @_user_1 actual text
        if user_text.startswith("@"):
            user_text = " ".join(user_text.split()[1:]).strip()

    except Exception as e:
        print(f"Error parsing message: {e}")
        return jsonify({"code": 0})

    if not user_text:
        return jsonify({"code": 0})

    # 3. Get access token
    token = get_tenant_token()
    if not token:
        print("Failed to get tenant token")
        return jsonify({"code": 0})

    # 4. Detect which table to query
    table_keyword, table_id = detect_table(user_text)

    if not table_id:
        available = ", ".join(TABLE_MAP.keys())
        send_reply(
            message_id,
            f"I'm not sure which table to look in.\n"
            f"Try mentioning one of these topics: {available}",
            token
        )
        return jsonify({"code": 0})

    # 5. Query Lark Base
    records, error = query_table(table_id, token)

    if error:
        send_reply(message_id, f"Sorry, I ran into an error: {error}", token)
        return jsonify({"code": 0})

    # 6. Format and send the reply
    reply = format_records(records, table_keyword)
    send_reply(message_id, reply, token)

    return jsonify({"code": 0})

# ── Health check (useful for Render + UptimeRobot) ────────────────────────────
@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
