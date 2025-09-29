#!/usr/bin/env python3
import os
import json
import tempfile
import logging
from datetime import datetime, timedelta
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
import openpyxl
from apscheduler.schedulers.background import BackgroundScheduler

# ---------------- CONFIG ----------------
API_ID = int(os.getenv("API_ID", ""))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", ""))
SUB_FILE = os.getenv("SUB_FILE", "subscriptions.json")
TRIAL_LIMIT = int(os.getenv("TRIAL_LIMIT", "2"))
CREDIT = "\n\n🤖 Powered by @captainpapaji"

# ---------------- LOGGING ----------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ---------------- SESSION FILE HANDLING ----------------
SESSION_NAME = "file_bot.session"
if os.path.exists(SESSION_NAME):
    logging.info("Deleting old session to avoid sync errors...")
    os.remove(SESSION_NAME)

# ---------------- APP ----------------
app = Client(SESSION_NAME, api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ---------------- STATE ----------------
user_sessions = {}
trial_uses = {}
daily_stats = {"new_users": set(), "files_processed": 0, "features": {"split":0,"merge":0,"xlsx_txt":0,"xlsx_msg":0,"txt_xlsx":0}}

# ---------------- SUBSCRIPTION HELPERS ----------------
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
        [InlineKeyboardButton("📥 Merge TXT Files", callback_data="merge_txt")],
        [InlineKeyboardButton("📄 XLSX → TXT", callback_data="xlsx_to_txt")],
        [InlineKeyboardButton("💬 XLSX → Message List", callback_data="xlsx_to_msg")],
        [InlineKeyboardButton("📊 TXT → XLSX", callback_data="txt_to_xlsx")]
    ])

def back_btn():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back")]])

# ---------------- OWNER/ADMIN NOTIFICATIONS ----------------
async def notify_owner_text(text):
    try:
        await app.send_message(chat_id=ADMIN_ID, text=text)
    except Exception as e:
        logging.error(f"notify_owner_text failed: {e}")

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
              f"- Merge TXT: {features['merge']}\n" \
              f"- XLSX → TXT: {features['xlsx_txt']}\n" \
              f"- XLSX → Msg: {features['xlsx_msg']}\n" \
              f"- TXT → XLSX: {features['txt_xlsx']}\n\n" \
              f"⏳ Expiring Subscriptions:\n" + ("\n".join(expiring_subs) if expiring_subs else "None")
    # send to admin
    import asyncio
    asyncio.get_event_loop().create_task(notify_owner_text(summary))
    # reset daily stats
    daily_stats["new_users"].clear()
    daily_stats["files_processed"] = 0
    for k in daily_stats["features"]:
        daily_stats["features"][k] = 0

# APScheduler
scheduler = BackgroundScheduler()
scheduler.add_job(daily_summary, 'cron', hour=0, minute=0)  # midnight
scheduler.start()

# ---------------- START BOT ----------------
if __name__ == "__main__":
    print("Bot is starting...")
    app.run()
