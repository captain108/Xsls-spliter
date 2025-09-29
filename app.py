#!/usr/bin/env python3
import os
import json
import logging
from datetime import datetime, timedelta
import asyncio
import openpyxl
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask
import threading

# ---------------- CONFIG ----------------
API_ID = int(os.getenv("API_ID", ""))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", ""))
SUB_FILE = os.getenv("SUB_FILE", "subscriptions.json")
TRIAL_LIMIT = int(os.getenv("TRIAL_LIMIT", "2"))
CREDIT = "\n\n🤖 Powered by @captainpapaji"
FLASK_PORT = int(os.getenv("PORT", 8000))
SESSION_NAME = "file_bot_new.session"

# ---------------- LOGGING ----------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ---------------- RESET SESSION ----------------
if os.path.exists(SESSION_NAME):
    logging.info("Deleting old session to avoid sync errors...")
    os.remove(SESSION_NAME)

# ---------------- INIT ----------------
app = Client(SESSION_NAME, api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
flask_app = Flask(__name__)

# ---------------- STATE ----------------
user_sessions = {}  # per-user state
trial_uses = {}     # in-memory trial count
daily_stats = {
    "new_users": set(),
    "files_processed": 0,
    "features": {"split":0,"xlsx_txt":0,"xlsx_msg":0,"txt_xlsx":0}
}

# ---------------- SUBSCRIPTION ----------------
def load_subs():
    if os.path.exists(SUB_FILE):
        try:
            with open(SUB_FILE, "r") as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_subs(data):
    with open(SUB_FILE, "w") as f:
        json.dump(data, f, indent=2)

def is_subscribed(uid):
    subs = load_subs()
    entry = subs.get(str(uid))
    if not entry:
        return False
    try:
        exp = datetime.strptime(entry["expires"], "%Y-%m-%d %H:%M:%S")
        return datetime.now() < exp
    except:
        return False

def add_sub(uid, days, plan="pro"):
    subs = load_subs()
    expiry = datetime.now() + timedelta(days=days)
    subs[str(uid)] = {"expires": expiry.strftime("%Y-%m-%d %H:%M:%S"), "plan": plan}
    save_subs(subs)

def remove_sub(uid):
    subs = load_subs()
    if str(uid) in subs:
        del subs[str(uid)]
        save_subs(subs)

def sub_status(uid):
    subs = load_subs()
    entry = subs.get(str(uid))
    if not entry:
        return "❌ No active subscription." + CREDIT
    expiry = datetime.strptime(entry["expires"], "%Y-%m-%d %H:%M:%S")
    remaining = expiry - datetime.now()
    return f"✅ Plan: {entry['plan']}\n⏳ Expires in {remaining.days} days" + CREDIT

def is_trial_allowed(uid):
    return trial_uses.get(str(uid), 0) < TRIAL_LIMIT

def use_trial(uid):
    trial_uses[str(uid)] = trial_uses.get(str(uid), 0) + 1

def unsub_msg():
    return (
        "❌ You're not subscribed or your subscription has expired.\n\n"
        "📦 Subscription Plans:\n"
        "🗓 1 Day – ₹30\n"
        "📅 1 Week – ₹180\n"
        "📆 1 Year – ₹1500\n\n"
        "💬 Contact @captainpapaji to activate." + CREDIT
    )

# ---------------- UI ----------------
def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📤 Split TXT File", callback_data="split_txt")],
        [InlineKeyboardButton("📄 XLSX → TXT", callback_data="xlsx_to_txt")],
        [InlineKeyboardButton("💬 XLSX → Message List", callback_data="xlsx_to_msg")],
        [InlineKeyboardButton("📊 TXT → XLSX", callback_data="txt_to_xlsx")]
    ])

def back_btn():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back")]])

# ---------------- NOTIFICATIONS ----------------
async def notify_owner_text(text):
    try:
        await app.send_message(chat_id=ADMIN_ID, text=text)
    except Exception as e:
        logging.error(f"notify_owner_text failed: {e}")

# ---------------- FILE HELPERS ----------------
def clean_lines(lines):
    seen = set()
    out = []
    for line in lines:
        s = line.strip()
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out

def save_lines_to_txt(lines, path):
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

def save_lines_to_xlsx(lines, path):
    wb = openpyxl.Workbook()
    ws = wb.active
    for i, v in enumerate(lines, start=1):
        ws.cell(row=i, column=1, value=v)
    wb.save(path)

# ---------------- DAILY SUMMARY ----------------
def daily_summary():
    total_users = len(load_subs())
    new_today = len(daily_stats["new_users"])
    files_processed = daily_stats["files_processed"]
    features = daily_stats["features"]

    expiring_subs = []
    subs = load_subs()
    for uid, info in subs.items():
        exp = datetime.strptime(info["expires"], "%Y-%m-%d %H:%M:%S")
        if 0 <= (exp - datetime.now()).days <= 3:
            expiring_subs.append(f"{uid} → { (exp - datetime.now()).days } days left")

    summary = f"📊 Daily Bot Summary – {datetime.now().strftime('%d %b %Y')}\n\n" \
              f"👥 Total users: {total_users}\n" \
              f"🆕 New users today: {new_today}\n" \
              f"📂 Files processed: {files_processed}\n\n" \
              f"🔥 Feature usage today:\n" \
              f"- Split TXT: {features['split']}\n" \
              f"- XLSX → TXT: {features['xlsx_txt']}\n" \
              f"- XLSX → Msg: {features['xlsx_msg']}\n" \
              f"- TXT → XLSX: {features['txt_xlsx']}\n\n" \
              f"⏳ Expiring Subscriptions:\n" + ("\n".join(expiring_subs) if expiring_subs else "None")
    asyncio.get_event_loop().create_task(notify_owner_text(summary))
    # reset daily stats
    daily_stats["new_users"].clear()
    daily_stats["files_processed"] = 0
    for k in daily_stats["features"]:
        daily_stats["features"][k] = 0

# ---------------- APScheduler ----------------
scheduler = BackgroundScheduler()
scheduler.add_job(daily_summary, 'cron', hour=0, minute=0)  # midnight
scheduler.start()

# ---------------- BOT COMMANDS ----------------
@app.on_message(filters.command("start"))
async def start(client: Client, message: Message):
    uid = message.from_user.id
    if not is_subscribed(uid) and not is_trial_allowed(uid):
        await message.reply(unsub_msg())
        return
    user_sessions[uid] = {}
    daily_stats["new_users"].add(uid)
    await message.reply("👋 Welcome! Choose an option:" + CREDIT, reply_markup=main_menu())

@app.on_message(filters.command("checksub"))
async def check_sub(client: Client, message: Message):
    await message.reply(sub_status(message.from_user.id))

@app.on_message(filters.command("plans"))
async def plans(client: Client, message: Message):
    await message.reply(unsub_msg())

@app.on_message(filters.command("addsub") & filters.user(ADMIN_ID))
async def add_sub_cmd(client: Client, message: Message):
    try:
        _, uid, days = message.text.split()
        add_sub(int(uid), int(days))
        await message.reply("✅ Subscription added." + CREDIT)
    except:
        await message.reply("❌ Usage: /addsub <user_id> <days>" + CREDIT)

@app.on_message(filters.command("extend") & filters.user(ADMIN_ID))
async def extend_sub_cmd(client: Client, message: Message):
    try:
        _, uid, days = message.text.split()
        add_sub(int(uid), int(days))
        await message.reply("✅ Subscription extended." + CREDIT)
    except:
        await message.reply("❌ Usage: /extend <user_id> <days>" + CREDIT)

@app.on_message(filters.command("removesub") & filters.user(ADMIN_ID))
async def remove_sub_cmd(client: Client, message: Message):
    try:
        _, uid = message.text.split()
        remove_sub(int(uid))
        await message.reply("🗑️ Subscription removed." + CREDIT)
    except:
        await message.reply("❌ Usage: /removesub <user_id>" + CREDIT)

@app.on_message(filters.command("listsubs") & filters.user(ADMIN_ID))
async def list_subs(client: Client, message: Message):
    subs = load_subs()
    if not subs:
        return await message.reply("📭 No active subscriptions." + CREDIT)
    msg = "👥 Active Subscribers:\n\n"
    sorted_subs = sorted(subs.items(), key=lambda x: x[1]["expires"])
    for uid, info in sorted_subs:
        try:
            user = await app.get_users(int(uid))
            name = f"{user.first_name or ''} {user.last_name or ''}".strip()
            username = f"@{user.username}" if user.username else ""
        except:
            name = "Unknown"
            username = ""
        msg += f"👤 {name} {username} ({uid}) | {info['plan']} | Expires: {info['expires']}\n"
    msg += f"\n📊 Total Subscribers: {len(subs)}" + CREDIT
    await message.reply(msg)

# ---------------- CALLBACK HANDLER ----------------
@app.on_callback_query()
async def cb_handler(client, cq):
    uid = cq.from_user.id
    data = cq.data
    if data == "back":
        await cq.message.edit_text("👋 Main Menu:" + CREDIT, reply_markup=main_menu())
        return

    if not is_subscribed(uid) and not is_trial_allowed(uid):
        await cq.message.edit_text(unsub_msg())
        return

    session = user_sessions.setdefault(uid, {})
    session["last_action"] = data

    if data == "split_txt":
        await cq.message.edit_text("📤 Send me the TXT file to split." + CREDIT, reply_markup=back_btn())
        daily_stats["features"]["split"] += 1
    elif data == "xlsx_to_txt":
        await cq.message.edit_text("📄 Send me the XLSX file to convert to TXT." + CREDIT, reply_markup=back_btn())
        daily_stats["features"]["xlsx_txt"] += 1
    elif data == "xlsx_to_msg":
        await cq.message.edit_text("💬 Send me the XLSX file to convert to message list." + CREDIT, reply_markup=back_btn())
        daily_stats["features"]["xlsx_msg"] += 1
    elif data == "txt_to_xlsx":
        await cq.message.edit_text("📊 Send me the TXT file to convert to XLSX." + CREDIT, reply_markup=back_btn())
        daily_stats["features"]["txt_xlsx"] += 1

# ---------------- FLASK STATUS ----------------
@flask_app.route("/")
def status():
    return "Bot is running ✅"

# ---------------- RUN BOTH ----------------
def run_flask():
    flask_app.run(host="0.0.0.0", port=FLASK_PORT)

def run_bot():
    print("Bot is starting...")
    app.run()

if __name__ == "__main__":
    # Start Flask in background
    threading.Thread(target=run_flask, daemon=True).start()
    # Start bot
    run_bot()
