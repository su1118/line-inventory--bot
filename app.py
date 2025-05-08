from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, FlexSendMessage

import json, os, random, datetime

# ===== LINE Bot 設定 =====
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# ===== Flask App =====
app = Flask(__name__)

# ===== 常數設定 =====
CATEGORY_CODES = {"衣物": "CL", "背包": "BA", "杯具": "CU", "帽子": "CA", "配件": "TH", "徽章磁鐵": "MA"}
SIZE_CODES = {"S": "1", "M": "2", "L": "3", "XL": "4", "2XL": "5", "3XL": "6", "4XL": "7", "5XL": "8"}
DATA_FILE = "inventory.json"
LOG_FILE = "log.txt"

user_states = {}

# ===== 資料存取 =====
def load_inventory():
    return json.load(open(DATA_FILE, "r", encoding="utf-8")) if os.path.exists(DATA_FILE) else {}

def save_inventory(data):
    json.dump(data, open(DATA_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

def log_action(user, action):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{now}] {user}: {action}\n")

# ===== Flex Message 功能選單 =====
def get_function_flex():
    flex_message_content = {
        "type": "bubble",
        "size": "mega",
        "header": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "text",
                    "text": "請選擇功能",
                    "weight": "bold",
                    "size": "xl",
                    "align": "center"
                }
            ]
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "spacing": "md",
            "contents": [
                {"type": "button", "style": "primary", "action": {"type": "message", "label": "新增商品", "text": "新增"}},
                {"type": "button", "style": "primary", "action": {"type": "message", "label": "查詢商品", "text": "查詢"}},
                {"type": "button", "style": "primary", "action": {"type": "message", "label": "補貨", "text": "補貨"}},
                {"type": "button", "style": "primary", "action": {"type": "message", "label": "販售", "text": "販售"}},
                {"type": "button", "style": "primary", "action": {"type": "message", "label": "調貨", "text": "調貨"}},
                {"type": "button", "style": "primary", "action": {"type": "message", "label": "刪除商品", "text": "刪除"}},
                {"type": "button", "style": "primary", "action": {"type": "message", "label": "商品總覽", "text": "總覽"}},
                {"type": "button", "style": "primary", "action": {"type": "message", "label": "紀錄查詢", "text": "紀錄"}}
            ]
        }
    }
    return FlexSendMessage(alt_text="請選擇功能", contents=flex_message_content)

# ===== 分步輸入處理器（新增、補貨、販售、調貨、刪除） =====
def handle_step_input(user_id, text):
    state = user_states[user_id]
    data = state["data"]

    if state["action"] == "add":
        if state["step"] == 1:
            data["name"] = text
            state["step"] = 2
            return "請輸入分類（衣物／背包／杯具／帽子／配件／徽章磁鐵）："
        elif state["step"] == 2:
            data["category"] = text
            state["step"] = 3
            return "請輸入尺寸（S ~ 5XL，若無尺寸請輸入 無）："
        elif state["step"] == 3:
            data["size"] = text
            state["step"] = 4
            return "請輸入數量："
        elif state["step"] == 4:
            try:
                qty = int(text)
                user_states.pop(user_id)
                return add_text(data["name"], data["category"], data["size"], qty, user_id)
            except ValueError:
                return "請輸入正確的數字作為數量"

    elif state["action"] in ["restock", "sell", "transfer"]:
        if state["step"] == 1:
            data["code"] = text
            state["step"] = 2
            return "請輸入數量："
        elif state["step"] == 2:
            try:
                qty = int(text)
                user_states.pop(user_id)
                if state["action"] == "restock":
                    return restock_text(data["code"], qty, user_id)
                elif state["action"] == "sell":
                    return sell_text(data["code"], qty, user_id)
                elif state["action"] == "transfer":
                    return transfer_text(data["code"], qty, user_id)
            except ValueError:
                return "請輸入正確的數字作為數量"

    elif state["action"] == "delete":
        if state["step"] == 1:
            data["code"] = text
            state["step"] = 2
            return "請輸入數量："
        elif state["step"] == 2:
            try:
                data["qty"] = int(text)
                state["step"] = 3
                return "請輸入地點（中心 或 倉庫）："
            except ValueError:
                return "請輸入正確的數字作為數量"
        elif state["step"] == 3:
            location = text.strip()
            if location not in ["中心", "倉庫"]:
                return "請輸入「中心」或「倉庫」"
            user_states.pop(user_id)
            return delete_text(data["code"], data["qty"], location, user_id)

# ===== LINE Webhook 接收點 =====
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

# ===== 處理 LINE 訊息事件 =====
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    text = event.message.text.strip()

    if user_id in user_states:
        reply = handle_step_input(user_id, text)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
        return

    if text.lower() in ["功能", "menu", "選單"]:
        line_bot_api.reply_message(event.reply_token, get_function_flex())
        return

    if text == "新增":
        user_states[user_id] = {"action": "add", "step": 1, "data": {}}
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="請輸入商品名稱："))
        return
    if text == "補貨":
        user_states[user_id] = {"action": "restock", "step": 1, "data": {}}
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="請輸入商品代碼："))
        return
    if text == "販售":
        user_states[user_id] = {"action": "sell", "step": 1, "data": {}}
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="請輸入商品代碼："))
        return
    if text == "調貨":
        user_states[user_id] = {"action": "transfer", "step": 1, "data": {}}
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="請輸入商品代碼："))
        return
    if text == "查詢":
        user_states[user_id] = {"action": "search", "step": 1, "data": {}}
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="請輸入商品名稱或代碼："))
        return

    if text == "刪除":
        user_states[user_id] = {"action": "delete", "step": 1, "data": {}}
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="請輸入商品代碼："))
        return

    reply = handle_command(text, user_id)
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

def handle_command(text, user):
    args = text.split()
    try:
        if args[0] == "查詢":
            return search_text(" ".join(args[1:]))
        elif args[0] == "總覽":
            return overview_text()
        elif args[0] == "補貨":
            return restock_text(args[1], int(args[2]), user)
        elif args[0] == "販售":
            return sell_text(args[1], int(args[2]), user)
        elif args[0] == "調貨":
            return transfer_text(args[1], int(args[2]), user)
        elif args[0] == "新增":
            return add_text(args[1], args[2], args[3], int(args[4]), user)
        elif args[0] == "刪除":
            return delete_text(args[1], int(args[2]), args[3], user)
        elif args[0] == "紀錄":
            return get_logs(int(args[1]) if len(args) > 1 else 5)
        else:
            return "無效指令，請使用『功能』選單或輸入完整指令"
    except Exception as e:
        return f"錯誤：{e}"

def search_text(keyword):
    data = load_inventory()
    result = ""
    for item in data.values():
        if keyword.lower() in item["code"].lower() or keyword.lower() in item["name"].lower():
            result += f"
{item['code']} - {item['name']} ({item['size']})
中心: {item['center']} 倉庫: {item['warehouse']}"
    return result.strip() if result else "找不到符合的商品"

def get_logs(n=5):
    if not os.path.exists(LOG_FILE):
        return "尚無操作紀錄"
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()
        return "".join(lines[-n:]) if lines else "尚無操作紀錄"

def handle_command(text, user):
    args = text.split()
    try:
        if args[0] == "查詢":
            return search_text(" ".join(args[1:]))
        elif args[0] == "總覽":
            return overview_text()
        elif args[0] == "補貨":
            return restock_text(args[1], int(args[2]), user)
        elif args[0] == "販售":
            return sell_text(args[1], int(args[2]), user)
        elif args[0] == "調貨":
            return transfer_text(args[1], int(args[2]), user)
        elif args[0] == "新增":
            return add_text(args[1], args[2], args[3], int(args[4]), user)
        elif args[0] == "刪除":
            return delete_text(args[1], int(args[2]), args[3], user)
        elif args[0] == "紀錄":
            return get_logs(int(args[1]) if len(args) > 1 else 5)
        else:
            return "無效指令，請使用『功能』選單或輸入完整指令"
    except Exception as e:
        return f"錯誤：{e}"

# ===== handle_command 與其他庫存函數請保留原本內容 =====

# ===== 啟動伺服器 =====
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
