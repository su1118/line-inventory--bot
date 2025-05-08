from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage,
    QuickReply, QuickReplyButton, MessageAction
)

import json, os, random, datetime

# ===== LINE Bot 設定 =====
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

app = Flask(__name__)

CATEGORY_CODES = {"衣物": "CL", "背包": "BA", "杯具": "CU", "帽子": "CA", "配件": "TH", "徽章磁鐵": "MA"}
SIZE_CODES = {"S": "1", "M": "2", "L": "3", "XL": "4", "2XL": "5", "3XL": "6", "4XL": "7", "5XL": "8"}
DATA_FILE = "inventory.json"
LOG_FILE = "log.txt"
user_states = {}

def load_inventory():
    return json.load(open(DATA_FILE, "r", encoding="utf-8")) if os.path.exists(DATA_FILE) else {}

def save_inventory(data):
    json.dump(data, open(DATA_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

def log_action(user, action):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{now}] {user}: {action}\n")

def get_function_quick_reply():
    return TextSendMessage(
        text="請選擇功能：",
        quick_reply=QuickReply(items=[
            QuickReplyButton(action=MessageAction(label="新增", text="新增")),
            QuickReplyButton(action=MessageAction(label="查詢", text="查詢")),
            QuickReplyButton(action=MessageAction(label="補貨", text="補貨")),
            QuickReplyButton(action=MessageAction(label="販售", text="販售")),
            QuickReplyButton(action=MessageAction(label="調貨", text="調貨")),
            QuickReplyButton(action=MessageAction(label="刪除", text="刪除")),
            QuickReplyButton(action=MessageAction(label="總覽", text="總覽")),
            QuickReplyButton(action=MessageAction(label="紀錄", text="紀錄"))
        ])
    )

def search_text(keyword):
    data = load_inventory()
    result = ""
    for item in data.values():
        if keyword.lower() in item["code"].lower() or keyword.lower() in item["name"].lower():
            result += f"{item['code']} - {item['name']} ({item['size']})\n中心: {item['center']} 倉庫: {item['warehouse']}\n"
    return result.strip() if result else "找不到符合的商品"

def overview_text():
    data = load_inventory()
    center_list = []
    warehouse_list = []
    for item in data.values():
        if item["center"] > 0:
            center_list.append(f"{item['code']} - {item['name']}({item['size']}): {item['center']}")
        if item["warehouse"] > 0:
            warehouse_list.append(f"{item['code']} - {item['name']}({item['size']}): {item['warehouse']}")
    return "【中心庫存】\n" + "\n".join(center_list) + "\n【倉庫庫存】\n" + "\n".join(warehouse_list)

def get_logs(n=5):
    if not os.path.exists(LOG_FILE):
        return "尚無操作紀錄"
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()
        return "".join(lines[-n:]) if lines else "尚無操作紀錄"

def restock_text(code, qty, user):
    data = load_inventory()
    if code in data:
        data[code]["warehouse"] += qty
        save_inventory(data)
        log_action(user, f"補貨 {code} 數量：{qty}")
        return f"補貨成功，目前倉庫庫存：{data[code]['warehouse']}"
    return "查無此商品代碼"

def sell_text(code, qty, user):
    data = load_inventory()
    if code in data:
        if data[code]["center"] >= qty:
            data[code]["center"] -= qty
            save_inventory(data)
            log_action(user, f"販售 {code} 數量：{qty}")
            return f"販售成功，中心剩餘庫存：{data[code]['center']}"
        else:
            return "庫存不足，請到倉庫補貨"
    return "查無此商品代碼"

def transfer_text(code, qty, user):
    data = load_inventory()
    if code in data:
        if data[code]["warehouse"] >= qty:
            data[code]["warehouse"] -= qty
            data[code]["center"] += qty
            save_inventory(data)
            log_action(user, f"調貨 {code} 數量：{qty}")
            return f"調貨成功，中心：{data[code]['center']}，倉庫：{data[code]['warehouse']}"
        else:
            return "倉庫庫存不足"
    return "查無此商品代碼"

def add_text(name, category, size, qty, user):
    data = load_inventory()
    prefix = CATEGORY_CODES.get(category, "XX")
    rand = f"{random.randint(0, 9999):04d}"
    size_code = SIZE_CODES.get(size.upper(), "9")
    code = f"{prefix}{rand}{size_code}"
    if code in data:
        return "代碼重複，請重試"
    data[code] = {
        "name": name,
        "category": category,
        "size": size.upper(),
        "code": code,
        "center": 0,
        "warehouse": qty
    }
    save_inventory(data)
    log_action(user, f"新增商品 {code}（{name}）數量：{qty}")
    return f"新增商品成功，代碼為 {code}"

def delete_text(code, qty, location, user):
    data = load_inventory()
    if code not in data:
        return "查無此商品代碼"
    if location == "中心" and data[code]["center"] >= qty:
        data[code]["center"] -= qty
    elif location == "倉庫" and data[code]["warehouse"] >= qty:
        data[code]["warehouse"] -= qty
    else:
        return "刪除失敗：數量不足或地點錯誤"
    save_inventory(data)
    log_action(user, f"刪除 {location} {code} 數量：{qty}")
    return f"刪除成功，目前{location}庫存：{data[code][location.lower()]}"

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
    elif state["action"] == "search":
        user_states.pop(user_id)
        return search_text(text)

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    text = event.message.text.strip()

    if user_id in user_states:
        reply = handle_step_input(user_id, text)
        line_bot_api.reply_message(event.reply_token, [
            TextSendMessage(text=reply),
            get_function_quick_reply()
        ])
        return

    if text.lower() in ["功能", "menu", "選單"]:
        line_bot_api.reply_message(event.reply_token, get_function_quick_reply())
        return

    actions = {
        "新增": "add", "補貨": "restock", "販售": "sell",
        "調貨": "transfer", "刪除": "delete", "查詢": "search"
    }
    if text in actions:
        user_states[user_id] = {"action": actions[text], "step": 1, "data": {}}
        prompt = "請輸入商品名稱：" if text == "新增" else "請輸入商品代碼：" if text != "查詢" else "請輸入商品名稱或代碼："
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=prompt))
        return

    reply = handle_command(text, user_id)
    line_bot_api.reply_message(event.reply_token, [
        TextSendMessage(text=reply),
        get_function_quick_reply()
    ])

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
