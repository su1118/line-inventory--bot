from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

import json, os, random, datetime

# ===== LINE Bot 設定 =====
LINE_CHANNEL_ACCESS_TOKEN = "wtWKP5aIRl79VjNO0LueW3V+c0C4IhTUGvDlwRe2TKwBwSGwrWfP35mgSKOU7Ie2dn3G9l3b85HZxovXfliCLAQwJa9B/1omWrs8hyJOftuBydYTTEt7bZP8RPmirYWC09/3rT/AH7vfXldcOJVjHgdB04t89/1O/w1cDnyilFU="
LINE_CHANNEL_SECRET = "91f81ff0defaa59d9f349fcbda672021"
line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# ===== Flask App =====
app = Flask(__name__)

# ===== 常數設定 =====
CATEGORY_CODES = {"衣物": "CL", "背包": "BA", "杯具": "CU", "帽子": "CA", "配件": "TH", "徽章磁鐵": "MA"}
SIZE_CODES = {"S": "1", "M": "2", "L": "3", "XL": "4", "2XL": "5", "3XL": "6", "4XL": "7", "5XL": "8"}
DATA_FILE = "inventory.json"
LOG_FILE = "log.txt"

# ===== 資料存取 =====
def load_inventory():
    return json.load(open(DATA_FILE, "r", encoding="utf-8")) if os.path.exists(DATA_FILE) else {}

def save_inventory(data):
    json.dump(data, open(DATA_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

def log_action(user, action):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{now}] {user}: {action}\n")

# ===== 功能實作 =====
def search_text(keyword):
    data = load_inventory()
    result = ""
    for item in data.values():
        if keyword.lower() in item["code"].lower() or keyword.lower() in item["name"].lower():
            result += f"\n{item['code']} - {item['name']} ({item['size']})\n中心: {item['center']} 倉庫: {item['warehouse']}"
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
    result = "【中心庫存】\n" + "\n".join(center_list) + "\n【倉庫庫存】\n" + "\n".join(warehouse_list)
    return result.strip()

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
    user_input = event.message.text.strip()
    user_id = event.source.user_id
    reply = handle_command(user_input, user_id)
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

# ===== 指令處理器 =====
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
        else:
            return "可用指令：\n查詢 <名稱/代碼>\n總覽\n補貨 <代碼> <數量>\n販售 <代碼> <數量>\n調貨 <代碼> <數量>\n新增 <名稱> <分類> <尺寸> <數量>\n刪除 <代碼> <數量> <中心/倉庫>"
    except Exception as e:
        return f"錯誤：{e}"

# ===== 啟動伺服器 =====
if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

