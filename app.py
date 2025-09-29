# bot.py
import os
import json
import asyncio
from threading import Thread
from flask import Flask
from pyrogram import Client, filters
from pyrogram.types import ReplyKeyboardMarkup, KeyboardButton
from apscheduler.schedulers.background import BackgroundScheduler
import xlsxwriter

# ----------------------------
# CONFIG
# ----------------------------
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID"))

SUB_FILE = "subs.json"
TRIAL_LIMIT = 2
trial_uses = {}

daily_stats = {"new_users": set(), "files_processed": 0, "features": {"split":0,"merge":0,"xlsx_txt":0,"xlsx_msg":0,"txt_xlsx":0}}

# ----------------------------
# CLIENT
# ----------------------------
if not os.path.exists("file_bot.session"):
    app = Client("file_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
else:
    app = Client("file_bot")

# ----------------------------
# SUBS HELPERS
# ----------------------------
def load_subs():
    if os.path.exists(SUB_FILE):
        with open(SUB_FILE, "r") as f:
            return json.load(f)
    return {}

def save_subs(data):
    with open(SUB_FILE, "w") as f:
        json.dump(data, f, indent=2)

def is_subscribed(uid):
    subs = load_subs()
    return str(uid) in subs

def is_trial_allowed(uid):
    return trial_uses.get(uid, 0) < TRIAL_LIMIT

def use_trial(uid):
    trial_uses[uid] = trial_uses.get(uid, 0) + 1

def add_sub(uid, days=30, plan="pro"):
    subs = load_subs()
    subs[str(uid)] = {"plan": plan, "days": days}
    save_subs(subs)

def remove_sub(uid):
    subs = load_subs()
    subs.pop(str(uid), None)
    save_subs(subs)

def sub_status(uid):
    if is_subscribed(uid):
        subs = load_subs()
        return subs.get(str(uid))
    return None

# ----------------------------
# FILE HELPERS
# ----------------------------
def clean_lines(lines):
    return list(dict.fromkeys([line.strip() for line in lines if line.strip()]))

def save_lines_to_txt(lines, path):
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

def save_lines_to_xlsx(lines, path):
    wb = xlsxwriter.Workbook(path)
    ws = wb.add_worksheet()
    for i, line in enumerate(lines):
        ws.write(i, 0, line)
    wb.close()

# ----------------------------
# UI HELPERS
# ----------------------------
def main_menu():
    buttons = [[KeyboardButton("📤 Upload File")],
               [KeyboardButton("📊 Check Stats"), KeyboardButton("⚙️ Plans")]]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

def back_btn():
    return ReplyKeyboardMarkup([[KeyboardButton("🔙 Back")]], resize_keyboard=True)

# ----------------------------
# COMMANDS
# ----------------------------
@app.on_message(filters.command("start"))
async def start(client, message):
    uid = message.from_user.id
    if not is_subscribed(uid) and not is_trial_allowed(uid):
        await message.reply("❌ Trial ended. Subscribe to continue.")
        return
    if not is_subscribed(uid):
        use_trial(uid)
    daily_stats["new_users"].add(uid)
    await message.reply("👋 Welcome!", reply_markup=main_menu())

@app.on_message(filters.command("checksub"))
async def check_sub(client, message):
    uid = message.from_user.id
    if is_subscribed(uid):
        status = sub_status(uid)
        await message.reply(f"✅ Subscribed ({status['plan']} plan, {status['days']} days left)")
    else:
        await message.reply(f"❌ Not subscribed. Trial remaining: {TRIAL_LIMIT - trial_uses.get(uid,0)}")

@app.on_message(filters.command("plans"))
async def plans(client, message):
    await message.reply("💳 Available plans:\n- Pro: 30 days\n- Premium: 90 days")

@app.on_message(filters.command("addsub") & filters.user(ADMIN_ID))
async def add_sub_cmd(client, message):
    try:
        uid = message.text.split()[1]
        add_sub(uid)
        await message.reply(f"✅ Subscription added for {uid}")
    except:
        await message.reply("Usage: /addsub <user_id>")

@app.on_message(filters.command("extend") & filters.user(ADMIN_ID))
async def extend_sub_cmd(client, message):
    try:
        parts = message.text.split()
        uid = parts[1]
        days = int(parts[2])
        subs = load_subs()
        if uid in subs:
            subs[uid]["days"] += days
            save_subs(subs)
            await message.reply(f"✅ Extended {uid} by {days} days")
        else:
            await message.reply("❌ User not subscribed")
    except:
        await message.reply("Usage: /extend <user_id> <days>")

@app.on_message(filters.command("removesub") & filters.user(ADMIN_ID))
async def remove_sub_cmd(client, message):
    try:
        uid = message.text.split()[1]
        remove_sub(uid)
        await message.reply(f"✅ Removed subscription for {uid}")
    except:
        await message.reply("Usage: /removesub <user_id>")

@app.on_message(filters.command("listsubs") & filters.user(ADMIN_ID))
async def list_subs(client, message):
    subs = load_subs()
    if not subs:
        await message.reply("❌ No active subscribers.")
        return
    
    msg_lines = ["📋 Active Subscribers:"]
    for uid, info in subs.items():
        plan = info.get("plan", "pro")
        days = info.get("days", 0)
        msg_lines.append(f"• User ID: {uid} — Plan: {plan}, Days Left: {days}")
    
    chunk_size = 4000
    msg_text = ""
    for line in msg_lines:
        if len(msg_text) + len(line) + 1 > chunk_size:
            await message.reply(msg_text)
            msg_text = ""
        msg_text += line + "\n"
    if msg_text:
        await message.reply(msg_text)

# ----------------------------
# FILE HANDLER
# ----------------------------
@app.on_message(filters.document)
async def handle_file(client, message):
    uid = message.from_user.id
    if not is_subscribed(uid) and not is_trial_allowed(uid):
        await message.reply("❌ Trial ended. Subscribe to continue.")
        return
    if not is_subscribed(uid):
        use_trial(uid)

    file_path = await message.download()
    daily_stats["files_processed"] += 1
    await message.reply(f"✅ File saved: {file_path}")

# ----------------------------
# DAILY SUMMARY
# ----------------------------
def daily_summary():
    try:
        stats_msg = f"📊 Daily Summary:\n- New users: {len(daily_stats['new_users'])}\n- Files processed: {daily_stats['files_processed']}"
        asyncio.run(app.send_message(ADMIN_ID, stats_msg))
        daily_stats["new_users"].clear()
        daily_stats["files_processed"] = 0
        daily_stats["features"] = {k:0 for k in daily_stats["features"]}
    except Exception as e:
        print("Failed daily summary:", e)

scheduler = BackgroundScheduler()
scheduler.add_job(daily_summary, 'cron', hour=0, minute=0)
scheduler.start()

# ----------------------------
# RUN BOT THREAD
# ----------------------------
def run_bot():
    asyncio.run(app.start())
    app.idle()

bot_thread = Thread(target=run_bot)
bot_thread.daemon = True
bot_thread.start()

# ----------------------------
# FLASK HEALTH CHECK
# ----------------------------
flask_app = Flask(__name__)

@flask_app.route("/")
def status():
    return "Bot is running ✅"

if __name__ == "__main__":
    flask_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
