#!/usr/bin/env python3
import os
import json
import tempfile
import logging
from datetime import datetime, timedelta
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
import openpyxl
from apscheduler.schedulers.background import BackgroundScheduler

# ---------------- CONFIG ----------------
API_ID = int(os.getenv("API_ID", "21845583"))
API_HASH = os.getenv("API_HASH", "081a3cc51a428ad292be0be4d4f4f975")
BOT_TOKEN = os.getenv("BOT_TOKEN", "7863454586:AAHHe-yWzUTqPW9Wjn8YhDo2K_DyZblGQHg")
ADMIN_ID = int(os.getenv("ADMIN_ID", "7597393283"))  # owner/admin
SUB_FILE = os.getenv("SUB_FILE", "subscriptions1.json")
TRIAL_LIMIT = int(os.getenv("TRIAL_LIMIT", "2"))
CREDIT = "\n\n🤖 Powered by @captainpapaji"

# ---------------- LOGGING ----------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ---------------- APP ----------------
app = Client("merged_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ---------------- STATE ----------------
user_sessions = {}   # per-user state
trial_uses = {}      # in-memory trial count
daily_stats = {"new_users": set(), "files_processed": 0, "features": {"split":0,"merge":0,"xlsx_txt":0,"xlsx_msg":0,"txt_xlsx":0}}

# ---------------- SUBSCRIPTION HELPERS ----------------
def load_subs():
    if os.path.exists(SUB_FILE):
        with open(SUB_FILE, "r") as f:
            try:
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
    except Exception:
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
        [InlineKeyboardButton("📄 XLSX → TXT", callback_data="xlsx_to_txt_menu")],
        [InlineKeyboardButton("💬 XLSX → Message List", callback_data="xlsx_to_msg_menu")],
        [InlineKeyboardButton("📊 TXT → XLSX", callback_data="txt_to_xlsx_menu")]
    ])

def back_btn():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back")]])

# ---------------- OWNER/ADMIN NOTIFICATIONS ----------------
async def notify_owner_text(client, text):
    try:
        await client.send_message(chat_id=ADMIN_ID, text=text)
    except Exception as e:
        logging.error("notify_owner_text failed: %s", e)

# ---------------- HELPERS ----------------
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

# ---------------- COMMANDS ----------------
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

# ---------------- CALLBACKS ----------------
@app.on_callback_query()
async def handle_callback(client: Client, cb: CallbackQuery):
    uid = cb.from_user.id
    if not is_subscribed(uid):
        if is_trial_allowed(uid):
            use_trial(uid)
        else:
            await cb.message.reply(unsub_msg())
            await cb.answer()
            return

    data = cb.data
    modes = {
        "split_txt": "📤 Send the `.txt` file to split.",
        "merge_txt": "🔢 How many `.txt` files to merge?",
        "xlsx_to_txt_menu": "📥 Send the `.xlsx` file to convert to TXT.",
        "xlsx_to_msg_menu": "📥 Send the `.xlsx` file to convert to message list.",
        "txt_to_xlsx_menu": "📥 Send the `.txt` file to convert to XLSX."
    }

    if data in modes:
        mode_name = data.replace("_menu","")
        user_sessions[uid] = {"mode": mode_name, "files":[]}
        await cb.message.reply(modes[data]+CREDIT, reply_markup=back_btn())

    elif data == "back":
        user_sessions[uid] = {}
        await cb.message.reply("🔙 Back to main menu:" + CREDIT, reply_markup=main_menu())

    elif data in ["by_lines","by_files"]:
        s = user_sessions.get(uid)
        if not s or "txt_file" not in s:
            await
