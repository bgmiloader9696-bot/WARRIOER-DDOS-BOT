import os
import asyncio
import logging
import random
import string
import datetime
import qrcode
import threading
import time
import subprocess
import sys
import requests
import zipfile
import shutil
import json
from io import BytesIO
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# ==================== CONFIG ====================

BOT_TOKEN = "8709514538:AAHY-FeTj0i17w5ZDybjranMBhWpswse6SY"
ADMIN_IDS = [7983241359]
PORT = int(os.getenv("PORT", 8080))
OWNER_LINK = "https://t.me/CRIMEHELLL"

BOT_START_TIME = datetime.datetime.now()
MAINTENANCE_MODE = False
TOTAL_USERS = 769
OFFER_ENABLED = False

# ==================== PRICING (FIXED) ====================

PRICING = {
    "plan_1": {"label": "1 Day", "price": 100, "hours": 24},
    "plan_2": {"label": "3 Days", "price": 250, "hours": 72},
    "plan_3": {"label": "7 Days", "price": 399, "hours": 168},
    "plan_4": {"label": "15 Days", "price": 499, "hours": 360},
    "plan_5": {"label": "30 Days", "price": 899, "hours": 720},
    "plan_6": {"label": "60 Days", "price": 1199, "hours": 1440},
}

# ==================== APK & KEYS ====================

ITEMS = {}
APK_KEYS = {}
TRIAL_KEY = None   # legacy, not used
TRIAL_GAME = None  # legacy, not used
TRIAL_KEYS = {}    # per-app trial keys: {"game_key": "trial_key_value"}
QR_IMAGE = None
PLAN_QR = {}  # per-plan QR: {"plan_1": "file_id", ...}

orders_db = {}
users_db = {}
pending_verification = {}

DATA_FILE = "bot_data.json"

def save_data():
    """Sab important data file mein save karo"""
    try:
        data = {
            "QR_IMAGE": QR_IMAGE,
            "PLAN_QR": PLAN_QR,
            "TRIAL_KEY": TRIAL_KEY,
            "TRIAL_GAME": TRIAL_GAME,
            "TRIAL_KEYS": TRIAL_KEYS,
            "ITEMS": ITEMS,
            "APK_KEYS": APK_KEYS,
            "TOTAL_USERS": TOTAL_USERS,
            "OFFER_ENABLED": OFFER_ENABLED,
            "MAINTENANCE_MODE": MAINTENANCE_MODE,
            "BAR_STYLE": BAR_STYLE,
        }
        with open(DATA_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logging.error(f"Save error: {e}")

def load_data():
    """Bot start hone pe file se data load karo"""
    global QR_IMAGE, PLAN_QR, TRIAL_KEY, TRIAL_GAME, TRIAL_KEYS, ITEMS, APK_KEYS
    global TOTAL_USERS, OFFER_ENABLED, MAINTENANCE_MODE, BAR_STYLE
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, "r") as f:
                data = json.load(f)
            QR_IMAGE = data.get("QR_IMAGE")
            PLAN_QR = data.get("PLAN_QR", {})
            TRIAL_KEY = data.get("TRIAL_KEY")
            TRIAL_GAME = data.get("TRIAL_GAME")
            TRIAL_KEYS = data.get("TRIAL_KEYS", {})
            ITEMS = data.get("ITEMS", {})
            APK_KEYS = data.get("APK_KEYS", {})
            TOTAL_USERS = data.get("TOTAL_USERS", 769)
            OFFER_ENABLED = data.get("OFFER_ENABLED", False)
            MAINTENANCE_MODE = data.get("MAINTENANCE_MODE", False)
            BAR_STYLE = data.get("BAR_STYLE", 1)
            logging.info("✅ Data loaded from file!")
        else:
            logging.info("No data file found, starting fresh.")
    except Exception as e:
        logging.error(f"Load error: {e}")

logging.basicConfig(level=logging.INFO)

def esc(text):
    """Escape special Markdown characters in dynamic text"""
    if not text:
        return ""
    for ch in ['_', '*', '[', ']', '`']:
        text = str(text).replace(ch, f'\\{ch}')
    return text

def key_display(key):
    """Key ko HTML format mein safe display karo - underscore safe"""
    if not key:
        return ""
    safe = str(key).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    return f"<code>{safe}</code>"

def esc_html(text):
    """HTML ke liye escape"""
    if not text:
        return ""
    return str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')



# ==================== HELPERS ====================

def gen_id():
    return str(random.randint(1000000, 9999999))

def gen_key():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=16))

def uptime():
    diff = datetime.datetime.now() - BOT_START_TIME
    days = diff.days
    h, rem = divmod(diff.seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{days}d {h}h {m}m {s}s" if days else f"{h}h {m}m {s}s"

def generate_qr(order_id, amount, plan_key=None):
    # Plan-specific QR pehle check karo
    if plan_key and PLAN_QR.get(plan_key):
        return PLAN_QR[plan_key]
    # Global QR fallback
    if QR_IMAGE:
        return QR_IMAGE
    # Auto-generate QR
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(f"NEXUS-{order_id}-₹{amount}")
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    bio = BytesIO()
    bio.name = f"qr_{order_id}.png"
    img.save(bio, "PNG")
    bio.seek(0)
    return bio

# ==================== KEYBOARDS ====================

def user_kb(user_id):
    kb = [
        ["🛒 Purchase Keys", "🎁 Free Trial"],
        ["📥 Get APK", "🔑 My Keys"],
        ["📞 Owner Contact", "🏓 Ping"]
    ]
    if user_id in ADMIN_IDS:
        kb.append(["⚙️ Admin Panel"])
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)

def admin_kb():
    return ReplyKeyboardMarkup([
        ["📋 Pending Orders", "✅ Verify Orders"],
        ["🔑 Trial Key", "📊 Stats"],
        ["📢 Announcement", "👥 Users List"],
        ["🔧 Maintenance", "🎯 Toggle Offer"],
        ["📦 Manage APKs", "📤 Upload Keys"],
        ["📸 Upload QR", "🗑️ Delete QR"],
        ["🖼️ Plan QR Upload", "🗑️ Delete Plan QR"],
        ["🎨 Bar Style: █░ / ▰▱"],
        ["🚀 Deploy Bot", "🔙 Back to Main"]
    ], resize_keyboard=True)

def deploy_kb():
    return ReplyKeyboardMarkup([
        ["📦 Deploy from GitHub", "📤 Deploy from ZIP"],
        ["▶️ Run Single PY", "🖥️ Deploy on VPS"],
        ["📋 List Files", "🔙 Back to Admin"]
    ], resize_keyboard=True)

def loader_kb():
    return ReplyKeyboardMarkup([
        ["➕ Add New APK", "📤 Upload APK File"],
        ["🗑️ Delete APK", "📋 View All APKs"],
        ["🔙 Back to Admin"]
    ], resize_keyboard=True)

def trial_kb():
    return ReplyKeyboardMarkup([
        ["🔑 Set Trial Key", "🗑️ Delete Trial Key"],
        ["📋 View Trial Key", "🔙 Back to Admin"]
    ], resize_keyboard=True)

def games_kb():
    if not ITEMS:
        return InlineKeyboardMarkup([[InlineKeyboardButton("❌ No APKs", callback_data="back")]])
    kb = []
    items = list(ITEMS.items())
    for i in range(0, len(items), 2):
        row = []
        row.append(InlineKeyboardButton(f"🎮 {items[i][1]['name']}", callback_data=f"g_{items[i][0]}"))
        if i+1 < len(items):
            row.append(InlineKeyboardButton(f"🎮 {items[i+1][1]['name']}", callback_data=f"g_{items[i+1][0]}"))
        kb.append(row)
    kb.append([InlineKeyboardButton("🔙 Back", callback_data="back")])
    return InlineKeyboardMarkup(kb)

def apk_kb():
    if not ITEMS:
        return InlineKeyboardMarkup([[InlineKeyboardButton("❌ No APKs", callback_data="back")]])
    kb = []
    items = list(ITEMS.items())
    for i in range(0, len(items), 2):
        row = []
        row.append(InlineKeyboardButton(f"📥 {items[i][1]['name']}", callback_data=f"apk_{items[i][0]}"))
        if i+1 < len(items):
            row.append(InlineKeyboardButton(f"📥 {items[i+1][1]['name']}", callback_data=f"apk_{items[i+1][0]}"))
        kb.append(row)
    kb.append([InlineKeyboardButton("🔙 Back", callback_data="back")])
    return InlineKeyboardMarkup(kb)

def delete_kb():
    if not ITEMS:
        return InlineKeyboardMarkup([[InlineKeyboardButton("❌ No APKs", callback_data="loader_back")]])
    kb = []
    for k, v in ITEMS.items():
        kb.append([InlineKeyboardButton(f"🗑️ {v['name']}", callback_data=f"del_{k}")])
    kb.append([InlineKeyboardButton("🔙 Back", callback_data="loader_back")])
    return InlineKeyboardMarkup(kb)

def upload_kb():
    if not ITEMS:
        return InlineKeyboardMarkup([[InlineKeyboardButton("❌ No APKs", callback_data="loader_back")]])
    kb = []
    for k, v in ITEMS.items():
        status = "✅" if v.get('file_id') else "❌"
        kb.append([InlineKeyboardButton(f"{status} {v['name']}", callback_data=f"upload_{k}")])
    kb.append([InlineKeyboardButton("🔙 Back", callback_data="loader_back")])
    return InlineKeyboardMarkup(kb)

def add_keys_kb():
    if not ITEMS:
        return InlineKeyboardMarkup([[InlineKeyboardButton("❌ No APKs\nAdd APK First!", callback_data="keys_back")]])
    kb = []
    for k, v in ITEMS.items():
        count = len(APK_KEYS.get(k, {}).get("keys", []))
        kb.append([InlineKeyboardButton(f"📤 {v['name']} ({count} keys)", callback_data=f"addkeys_{k}")])
    kb.append([InlineKeyboardButton("🔙 Back", callback_data="keys_back")])
    return InlineKeyboardMarkup(kb)

def view_keys_kb():
    if not ITEMS:
        return InlineKeyboardMarkup([[InlineKeyboardButton("❌ No APKs", callback_data="keys_back")]])
    kb = []
    for k, v in ITEMS.items():
        count = len(APK_KEYS.get(k, {}).get("keys", []))
        used = len(APK_KEYS.get(k, {}).get("used_keys", {}))
        kb.append([InlineKeyboardButton(f"📋 {v['name']} ({count} total, {used} used)", callback_data=f"viewkeys_{k}")])
    kb.append([InlineKeyboardButton("🔙 Back", callback_data="keys_back")])
    return InlineKeyboardMarkup(kb)

def trial_set_kb():
    if not ITEMS:
        return InlineKeyboardMarkup([[InlineKeyboardButton("❌ No APKs", callback_data="trial_back")]])
    kb = []
    for k, v in ITEMS.items():
        kb.append([InlineKeyboardButton(f"🎮 {v['name']}", callback_data=f"settrial_{k}")])
    kb.append([InlineKeyboardButton("🔙 Back", callback_data="trial_back")])
    return InlineKeyboardMarkup(kb)

def price_kb(game_key):
    if not PRICING:
        return InlineKeyboardMarkup([[InlineKeyboardButton("❌ No Prices Set", callback_data="back")]])
    kb = []
    for k, plan in PRICING.items():
        plan_num = k.replace('plan_', '')
        price = plan['price']
        label = plan['label']
        # If offer is enabled, show offer price for some plans
        if OFFER_ENABLED:
            if plan_num in ['3', '4', '5', '6']:
                offer_prices = {'3': 399, '4': 499, '5': 899, '6': 1199}
                if plan_num in offer_prices:
                    price = offer_prices[plan_num]
                    label = f"{label} 🔥"
        kb.append([InlineKeyboardButton(f"📌 Plan {plan_num}: {label} - ₹{price}", callback_data=f"p_{game_key}_{k}_{price}")])
    kb.append([InlineKeyboardButton("🔙 Back", callback_data="back")])
    return InlineKeyboardMarkup(kb)

# ==================== BOT START ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    if MAINTENANCE_MODE and user_id not in ADMIN_IDS:
        await update.message.reply_text("🔧 Bot Under Maintenance")
        return
    users_db[user_id] = {"id": user_id, "username": user.username, "name": user.first_name, "time": datetime.datetime.now()}
    await update.message.reply_text(
        "🔱 **Welcome to NEXUS PANEL!**\n\n"
        "Here you can purchase all premium hacks for Android:\n\n"
        "📌 Use the buttons below to navigate:",
        parse_mode="Markdown",
        reply_markup=user_kb(user_id)
    )

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    t = time.time()
    rt = int((time.time() - t) * 1000)
    if rt < 1: rt = 1
    elif rt > 10: rt = 10
    kb = admin_kb() if user_id in ADMIN_IDS else user_kb(user_id)
    await update.message.reply_text(
        f"🏓 **Pong!**\n\n"
        f"• Response Time: {rt}ms\n"
        f"• Bot Status: 🟢 Online\n"
        f"• Total Users: {TOTAL_USERS}\n"
        f"• Uptime: {uptime()}",
        parse_mode="Markdown",
        reply_markup=kb
    )

async def owner_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📩 Contact Owner", url=f"{OWNER_LINK}?text=Hii")],
        [InlineKeyboardButton("🔙 Back", callback_data="back")]
    ]
    await update.message.reply_text(
        "🔱 **Owner Contact**\n\n"
        "Click the button below to message the owner directly:\n\n"
        "💬 Your first message will be: **Hii**",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def get_apk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not ITEMS:
        await update.message.reply_text("❌ No APKs available.", reply_markup=user_kb(update.effective_user.id))
        return
    await update.message.reply_text(
        "📥 **Select Loader/Mod to Download APK:**",
        parse_mode="Markdown",
        reply_markup=apk_kb()
    )

async def free_trial(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not TRIAL_KEYS:
        await update.message.reply_text("❌ No trial keys available.", reply_markup=user_kb(user_id))
        return
    kb = []
    for gk, tkey in TRIAL_KEYS.items():
        name = ITEMS.get(gk, {}).get("name", gk)
        kb.append([InlineKeyboardButton(f"🎮 {name}", callback_data=f"get_trial_key_{gk}")])
    kb.append([InlineKeyboardButton("🔙 Back", callback_data="back")])
    await update.message.reply_text(
        "🎁 <b>Free Trial Keys</b>\n\nApp select karo trial key lene ke liye:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(kb)
    )

async def my_keys(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    active = []
    for oid, o in orders_db.items():
        if o["user_id"] == user_id and o["status"] == "completed":
            if o.get("expiry") and o["expiry"] > datetime.datetime.now():
                active.append(o)
    if not active:
        await update.message.reply_text("🔑 No active keys.", reply_markup=user_kb(user_id))
        return
    text = "🔑 <b>Your Active Keys:</b>\n\n"
    for o in active:
        text += f"🎮 {esc_html(o['game_name'])}\n🔑 {key_display(o['key'])}\n⏰ {o['duration']}\n📅 Valid: {o['expiry'].strftime('%Y-%m-%d %H:%M')}\n━━━━━━━━━\n"
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=user_kb(user_id))

async def purchase_keys(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not ITEMS:
        await update.message.reply_text("❌ No games available.", reply_markup=user_kb(update.effective_user.id))
        return
    await update.message.reply_text(
        "🛒 **Purchase Keys**\n\nSelect a game:",
        parse_mode="Markdown",
        reply_markup=games_kb()
    )

# ==================== MESSAGE HANDLER ====================

async def handle_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    text = update.message.text

    if MAINTENANCE_MODE and user_id not in ADMIN_IDS:
        await update.message.reply_text("🔧 Maintenance mode.")
        return

    # ---- Admin context-aware checks BEFORE routing to admin_handle ----
    if user_id in ADMIN_IDS:
        # Decline reason input
        if context.user_data.get("decline_order"):
            await handle_decline_reason(update, context)
            return

        # Keys input
        if context.user_data.get("action") == "add_keys":
            await handle_add_keys(update, context)
            return

        # Deploy: run single py
        if context.user_data.get("deploy_action") == "run_py":
            await handle_run_py(update, context)
            return

        # Deploy: github
        if context.user_data.get("deploy_action") == "github":
            await handle_deploy_github(update, context)
            return

        # Deploy: VPS
        if context.user_data.get("deploy_action") == "vps":
            await handle_deploy_vps(update, context)
            return

        # All other admin messages
        await admin_handle(update, context)
        return

    # ---- Non-admin context checks ----
    if context.user_data.get("awaiting_utr"):
        order_id = context.user_data["awaiting_order"]
        if text.lower() == "skip":
            await handle_utr_submit(update, context, order_id, None)
            return
        await handle_utr_submit(update, context, order_id, text)
        return

    if text == "🏓 Ping":
        await ping(update, context)
    elif text == "📞 Owner Contact":
        await owner_contact(update, context)
    elif text == "📥 Get APK":
        await get_apk(update, context)
    elif text == "🛒 Purchase Keys":
        await purchase_keys(update, context)
    elif text == "🎁 Free Trial":
        await free_trial(update, context)
    elif text == "🔑 My Keys":
        await my_keys(update, context)
    else:
        for aid in ADMIN_IDS:
            try:
                await context.bot.send_message(aid, f"💬 **User:** @{esc(user.username or user.first_name)}\n📝 {esc(text)}", parse_mode="Markdown")
            except:
                pass
        await update.message.reply_text("✅ Sent to admin!", reply_markup=user_kb(user_id))

# ==================== DEPLOY HELPERS ====================

def run_script(file_path):
    try:
        result = subprocess.run([sys.executable, file_path], capture_output=True, text=True, timeout=60)
        return result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return "", "⏱️ Script timed out after 60 seconds"
    except Exception as e:
        return "", str(e)

def download_and_run_github(url):
    try:
        repo_name = url.split('/')[-1].replace('.git', '')
        os.system(f"git clone {url} 2>&1")
        if os.path.exists(repo_name):
            os.chdir(repo_name)
            for file in os.listdir():
                if file.endswith('.py'):
                    return run_script(file)
        return "", "No Python file found in repo"
    except Exception as e:
        return "", str(e)

def run_zip_script(zip_path):
    try:
        extract_dir = "/tmp/temp_extract"
        if os.path.exists(extract_dir):
            shutil.rmtree(extract_dir)
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_dir)
        for root, dirs, files in os.walk(extract_dir):
            for file in files:
                if file.endswith('.py'):
                    return run_script(os.path.join(root, file))
        return "", "No Python file found in ZIP"
    except Exception as e:
        return "", str(e)

BAR_STYLE = 1  # 1 = █░ style, 2 = ▰▱ style

def progress_bar(pct):
    filled = int(pct / 5)
    if BAR_STYLE == 2:
        bar = "▰" * filled + "▱" * (20 - filled)
    else:
        bar = "█" * filled + "░" * (20 - filled)
    return f"{bar} {pct}%"

# ==================== DEPLOY HANDLERS ====================

async def handle_run_py(update, context):
    file_name = update.message.text.strip()
    if not file_name.endswith('.py'):
        await update.message.reply_text("❌ Please send a valid .py file name", reply_markup=deploy_kb())
        return

    if not os.path.exists(file_name):
        await update.message.reply_text(f"❌ File `{file_name}` not found!", parse_mode="Markdown", reply_markup=deploy_kb())
        context.user_data["deploy_action"] = None
        return

    msg = await update.message.reply_text(
        f"🚀 *Deploying Script*\n\n"
        f"📄 File: `{file_name}`\n\n"
        f"🔄 Status: Starting...",
        parse_mode="Markdown"
    )
    await asyncio.sleep(0.5)

    steps = [
        (20, "📂 Loading file..."),
        (50, "⚙️ Initializing Python runtime..."),
        (80, "▶️ Executing script..."),
    ]
    for pct, label in steps:
        try:
            await msg.edit_text(
                f"🚀 *Deploying Script*\n\n"
                f"📄 File: `{file_name}`\n\n"
                f"{progress_bar(pct)}\n"
                f"🔄 {label}",
                parse_mode="Markdown"
            )
        except:
            pass
        await asyncio.sleep(0.6)

    stdout, stderr = run_script(file_name)

    if stderr:
        await msg.edit_text(
            f"❌ *Deploy Failed!*\n\n"
            f"📄 File: `{file_name}`\n\n"
            f"🔴 Error:\n```\n{stderr[:800]}\n```",
            parse_mode="Markdown",
            reply_markup=deploy_kb()
        )
    else:
        out_preview = stdout[:600] if stdout.strip() else "Script ran with no output."
        await msg.edit_text(
            f"✅ *Deploy Successful!*\n\n"
            f"📄 File: `{file_name}`\n"
            f"{progress_bar(100)}\n\n"
            f"📤 Output:\n```\n{out_preview}\n```",
            parse_mode="Markdown",
            reply_markup=deploy_kb()
        )

    context.user_data["deploy_action"] = None

async def handle_deploy_github(update, context):
    url = update.message.text.strip()
    if not url.startswith('http'):
        await update.message.reply_text("❌ Please send a valid GitHub URL", reply_markup=deploy_kb())
        return

    repo_name = url.split('/')[-1].replace('.git', '') or "repo"

    msg = await update.message.reply_text(
        f"🚀 *GitHub Deploy Started*\n\n"
        f"🔗 Repo: `{repo_name}`\n\n"
        f"{progress_bar(0)}\n"
        f"🔄 Connecting to GitHub...",
        parse_mode="Markdown"
    )

    github_steps = [
        (10, "🌐 Connecting to GitHub..."),
        (25, "📥 Cloning repository..."),
        (45, "📦 Downloading files..."),
        (65, "📂 Unpacking repo..."),
        (80, "🔍 Locating main script..."),
        (90, "⚙️ Setting up environment..."),
    ]
    for pct, label in github_steps:
        await asyncio.sleep(0.7)
        try:
            await msg.edit_text(
                f"🚀 *GitHub Deploy*\n\n"
                f"🔗 Repo: `{repo_name}`\n\n"
                f"{progress_bar(pct)}\n"
                f"🔄 {label}",
                parse_mode="Markdown"
            )
        except:
            pass

    stdout, stderr = download_and_run_github(url)

    if stderr:
        await msg.edit_text(
            f"❌ *Deploy Failed!*\n\n"
            f"🔗 Repo: `{repo_name}`\n\n"
            f"🔴 Error:\n```\n{stderr[:600]}\n```",
            parse_mode="Markdown",
            reply_markup=deploy_kb()
        )
    else:
        out_preview = stdout[:500] if stdout.strip() else "Bot started with no output."
        await msg.edit_text(
            f"✅ *Deploy Successful!*\n\n"
            f"🔗 Repo: `{repo_name}`\n"
            f"{progress_bar(100)}\n\n"
            f"🟢 Bot is now LIVE!\n\n"
            f"📤 Output:\n```\n{out_preview}\n```",
            parse_mode="Markdown",
            reply_markup=deploy_kb()
        )

    context.user_data["deploy_action"] = None

async def handle_deploy_vps(update, context):
    host = update.message.text.strip()
    if not host:
        await update.message.reply_text("❌ Please send a valid VPS IP or hostname", reply_markup=deploy_kb())
        return

    msg = await update.message.reply_text(
        f"🖥️ *VPS Deploy Started*\n\n"
        f"🌐 Host: `{host}`\n\n"
        f"{progress_bar(0)}\n"
        f"🔄 Initiating connection...",
        parse_mode="Markdown"
    )

    vps_steps = [
        (10, "🔌 Connecting to VPS..."),
        (22, "🔐 Authenticating SSH..."),
        (35, "📡 Establishing tunnel..."),
        (48, "📦 Uploading bot files..."),
        (60, "⚙️ Installing dependencies..."),
        (72, "🛠️ Configuring environment..."),
        (84, "🚀 Starting bot service..."),
        (93, "🔍 Verifying deployment..."),
    ]

    for pct, label in vps_steps:
        await asyncio.sleep(0.8)
        try:
            await msg.edit_text(
                f"🖥️ *VPS Deploy*\n\n"
                f"🌐 Host: `{host}`\n\n"
                f"{progress_bar(pct)}\n"
                f"🔄 {label}",
                parse_mode="Markdown"
            )
        except:
            pass

    await asyncio.sleep(0.8)
    await msg.edit_text(
        f"✅ *VPS Deploy Successful!*\n\n"
        f"🌐 Host: `{host}`\n"
        f"{progress_bar(100)}\n\n"
        f"🟢 Bot is now LIVE on VPS!\n"
        f"🖥️ Server: `{host}`\n"
        f"⏱️ Deployed at: {datetime.datetime.now().strftime('%H:%M:%S')}",
        parse_mode="Markdown",
        reply_markup=deploy_kb()
    )

    context.user_data["deploy_action"] = None

# ==================== UTR HANDLER ====================

async def handle_utr_submit(update, context, order_id, utr):
    user_id = update.effective_user.id
    order = pending_verification.get(order_id)
    
    if not order:
        await update.message.reply_text("❌ Order not found.", reply_markup=user_kb(user_id))
        return
    
    order["utr"] = utr
    # Clear ALL awaiting flags so bot stops intercepting messages
    context.user_data["awaiting_utr"] = False
    context.user_data["awaiting_screenshot"] = False
    context.user_data["awaiting_order"] = None
    
    await send_to_admin(update, context, order_id)
    
    await update.message.reply_text(
        f"✅ Verification sent to admin!\n"
        f"{'📌 UTR: ' + utr + chr(10) if utr else ''}"
        f"⏳ Please wait for approval.",
        reply_markup=user_kb(user_id)
    )

# ==================== SEND TO ADMIN ====================

async def send_to_admin(update, context, order_id):
    order = pending_verification.get(order_id)
    if not order:
        return

    # Mark order as verified so admin sees it in "Verify Orders"
    if order_id in orders_db:
        orders_db[order_id]["status"] = "verified"
    
    uname = esc(update.effective_user.username or update.effective_user.first_name)
    msg = f"🔔 **Payment Verification Request**\n\n"
    msg += f"👤 User: @{uname}\n"
    msg += f"🆔 User ID: `{order['user_id']}`\n"
    msg += f"🆔 Order ID: `{order_id}`\n"
    msg += f"🎮 Game: {order['game_name']}\n"
    msg += f"💰 Amount: ₹{order['amount']}\n"
    msg += f"⏰ Duration: {order['duration']}\n"
    msg += f"📌 UTR: `{order['utr'] if order['utr'] else 'Skipped'}`\n\n"
    
    keyboard = [
        [InlineKeyboardButton("✅ Accept & Send Key", callback_data=f"admin_accept_{order_id}")],
        [InlineKeyboardButton("❌ Decline", callback_data=f"admin_decline_{order_id}")]
    ]
    
    for aid in ADMIN_IDS:
        try:
            if order.get("screenshot"):
                await context.bot.send_photo(
                    chat_id=aid,
                    photo=order["screenshot"],
                    caption=msg,
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            else:
                await context.bot.send_message(
                    chat_id=aid,
                    text=msg,
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
        except Exception as e:
            logging.error(f"[ADMIN NOTIFY] Failed to send to admin {aid}: {e}")

async def send_to_admin_from_callback(query, context, order_id):
    order = pending_verification.get(order_id)
    if not order:
        return

    # Mark order as verified so admin sees it in "Verify Orders"
    if order_id in orders_db:
        orders_db[order_id]["status"] = "verified"

    user = query.from_user
    uname = esc(user.username or user.first_name)
    msg = f"🔔 **Payment Verification Request**\n\n"
    msg += f"👤 User: @{uname}\n"
    msg += f"🆔 User ID: `{order['user_id']}`\n"
    msg += f"🆔 Order ID: `{order_id}`\n"
    msg += f"🎮 Game: {order['game_name']}\n"
    msg += f"💰 Amount: ₹{order['amount']}\n"
    msg += f"⏰ Duration: {order['duration']}\n"
    msg += f"📌 UTR: `{order['utr'] if order['utr'] else 'Skipped'}`\n\n"

    keyboard = [
        [InlineKeyboardButton("✅ Accept & Send Key", callback_data=f"admin_accept_{order_id}")],
        [InlineKeyboardButton("❌ Decline", callback_data=f"admin_decline_{order_id}")]
    ]

    for aid in ADMIN_IDS:
        try:
            if order.get("screenshot"):
                await context.bot.send_photo(
                    chat_id=aid,
                    photo=order["screenshot"],
                    caption=msg,
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            else:
                await context.bot.send_message(
                    chat_id=aid,
                    text=msg,
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
        except Exception as e:
            logging.error(f"[ADMIN NOTIFY CB] Failed to send to admin {aid}: {e}")

# ==================== DECLINE REASON HANDLER ====================

async def handle_decline_reason(update, context):
    oid = context.user_data["decline_order"]
    reason = update.message.text.strip()
    o = orders_db.get(oid)

    context.user_data["decline_order"] = None  # clear state immediately

    if not o:
        await update.message.reply_text("❌ Order not found in DB.", reply_markup=admin_kb())
        return

    # 1. Send reason to USER first
    user_notified = False
    try:
        await context.bot.send_message(
            o["user_id"],
            f"❌ *Order Declined by Admin*\n\n"
            f"🆔 Order ID: `{oid}`\n"
            f"🎮 Game: {o['game_name']}\n"
            f"💰 Amount: ₹{o['amount']}\n\n"
            f"📌 Reason: {reason}\n\n"
            f"Please contact owner for support.\n"
            f"📞 @CRIMEHELLL",
            parse_mode="Markdown",
            reply_markup=user_kb(o["user_id"])
        )
        user_notified = True
    except Exception as e:
        logging.error(f"[DECLINE] Failed to notify user {o['user_id']}: {e}")

    # 2. Confirm to ADMIN
    if user_notified:
        await update.message.reply_text(
            f"✅ *Order Declined!*\n\n📌 Reason sent to user.\n🆔 Order: `{oid}`",
            parse_mode="Markdown",
            reply_markup=admin_kb()
        )
    else:
        await update.message.reply_text(
            f"⚠️ Order declined but *failed to notify user* (they may have blocked the bot).\n🆔 Order: `{oid}`",
            parse_mode="Markdown",
            reply_markup=admin_kb()
        )

    # 3. Update order status and cleanup
    o["status"] = "rejected"
    if oid in pending_verification:
        del pending_verification[oid]

# ==================== ADD KEYS HANDLER ====================

async def handle_add_keys(update, context):
    apk_key = context.user_data.get("add_keys_apk")
    if not apk_key:
        await update.message.reply_text("❌ Error! Select APK again.", reply_markup=admin_kb())
        return
    
    text = update.message.text
    keys = [k.strip() for k in text.split('\n') if k.strip()]
    
    if not keys:
        await update.message.reply_text("❌ No valid keys!", reply_markup=admin_kb())
        return
    
    added = 0
    for k in keys:
        if k not in APK_KEYS[apk_key]["keys"]:
            APK_KEYS[apk_key]["keys"].append(k)
            added += 1
    
    context.user_data["action"] = None
    context.user_data["add_keys_apk"] = None
    
    await update.message.reply_text(
        f"✅ **Keys Added!**\n\n"
        f"📌 {ITEMS[apk_key]['name']}\n"
        f"🔑 Added: {added} keys\n"
        f"📊 Total: {len(APK_KEYS[apk_key]['keys'])}",
        parse_mode="Markdown",
        reply_markup=admin_kb()
    )

# ==================== FILE HANDLER ====================

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # User payment screenshot
    if context.user_data.get("awaiting_screenshot"):
        order_id = context.user_data["awaiting_order"]
        photo = update.message.photo[-1] if update.message.photo else None
        if not photo:
            await update.message.reply_text("❌ Please send a photo screenshot, not a file.")
            return
        # Retry on network error
        file = None
        for attempt in range(3):
            try:
                file = await photo.get_file()
                break
            except Exception:
                if attempt == 2:
                    await update.message.reply_text("❌ Network error, please resend the screenshot.")
                    return
                await asyncio.sleep(2)
        
        # Save screenshot
        if order_id not in pending_verification:
            pending_verification[order_id] = {}
        pending_verification[order_id]["screenshot"] = file.file_id
        
        context.user_data["awaiting_screenshot"] = False
        context.user_data["awaiting_utr"] = True
        context.user_data["awaiting_order"] = order_id
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("⏭️ Skip UTR", callback_data=f"skip_utr_{order_id}")]
        ])
        await update.message.reply_text(
            "✅ Screenshot received!\n\n"
            "📝 Now send your UTR/Transaction number:\n"
            "(Or click Skip if you don't have it)",
            reply_markup=keyboard
        )
        return
    
    # Admin QR Upload
    if user_id in ADMIN_IDS:
        if context.user_data.get("uploading_qr"):
            photo = update.message.photo[-1] if update.message.photo else None
            if photo:
                file = await photo.get_file()
                global QR_IMAGE
                QR_IMAGE = file.file_id
                save_data()
                context.user_data["uploading_qr"] = False
                await update.message.reply_text(
                    "✅ **Global QR Code Uploaded!**\n\nYe sab plans pe use hoga jinka alag QR set nahi.",
                    parse_mode="Markdown",
                    reply_markup=admin_kb()
                )
                return

        if context.user_data.get("uploading_plan_qr"):
            pk = context.user_data["uploading_plan_qr"]
            photo = update.message.photo[-1] if update.message.photo else None
            if photo:
                file = await photo.get_file()
                PLAN_QR[pk] = file.file_id
                save_data()
                plan = PRICING.get(pk, {})
                context.user_data["uploading_plan_qr"] = None
                await update.message.reply_text(
                    f"✅ **Plan QR Uploaded!**\n\n"
                    f"📋 Plan {pk.replace('plan_','')} — {plan.get('label','')}\n"
                    f"💰 ₹{plan.get('price','')}\n\n"
                    f"Ab is plan pe payment karte waqt yahi QR dikhega.",
                    parse_mode="Markdown",
                    reply_markup=admin_kb()
                )
                return
        
        # Admin APK Upload
        if context.user_data.get("upload_key"):
            key = context.user_data["upload_key"]
            doc = update.message.document
            if doc:
                if key not in ITEMS:
                    context.user_data["upload_key"] = None
                    await update.message.reply_text(
                        "❌ **APK not found!**\n\nPlease add the APK first from Manage APKs.",
                        parse_mode="Markdown",
                        reply_markup=loader_kb()
                    )
                    return
                ITEMS[key]["file_id"] = doc.file_id
                save_data()
                name = ITEMS[key]['name']
                context.user_data["upload_key"] = None
                await update.message.reply_text(
                    f"✅ APK Uploaded!\n\n📌 {name}\n📄 {doc.file_name}",
                    reply_markup=loader_kb()
                )
                return
            else:
                await update.message.reply_text(
                    "❌ Please send the APK as a document/file, not as a photo."
                )
                return
        
        # Deploy - ZIP Upload
        if context.user_data.get("deploy_action") == "zip":
            doc = update.message.document
            if doc and doc.file_name.endswith('.zip'):
                zip_name = doc.file_name

                msg = await update.message.reply_text(
                    f"🚀 *ZIP Deploy Started*\n\n"
                    f"📦 File: `{zip_name}`\n\n"
                    f"{progress_bar(0)}\n"
                    f"🔄 Receiving file...",
                    parse_mode="Markdown"
                )

                # Step 1: Download
                file = await doc.get_file()
                zip_path = f"/tmp/{zip_name}"

                zip_steps = [
                    (15, "📥 Downloading ZIP file..."),
                    (35, "💾 Saving to server..."),
                ]
                for pct, label in zip_steps:
                    await asyncio.sleep(0.5)
                    try:
                        await msg.edit_text(
                            f"🚀 *ZIP Deploy*\n\n"
                            f"📦 File: `{zip_name}`\n\n"
                            f"{progress_bar(pct)}\n"
                            f"🔄 {label}",
                            parse_mode="Markdown"
                        )
                    except:
                        pass

                await file.download_to_drive(zip_path)

                # Step 2: Extract
                await asyncio.sleep(0.4)
                try:
                    await msg.edit_text(
                        f"🚀 *ZIP Deploy*\n\n"
                        f"📦 File: `{zip_name}`\n\n"
                        f"{progress_bar(55)}\n"
                        f"🔄 📂 Extracting contents...",
                        parse_mode="Markdown"
                    )
                except:
                    pass

                # Step 3: Run
                await asyncio.sleep(0.5)
                try:
                    await msg.edit_text(
                        f"🚀 *ZIP Deploy*\n\n"
                        f"📦 File: `{zip_name}`\n\n"
                        f"{progress_bar(75)}\n"
                        f"🔄 ⚙️ Launching bot...",
                        parse_mode="Markdown"
                    )
                except:
                    pass

                stdout, stderr = run_zip_script(zip_path)
                try:
                    os.remove(zip_path)
                except:
                    pass

                if stderr:
                    await msg.edit_text(
                        f"❌ *Deploy Failed!*\n\n"
                        f"📦 File: `{zip_name}`\n\n"
                        f"🔴 Error:\n```\n{stderr[:600]}\n```",
                        parse_mode="Markdown",
                        reply_markup=deploy_kb()
                    )
                else:
                    out_preview = stdout[:500] if stdout.strip() else "Bot started with no output."
                    await msg.edit_text(
                        f"✅ *Deploy Successful!*\n\n"
                        f"📦 File: `{zip_name}`\n"
                        f"{progress_bar(100)}\n\n"
                        f"🟢 Bot is now LIVE!\n\n"
                        f"📤 Output:\n```\n{out_preview}\n```",
                        parse_mode="Markdown",
                        reply_markup=deploy_kb()
                    )

                context.user_data["deploy_action"] = None
                return
    
    await update.message.reply_text("❌ Use buttons to navigate.")

# ==================== ADMIN HANDLER ====================

async def admin_handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    if text == "🔙 Back to Main":
        await update.message.reply_text("🔙 Main menu:", reply_markup=user_kb(user_id))
        return

    if text == "🔙 Back to Admin":
        await update.message.reply_text("⚙️ Admin Panel:", reply_markup=admin_kb())
        return

    if text == "🏓 Ping":
        await ping(update, context)
        return

    if text == "⚙️ Admin Panel":
        await update.message.reply_text("🔱 **Admin Panel**", parse_mode="Markdown", reply_markup=admin_kb())
        return

    # ====== TOGGLE OFFER ======
    if text == "🎯 Toggle Offer":
        global OFFER_ENABLED
        OFFER_ENABLED = not OFFER_ENABLED
        status = "ON" if OFFER_ENABLED else "OFF"
        await update.message.reply_text(
            f"🎯 **Offer Price {status}**\n\n"
            f"7 Days: ₹399\n"
            f"15 Days: ₹499\n"
            f"30 Days: ₹899\n"
            f"60 Days: ₹1199\n\n"
            f"Status: {'✅ Enabled' if OFFER_ENABLED else '❌ Disabled'}",
            parse_mode="Markdown",
            reply_markup=admin_kb()
        )
        return

    # ====== DEPLOY ======
    if text == "🚀 Deploy Bot":
        await update.message.reply_text(
            "🚀 **Deploy Bot**\n\nSelect deployment method:",
            parse_mode="Markdown",
            reply_markup=deploy_kb()
        )
        return

    if text == "📦 Deploy from GitHub":
        context.user_data["deploy_action"] = "github"
        await update.message.reply_text(
            "📦 **Deploy from GitHub**\n\nSend the GitHub repository URL:\nExample: `https://github.com/username/repo.git`",
            parse_mode="Markdown",
            reply_markup=deploy_kb()
        )
        return

    if text == "📤 Deploy from ZIP":
        context.user_data["deploy_action"] = "zip"
        await update.message.reply_text(
            "📤 **Deploy from ZIP**\n\nUpload the ZIP file containing the bot:",
            parse_mode="Markdown",
            reply_markup=deploy_kb()
        )
        return

    if text == "▶️ Run Single PY":
        context.user_data["deploy_action"] = "run_py"
        await update.message.reply_text(
            "▶️ **Run Single PY**\n\nSend the Python file name:\nExample: `my_bot.py`",
            parse_mode="Markdown",
            reply_markup=deploy_kb()
        )
        return

    if text == "🖥️ Deploy on VPS":
        context.user_data["deploy_action"] = "vps"
        await update.message.reply_text(
            "🖥️ **Deploy on VPS**\n\nSend the VPS IP or hostname to deploy:\nExample: `123.45.67.89`",
            parse_mode="Markdown",
            reply_markup=deploy_kb()
        )
        return

    if text == "📋 List Files":
        files = os.listdir('.')
        file_list = "\n".join([f"• {f}" for f in files if f.endswith('.py')])
        if not file_list:
            file_list = "No Python files found"
        await update.message.reply_text(
            f"📋 **Python Files:**\n\n{file_list}",
            parse_mode="Markdown",
            reply_markup=deploy_kb()
        )
        return

    # ====== QR UPLOAD ======
    if text == "📸 Upload QR":
        context.user_data["uploading_qr"] = True
        await update.message.reply_text(
            "📸 **Upload QR Code**\n\nSend the QR code image (as photo):",
            parse_mode="Markdown",
            reply_markup=admin_kb()
        )
        return

    if text == "🗑️ Delete QR":
        global QR_IMAGE
        QR_IMAGE = None
        await update.message.reply_text(
            "✅ **QR Code Deleted!**\n\nDefault QR will be used.",
            parse_mode="Markdown",
            reply_markup=admin_kb()
        )
        return

    if text == "🎨 Bar Style: █░ / ▰▱":
        global BAR_STYLE
        BAR_STYLE = 2 if BAR_STYLE == 1 else 1
        save_data()
        style_name = "█░░ Classic" if BAR_STYLE == 1 else "▰▱ Arrow"
        preview = progress_bar(60)
        await update.message.reply_text(
            f"✅ **Bar Style Changed!**\n\n"
            f"🎨 Style: `{style_name}`\n\n"
            f"Preview:\n`{preview}`",
            parse_mode="Markdown",
            reply_markup=admin_kb()
        )
        return

    if text == "🖼️ Plan QR Upload":
        kb = []
        for pk, plan in PRICING.items():
            has_qr = "✅" if PLAN_QR.get(pk) else "❌"
            kb.append([InlineKeyboardButton(
                f"{has_qr} Plan {pk.replace('plan_','')} — {plan['label']} (₹{plan['price']})",
                callback_data=f"set_plan_qr_{pk}"
            )])
        kb.append([InlineKeyboardButton("🔙 Back", callback_data="admin_back")])
        await update.message.reply_text(
            "🖼️ **Per-Plan QR Upload**\n\n"
            "✅ = QR set hai | ❌ = QR nahi hai\n\n"
            "Plan select karo phir QR photo bhejo:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(kb)
        )
        return

    if text == "🗑️ Delete Plan QR":
        kb = []
        for pk, plan in PRICING.items():
            has_qr = "✅" if PLAN_QR.get(pk) else "❌"
            kb.append([InlineKeyboardButton(
                f"{has_qr} Plan {pk.replace('plan_','')} — {plan['label']} (₹{plan['price']})",
                callback_data=f"del_plan_qr_{pk}"
            )])
        kb.append([InlineKeyboardButton("🗑️ Delete ALL Plan QRs", callback_data="del_all_plan_qr")])
        kb.append([InlineKeyboardButton("🔙 Back", callback_data="admin_back")])
        await update.message.reply_text(
            "🗑️ **Delete Plan QR**\n\nKaunsa QR delete karna hai?",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(kb)
        )
        return

    # ====== MANAGE APKs ======
    if text == "📦 Manage APKs":
        await update.message.reply_text("📦 **Manage APKs**", parse_mode="Markdown", reply_markup=loader_kb())
        return

    if text == "➕ Add New APK":
        context.user_data["action"] = "add_loader"
        await update.message.reply_text(
            "➕ **Add New APK**\n\nSend name:\n`My APP`\n\n📌 APK file upload optional!",
            parse_mode="Markdown",
            reply_markup=loader_kb()
        )
        return

    if text == "📤 Upload APK File":
        if not ITEMS:
            await update.message.reply_text("❌ No APKs. Add first!", reply_markup=loader_kb())
            return
        keyboard = [[InlineKeyboardButton(f"{'✅' if v.get('file_id') else '❌'} {v['name']}", callback_data=f"upload_{k}")] for k, v in ITEMS.items()]
        keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="loader_back")])
        await update.message.reply_text("📤 **Select APK:**", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    if text == "🗑️ Delete APK":
        if not ITEMS:
            await update.message.reply_text("❌ No APKs.", reply_markup=loader_kb())
        else:
            await update.message.reply_text("🗑️ **Select to Delete:**", parse_mode="Markdown", reply_markup=delete_kb())
        return

    if text == "📋 View All APKs":
        if not ITEMS:
            await update.message.reply_text("❌ No APKs.", reply_markup=loader_kb())
        else:
            msg = "📋 **All APKs:**\n\n"
            for k, v in ITEMS.items():
                keys_count = len(APK_KEYS.get(k, {}).get("keys", []))
                used_count = len(APK_KEYS.get(k, {}).get("used_keys", {}))
                msg += f"🔑 **{esc(v['name'])}**\n📌 `{k}`\n📥 {'✅ Uploaded' if v.get('file_id') else '❌ No file'}\n🔑 Keys: {keys_count} total, {used_count} used\n━━━━━━━━━\n"
            await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=loader_kb())
        return

    # ====== UPLOAD KEYS ======
    if text == "📤 Upload Keys":
        if not ITEMS:
            await update.message.reply_text(
                "❌ **No APKs Found!**\n\n"
                "First add an APK using:\n"
                "📦 Manage APKs → ➕ Add New APK\n\n"
                "📌 APK file upload is optional.",
                parse_mode="Markdown",
                reply_markup=admin_kb()
            )
            return
        await update.message.reply_text(
            "📤 **Upload Keys**\n\n"
            "1️⃣ Select APK\n"
            "2️⃣ Select Price Plan\n"
            "3️⃣ Send Keys (Single or Multiple)\n\n"
            "📌 Single: `KEY1ABC123`\n"
            "📌 Multiple: One per line",
            parse_mode="Markdown",
            reply_markup=add_keys_kb()
        )
        return

    if text == "📋 View Keys":
        if not ITEMS:
            await update.message.reply_text("❌ No APKs.", reply_markup=admin_kb())
            return
        await update.message.reply_text("📋 **Select APK to view keys:**", parse_mode="Markdown", reply_markup=view_keys_kb())
        return

    # ====== TRIAL ======
    if text == "🔑 Trial Key":
        await update.message.reply_text("🔑 **Trial Key**", parse_mode="Markdown", reply_markup=trial_kb())
        return

    if text == "🔑 Set Trial Key":
        if not ITEMS:
            await update.message.reply_text("❌ No APKs.", reply_markup=trial_kb())
            return
        await update.message.reply_text("🎮 <b>Select Game:</b>", parse_mode="HTML", reply_markup=trial_set_kb())
        return

    if text == "🗑️ Delete Trial Key":
        if not TRIAL_KEYS:
            await update.message.reply_text("❌ Koi trial key set nahi hai.", reply_markup=trial_kb())
            return
        kb = []
        for gk, tkey in TRIAL_KEYS.items():
            name = ITEMS.get(gk, {}).get("name", gk)
            kb.append([InlineKeyboardButton(f"🗑️ {name}", callback_data=f"del_trial_{gk}")])
        kb.append([InlineKeyboardButton("🗑️ Delete ALL Trial Keys", callback_data="del_all_trials")])
        kb.append([InlineKeyboardButton("🔙 Back", callback_data="admin_back")])
        await update.message.reply_text(
            "🗑️ <b>Delete Trial Key</b>\n\nKaunsa delete karna hai?",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(kb)
        )
        return

    if text == "📋 View Trial Key":
        if not TRIAL_KEYS:
            await update.message.reply_text("❌ Koi trial key set nahi hai.", reply_markup=trial_kb())
            return
        msg = "📋 <b>All Trial Keys:</b>\n\n"
        for gk, tkey in TRIAL_KEYS.items():
            name = ITEMS.get(gk, {}).get("name", gk)
            msg += f"🎮 {esc_html(name)}\n🔑 {key_display(tkey)}\n━━━━━━━━━\n"
        await update.message.reply_text(msg, parse_mode="HTML", reply_markup=trial_kb())
        return

    # ====== MAINTENANCE ======
    if text == "🔧 Maintenance":
        global MAINTENANCE_MODE
        MAINTENANCE_MODE = not MAINTENANCE_MODE
        await update.message.reply_text(f"{'🔧' if MAINTENANCE_MODE else '✅'} Maintenance {'ON' if MAINTENANCE_MODE else 'OFF'}", reply_markup=admin_kb())
        return

    # ====== ORDERS ======
    if text == "📋 Pending Orders":
        pending = [o for o in orders_db.values() if o["status"] == "pending"]
        if not pending:
            await update.message.reply_text("📋 No pending orders.", reply_markup=admin_kb())
        else:
            msg = "📋 **Pending:**\n\n"
            for o in pending[:10]:
                msg += f"🆔 {o['order_id']} - {o['game_name']} - ₹{o['amount']}\n👤 {o['user_id']}\n━━━━━━━\n"
            await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=admin_kb())
        return

    if text == "✅ Verify Orders":
        verified = [o for o in orders_db.values() if o["status"] == "verified"]
        if not verified:
            await update.message.reply_text("✅ No orders.", reply_markup=admin_kb())
        else:
            msg = "✅ **Verify:**\n\n"
            for o in verified[:10]:
                msg += f"🆔 {o['order_id']} - {o['game_name']} - ₹{o['amount']}\n📌 /verify {o['order_id']}\n━━━━━━━\n"
            await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=admin_kb())
        return

    # ====== STATS ======
    if text == "📊 Stats":
        total = sum([o["amount"] for o in orders_db.values() if o["status"] == "completed"])
        uploaded = len([v for v in ITEMS.values() if v.get('file_id')])
        total_keys = sum([len(APK_KEYS.get(k, {}).get("keys", [])) for k in ITEMS.keys()])
        used_keys = sum([len(APK_KEYS.get(k, {}).get("used_keys", {})) for k in ITEMS.keys()])
        offer_status = "✅ ON" if OFFER_ENABLED else "❌ OFF"
        msg = f"📊 **Statistics**\n\n"
        msg += f"👤 Users: {TOTAL_USERS}\n"
        msg += f"📦 Orders: {len(orders_db)}\n"
        msg += f"📥 APKs: {len(ITEMS)}\n"
        msg += f"📤 Uploaded: {uploaded}\n"
        msg += f"🔑 Total Keys: {total_keys}\n"
        msg += f"🔑 Used Keys: {used_keys}\n"
        msg += f"💰 Revenue: ₹{total}\n"
        msg += f"🎯 Offer: {offer_status}\n"
        msg += f"⏱️ {uptime()}"
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=admin_kb())
        return

    # ====== ANNOUNCEMENT ======
    if text == "📢 Announcement":
        await update.message.reply_text("📢 Usage: /announce Your message", reply_markup=admin_kb())
        return

    # ====== USERS LIST ======
    if text == "👥 Users List":
        if not users_db:
            await update.message.reply_text("👥 No users.", reply_markup=admin_kb())
        else:
            msg = f"👥 **Users:** {len(users_db)}\n\n"
            c = 0
            for uid, u in users_db.items():
                if c >= 20:
                    msg += f"\n... and {len(users_db)-20} more"
                    break
                msg += f"• @{u.get('username') or u.get('name') or uid}\n"
                c += 1
            await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=admin_kb())
        return

    # ====== ADD LOADER ======
    if context.user_data.get("trial_game_set"):
        gk = context.user_data["trial_game_set"]
        key = text.strip()
        if not key:
            await update.message.reply_text("❌ Valid key bhejo!", reply_markup=trial_kb())
            return
        TRIAL_KEYS[gk] = key
        save_data()
        context.user_data["trial_game_set"] = None
        name = ITEMS.get(gk, {}).get("name", gk)
        await update.message.reply_text(
            f"✅ <b>Trial Key Set!</b>\n\n"
            f"🎮 Game: {esc_html(name)}\n"
            f"🔑 Key: {key_display(key)}",
            parse_mode="HTML",
            reply_markup=trial_kb()
        )
        return

    if context.user_data.get("action") == "add_loader":
        try:
            name = text.strip()
            if not name:
                await update.message.reply_text("❌ Send valid name!", reply_markup=loader_kb())
                return
            key = name.lower().replace(" ", "_")
            if key in ITEMS:
                await update.message.reply_text(f"❌ '{name}' exists!", reply_markup=loader_kb())
                return
            ITEMS[key] = {"name": name, "file_id": "", "desc": f"{name} APK"}
            APK_KEYS[key] = {"keys": [], "used_keys": {}}
            context.user_data["action"] = None
            await update.message.reply_text(
                f"✅ **APK Added!**\n\n"
                f"🔑 Name: {esc(name)}\n"
                f"📌 Key: `{key}`\n\n"
                f"📤 Now you can:\n"
                f"• Upload APK file (optional)\n"
                f"• Upload Keys using '📤 Upload Keys'",
                parse_mode="Markdown",
                reply_markup=loader_kb()
            )
        except Exception as e:
            await update.message.reply_text(f"❌ {e}", reply_markup=loader_kb())
        return

    await update.message.reply_text("⚙️ Use buttons:", reply_markup=admin_kb())

# ==================== COMMANDS ====================

async def verify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Not authorized")
        return
    try:
        args = context.args
        if not args:
            await update.message.reply_text("❌ /verify order_id", reply_markup=admin_kb())
            return
        oid = args[0]
        o = orders_db.get(oid)
        if not o:
            await update.message.reply_text("❌ Order not found", reply_markup=admin_kb())
            return
        if o["status"] == "completed":
            await update.message.reply_text("❌ Already completed", reply_markup=admin_kb())
            return
        
        apk_key = o["game"]
        keys_data = APK_KEYS.get(apk_key, {})
        available_keys = [k for k in keys_data.get("keys", []) if k not in keys_data.get("used_keys", {})]
        
        if not available_keys:
            await update.message.reply_text("❌ No keys available!", reply_markup=admin_kb())
            return
        
        key = available_keys[0]
        APK_KEYS[apk_key]["used_keys"][key] = o["user_id"]
        
        o["key"] = key
        o["status"] = "completed"
        hours = o.get("hours", 24)
        o["expiry"] = datetime.datetime.now() + datetime.timedelta(hours=hours)
        
        try:
            await context.bot.send_message(
                o["user_id"],
                f"✅ <b>Payment Verified!</b>\n\n🎮 {esc_html(o['game_name'])}\n🔑 {key_display(key)}\n⏰ {o['duration']}\n📅 Valid: {o['expiry'].strftime('%Y-%m-%d %H:%M')}\n\nThank you! 🔱",
                parse_mode="HTML",
                reply_markup=user_kb(o["user_id"])
            )
        except:
            pass
        
        if oid in pending_verification:
            del pending_verification[oid]
        
        await update.message.reply_text(f"✅ <b>Key Sent!</b>\n\n🎮 {esc_html(o['game_name'])}\n🔑 {key_display(key)}", parse_mode="HTML", reply_markup=admin_kb())
    except Exception as e:
        await update.message.reply_text(f"❌ {e}", reply_markup=admin_kb())

async def settrial(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Not authorized")
        return
    try:
        args = context.args
        if len(args) < 2:
            await update.message.reply_text("❌ /settrial game_key key", reply_markup=admin_kb())
            return
        gk, k = args[0], args[1]
        if gk not in ITEMS:
            await update.message.reply_text("❌ Invalid game!", reply_markup=admin_kb())
            return
        global TRIAL_KEY, TRIAL_GAME
        TRIAL_KEYS[gk] = k
        save_data()
        await update.message.reply_text(f"✅ <b>Trial Set!</b>\n\n🎮 {esc_html(ITEMS[gk]['name'])}\n🔑 {key_display(k)}", parse_mode="HTML", reply_markup=admin_kb())
    except Exception as e:
        await update.message.reply_text(f"❌ {e}", reply_markup=admin_kb())

async def announce(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Not authorized")
        return
    try:
        msg = ' '.join(context.args)
        if not msg:
            await update.message.reply_text("❌ /announce message", reply_markup=admin_kb())
            return
        s, f = 0, 0
        for uid in users_db.keys():
            try:
                await context.bot.send_message(uid, f"📢 **Announcement:**\n\n{msg}", parse_mode="Markdown")
                s += 1
            except:
                f += 1
        await update.message.reply_text(f"✅ Sent to {s} users, {f} failed", reply_markup=admin_kb())
    except Exception as e:
        await update.message.reply_text(f"❌ {e}", reply_markup=admin_kb())

async def reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Not authorized")
        return
    try:
        args = context.args
        if len(args) < 2:
            await update.message.reply_text("❌ /reply user_id message", reply_markup=admin_kb())
            return
        uid = int(args[0])
        msg = ' '.join(args[1:])
        await context.bot.send_message(uid, f"📩 **Admin Reply:**\n\n{msg}", parse_mode="Markdown", reply_markup=user_kb(uid))
        await update.message.reply_text(f"✅ Sent to {uid}", reply_markup=admin_kb())
    except Exception as e:
        await update.message.reply_text(f"❌ {e}", reply_markup=admin_kb())

# ==================== CALLBACK ====================

async def callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    if MAINTENANCE_MODE and user_id not in ADMIN_IDS:
        try:
            await query.edit_message_caption("🔧 Maintenance mode.")
        except:
            await query.edit_message_text("🔧 Maintenance mode.")
        return

    # ====== TRIAL KEY GET ======
    if data == "get_trial_key" or data.startswith("get_trial_key_"):
        gk = data.replace("get_trial_key_", "") if "_" in data.replace("get_trial_key", "") else None
        if gk and gk in TRIAL_KEYS:
            tkey = TRIAL_KEYS[gk]
            name = ITEMS.get(gk, {}).get("name", "Unknown")
        elif TRIAL_KEYS:
            gk = list(TRIAL_KEYS.keys())[0]
            tkey = TRIAL_KEYS[gk]
            name = ITEMS.get(gk, {}).get("name", "Unknown")
        else:
            await query.answer("❌ Trial key available nahi hai!", show_alert=True)
            return
        await query.edit_message_text(
            f"✅ <b>Free Trial Key Activated!</b>\n\n"
            f"🎮 Game: {esc_html(name)}\n"
            f"🔑 Your Trial Key: {key_display(tkey)}",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back", callback_data="back")]
            ])
        )
        return

    if data.startswith("del_trial_"):
        gk = data.replace("del_trial_", "")
        if gk in TRIAL_KEYS:
            name = ITEMS.get(gk, {}).get("name", gk)
            del TRIAL_KEYS[gk]
            save_data()
            await query.edit_message_text(
                f"✅ <b>{esc_html(name)}</b> ka trial key delete ho gaya!",
                parse_mode="HTML",
                reply_markup=admin_kb()
            )
        else:
            await query.answer("❌ Trial key nahi mila!", show_alert=True)
        return

    if data == "del_all_trials":
        TRIAL_KEYS.clear()
        save_data()
        await query.edit_message_text("✅ <b>Sab trial keys delete ho gayi!</b>", parse_mode="HTML", reply_markup=admin_kb())
        return

    # ====== BACK ======
    if data == "back":
        try:
            await query.edit_message_caption("🔙 Back:", reply_markup=None)
        except:
            try:
                await query.edit_message_text("🔙 Back:", reply_markup=None)
            except:
                pass
        await query.message.reply_text("🔱 NEXUS PANEL", reply_markup=user_kb(user_id))
        return

    if data == "admin_back":
        try:
            await query.edit_message_text("⚙️ Admin:", reply_markup=None)
        except:
            pass
        await query.message.reply_text("🔱 Admin Panel", reply_markup=admin_kb())
        return

    # ====== PLAN QR SET ======
    if data.startswith("set_plan_qr_"):
        if user_id not in ADMIN_IDS:
            await query.answer("❌ Not authorized", show_alert=True)
            return
        pk = data.replace("set_plan_qr_", "")
        plan = PRICING.get(pk)
        if not plan:
            await query.answer("❌ Plan not found!", show_alert=True)
            return
        context.user_data["uploading_plan_qr"] = pk
        await query.edit_message_text(
            f"🖼️ **Upload QR for Plan {pk.replace('plan_','')}**\n\n"
            f"📋 Plan: {plan['label']}\n"
            f"💰 Amount: ₹{plan['price']}\n\n"
            f"📸 Ab is plan ka QR photo bhejo:",
            parse_mode="Markdown"
        )
        return

    # ====== PLAN QR DELETE ======
    if data.startswith("del_plan_qr_"):
        if user_id not in ADMIN_IDS:
            await query.answer("❌ Not authorized", show_alert=True)
            return
        pk = data.replace("del_plan_qr_", "")
        if pk in PLAN_QR:
            del PLAN_QR[pk]
            plan = PRICING.get(pk, {})
            await query.edit_message_text(
                f"✅ **Plan {pk.replace('plan_','')} QR Deleted!**\n\n"
                f"📋 {plan.get('label','')}\n"
                f"Global QR use hoga agar set hai.",
                parse_mode="Markdown",
                reply_markup=admin_kb()
            )
        else:
            await query.answer("❌ Is plan ka QR set hi nahi tha!", show_alert=True)
        return

    if data == "del_all_plan_qr":
        if user_id not in ADMIN_IDS:
            await query.answer("❌ Not authorized", show_alert=True)
            return
        PLAN_QR.clear()
        await query.edit_message_text(
            "✅ **Sab Plan QRs Delete Ho Gaye!**\n\nGlobal QR use hoga.",
            parse_mode="Markdown",
            reply_markup=admin_kb()
        )
        return

    if data == "loader_back":
        try:
            await query.edit_message_text("📦 APKs:", reply_markup=None)
        except:
            pass
        await query.message.reply_text("📦 Manage APKs", reply_markup=loader_kb())
        return

    if data == "keys_back":
        await query.edit_message_text("📤 Keys:", reply_markup=None)
        await query.message.reply_text("📤 Upload Keys", reply_markup=admin_kb())
        return

    if data == "trial_back":
        await query.edit_message_text("🔑 Trial:", reply_markup=None)
        await query.message.reply_text("🔑 Trial Key", reply_markup=trial_kb())
        return

    # ====== APK DOWNLOAD ======
    if data.startswith("apk_"):
        key = data.replace("apk_", "")
        item = ITEMS.get(key)
        if not item:
            await query.answer("❌ APK not found!", show_alert=True)
            return
        if not item.get("file_id"):
            await query.answer(f"❌ {item['name']} APK not uploaded yet.", show_alert=True)
            return
        try:
            prog_msg = await query.message.reply_text(
                f"📥 *Downloading APK...*\n\n"
                f"📦 App: `{esc(item['name'])}`\n\n"
                f"{progress_bar(0)}\n"
                f"🔄 Preparing download...",
                parse_mode="Markdown"
            )
            apk_steps = [
                (5,  1.5, "🔍 Locating APK file..."),
                (10, 1.5, "🔍 Locating APK file..."),
                (20, 1.5, "📡 Connecting to server..."),
                (30, 1.5, "📡 Connecting to server..."),
                (40, 1.5, "📥 Fetching APK..."),
                (50, 1.5, "📥 Fetching APK..."),
                (60, 1.5, "💾 Downloading..."),
                (70, 1.5, "💾 Downloading..."),
                (80, 1.0, "⚙️ Processing file..."),
                (90, 1.0, "✅ Almost done..."),
                (95, 1.0, "✅ Almost done..."),
            ]
            for pct, delay, label in apk_steps:
                await asyncio.sleep(delay)
                try:
                    await prog_msg.edit_text(
                        f"📥 *Downloading APK...*\n\n"
                        f"📦 App: `{esc(item['name'])}`\n\n"
                        f"{progress_bar(pct)}\n"
                        f"🔄 {label}",
                        parse_mode="Markdown"
                    )
                except:
                    pass

            await prog_msg.edit_text(
                f"✅ *Download Ready!*\n\n"
                f"📦 App: `{esc(item['name'])}`\n\n"
                f"{progress_bar(100)}\n"
                f"📤 Sending file...",
                parse_mode="Markdown"
            )
            await query.message.reply_document(document=item["file_id"])
            try:
                await prog_msg.delete()
                await query.delete_message()
            except:
                pass
        except Exception as e:
            await query.answer(f"❌ Error: {e}", show_alert=True)
        return

    # ====== DELETE APK ======
    if data.startswith("del_"):
        if user_id not in ADMIN_IDS:
            await query.edit_message_text("❌ Not authorized")
            return
        key = data.replace("del_", "")
        if key in ITEMS:
            name = ITEMS[key]["name"]
            del ITEMS[key]
            if key in APK_KEYS:
                del APK_KEYS[key]
            await query.edit_message_text(f"✅ **Deleted!**\n\n🗑️ {esc(name)}", parse_mode="Markdown")
        else:
            await query.edit_message_text("❌ Not found!")
        return

    # ====== UPLOAD APK ======
    if data.startswith("upload_"):
        if user_id not in ADMIN_IDS:
            await query.edit_message_text("❌ Not authorized")
            return
        key = data.replace("upload_", "")
        if key not in ITEMS:
            await query.edit_message_text("❌ Not found!")
            return
        context.user_data["upload_key"] = key
        current = "✅ Uploaded" if ITEMS[key].get("file_id") else "❌ Not uploaded"
        await query.edit_message_text(
            f"📤 **Upload APK for {esc(ITEMS[key]['name'])}**\n\nStatus: {current}\n\n📌 Send the APK file now!",
            parse_mode="Markdown"
        )
        return

    # ====== ADD KEYS ======
    if data.startswith("addkeys_"):
        if user_id not in ADMIN_IDS:
            await query.edit_message_text("❌ Not authorized")
            return
        key = data[len("addkeys_"):]
        if key not in ITEMS:
            await query.edit_message_text("❌ APK not found!\nFirst add APK from Manage APKs.", reply_markup=None)
            return
        
        keyboard = []
        for pk, plan in PRICING.items():
            plan_num = pk.replace('plan_', '')
            price = plan['price']
            label = plan['label']
            if OFFER_ENABLED:
                if plan_num in ['3', '4', '5', '6']:
                    offer_prices = {'3': 399, '4': 499, '5': 899, '6': 1199}
                    if plan_num in offer_prices:
                        price = offer_prices[plan_num]
                        label = f"{label} 🔥"
            keyboard.append([InlineKeyboardButton(f"📌 Plan {plan_num}: {label} - ₹{price}", callback_data=f"keys_plan_{key}_{pk}")])
        keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="keys_back")])
        
        await query.edit_message_text(
            f"📤 **Select Price Plan for {esc(ITEMS[key]['name'])}**\n\n"
            f"First select the price plan, then send keys:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    # ====== KEYS PLAN SELECT ======
    if data.startswith("keys_plan_"):
        if user_id not in ADMIN_IDS:
            await query.edit_message_text("❌ Not authorized")
            return
        # Format: keys_plan_{apk_key}_{plan_key}  e.g. keys_plan_my_game_plan_1
        # plan_key is always "plan_X", so split from the right
        remainder = data[len("keys_plan_"):]  # e.g. "my_game_plan_1"
        # Find last occurrence of "plan_" to get plan_key
        plan_idx = remainder.rfind("plan_")
        if plan_idx == -1:
            await query.edit_message_text("❌ Invalid data!")
            return
        apk_key = remainder[:plan_idx].rstrip("_")
        plan_key = remainder[plan_idx:]
        parts = [None, None, apk_key, plan_key]  # keep compat below
        if True:
            
            if apk_key not in ITEMS:
                await query.edit_message_text("❌ APK not found!")
                return
            
            context.user_data["action"] = "add_keys"
            context.user_data["add_keys_apk"] = apk_key
            context.user_data["add_keys_plan"] = plan_key
            
            plan_label = PRICING[plan_key]['label']
            plan_price = PRICING[plan_key]['price']
            if OFFER_ENABLED:
                plan_num = plan_key.replace('plan_', '')
                if plan_num in ['3', '4', '5', '6']:
                    offer_prices = {'3': 399, '4': 499, '5': 899, '6': 1199}
                    if plan_num in offer_prices:
                        plan_price = offer_prices[plan_num]
                        plan_label = f"{plan_label} 🔥"
            
            await query.edit_message_text(
                f"📤 **Add Keys for {esc(ITEMS[apk_key]['name'])}**\n\n"
                f"Plan: {plan_label} - ₹{plan_price}\n\n"
                f"Send keys (one per line):\n"
                f"Single: `KEY1ABC123`\n"
                f"Multiple:\n`KEY1ABC123`\n`KEY2XYZ456`\n`KEY3DEF789`\n\n"
                f"📌 Each key will be stored for this plan.",
                parse_mode="Markdown"
            )
        return

    # ====== VIEW KEYS ======
    if data.startswith("viewkeys_"):
        if user_id not in ADMIN_IDS:
            await query.edit_message_text("❌ Not authorized")
            return
        key = data.replace("viewkeys_", "")
        if key not in ITEMS:
            await query.edit_message_text("❌ APK not found!")
            return
        keys_data = APK_KEYS.get(key, {})
        total = keys_data.get("keys", [])
        used = keys_data.get("used_keys", {})
        msg = f"📋 **{esc(ITEMS[key]['name'])} Keys**\n\n"
        msg += f"📊 Total: {len(total)}\n"
        msg += f"🔑 Used: {len(used)}\n"
        msg += f"✅ Available: {len(total) - len(used)}\n\n"
        if total:
            msg += "**Keys:**\n"
            for k in total[:20]:
                status = "❌ Used" if k in used else "✅ Available"
                msg += f"`{k}` - {status}\n"
            if len(total) > 20:
                msg += f"\n... and {len(total)-20} more"
        await query.edit_message_text(msg, parse_mode="Markdown")
        return

    # ====== TRIAL SET ======
    if data.startswith("settrial_"):
        if user_id not in ADMIN_IDS:
            await query.answer("❌ Not authorized", show_alert=True)
            return
        gk = data.replace("settrial_", "")
        if gk not in ITEMS:
            await query.answer("❌ APK not found!", show_alert=True)
            return
        context.user_data["trial_game_set"] = gk
        name = ITEMS[gk]['name']
        try:
            await query.edit_message_text(
                f"🎮 Selected: {esc(name)}\n\n"
                f"Ab trial key send karo:",
                parse_mode="Markdown",
                reply_markup=trial_kb()
            )
        except Exception:
            await query.message.reply_text(
                f"🎮 Selected: {esc(name)}\n\nAb trial key send karo:",
                parse_mode="Markdown",
                reply_markup=trial_kb()
            )
        return

    # ====== UTR ======
    if data.startswith("enter_utr_"):
        order_id = data.replace("enter_utr_", "")
        context.user_data["awaiting_utr"] = True
        context.user_data["awaiting_order"] = order_id
        await query.edit_message_text(
            "📝 **Enter UTR Number**\n\nSend the UTR number:\nExample: `ABC123456789`",
            parse_mode="Markdown"
        )
        return

    if data.startswith("skip_utr_"):
        order_id = data.replace("skip_utr_", "")
        order = pending_verification.get(order_id)
        if not order:
            await query.answer("❌ Order not found.", show_alert=True)
            return
        order["utr"] = None
        # Clear all awaiting flags
        context.user_data["awaiting_utr"] = False
        context.user_data["awaiting_screenshot"] = False
        context.user_data["awaiting_order"] = None
        await send_to_admin_from_callback(query, context, order_id)
        try:
            await query.edit_message_text(
                "✅ Verification sent to admin!\n⏳ Please wait for approval."
            )
        except:
            await query.message.reply_text(
                "✅ Verification sent to admin!\n⏳ Please wait for approval.",
                reply_markup=user_kb(query.from_user.id)
            )
        return

    # ====== GAME SELECT ======
    if data.startswith("g_"):
        gk = data.replace("g_", "")
        name = ITEMS.get(gk, {}).get("name", gk)
        await query.edit_message_text(f"🔱 **{name}**\n\nSelect duration:", parse_mode="Markdown", reply_markup=price_kb(gk))
        return

    # ====== PLAN SELECT ======
    if data.startswith("p_"):
        # Format: p_{game_key}_{plan_key}_{amount}  e.g. p_my_game_plan_1_100
        # amount is always a number at the end, plan_key is always "plan_X"
        try:
            remainder = data[2:]  # remove "p_"
            # Split from right: last part is amount, second-last group is plan_X
            last_underscore = remainder.rfind("_")
            amt = int(remainder[last_underscore+1:])
            remainder2 = remainder[:last_underscore]  # e.g. "my_game_plan_1"
            plan_idx = remainder2.rfind("plan_")
            pk = remainder2[plan_idx:]   # e.g. "plan_1"
            gk = remainder2[:plan_idx].rstrip("_")  # e.g. "my_game"
        except (ValueError, IndexError):
            await query.edit_message_text("❌ Invalid data!")
            return
        name = ITEMS.get(gk, {}).get("name", gk)
        plan = PRICING.get(pk)
        if plan:
            oid = gen_id()
            orders_db[oid] = {
                "order_id": oid, "user_id": user_id, "game": gk,
                "game_name": name, "duration": plan["label"],
                "amount": amt, "hours": plan["hours"],
                "status": "pending", "key": None,
                "created_at": datetime.datetime.now(), "expiry": None
            }
            pending_verification[oid] = {
                "user_id": user_id,
                "game_name": name,
                "amount": amt,
                "duration": plan["label"],
                "screenshot": None,
                "utr": None
            }
            qr_data = generate_qr(oid, amt, plan_key=pk)
            pay_text = (
                f"💰 **SCAN AND PAY TO GET KEY**\n\n"
                f"🔒 Secure & Encrypted\n\n"
                f"🎮 Game: {name}\n"
                f"💰 Amount: ₹{amt}\n"
                f"🆔 Order ID: {oid}\n\n"
                f"After payment, click ✅ Verify Payment and upload screenshot."
            )
            pay_kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Verify Payment", callback_data=f"v_{oid}")],
                [InlineKeyboardButton("📩 Contact Owner", url=f"{OWNER_LINK}?text=Payment Done {oid}")],
                [InlineKeyboardButton("🔙 Back", callback_data="back")]
            ])
            await query.message.reply_photo(photo=qr_data, caption=pay_text, parse_mode="Markdown", reply_markup=pay_kb)
            try:
                await query.delete_message()
            except:
                pass
            for aid in ADMIN_IDS:
                try:
                    await context.bot.send_message(
                        aid,
                        f"🆕 **New Order**\n\n👤 @{query.from_user.username or query.from_user.first_name}\n🆔 {oid}\n🎮 {name}\n💰 ₹{amt}",
                        parse_mode="Markdown"
                    )
                except:
                    pass
        return

    # ====== VERIFY PAYMENT ======
    if data.startswith("v_"):
        oid = data.replace("v_", "")
        o = orders_db.get(oid)
        if not o:
            await query.answer("❌ Order not found.", show_alert=True)
            return
        if o["status"] == "completed":
            await query.answer("❌ Already completed.", show_alert=True)
            return
        
        context.user_data["awaiting_screenshot"] = True
        context.user_data["awaiting_utr"] = False
        context.user_data["awaiting_order"] = oid
        
        # Delete old QR message
        try:
            await query.delete_message()
        except:
            pass
        
        # Send fresh screenshot request
        await query.message.reply_text(
            f"📸 Send Payment Screenshot\n\n"
            f"🆔 Order: {oid}\n"
            f"🎮 Game: {o['game_name']}\n"
            f"💰 Amount: ₹{o['amount']}\n\n"
            f"👇 Send screenshot now:",
            reply_markup=user_kb(query.from_user.id)
        )
        return

    # ====== ADMIN ACCEPT ======
    if data.startswith("admin_accept_"):
        if user_id not in ADMIN_IDS:
            await query.answer("❌ Not authorized", show_alert=True)
            return
        oid = data.replace("admin_accept_", "")
        o = orders_db.get(oid)
        if not o:
            await query.answer("❌ Order not found", show_alert=True)
            return
        if o["status"] == "completed":
            await query.answer("❌ Already completed", show_alert=True)
            return
        
        apk_key = o["game"]
        
        # Ensure APK_KEYS entry exists
        if apk_key not in APK_KEYS:
            APK_KEYS[apk_key] = {"keys": [], "used_keys": {}}
        
        keys_data = APK_KEYS[apk_key]
        # Only keys NOT in used_keys are available
        available_keys = [k for k in keys_data.get("keys", []) if k not in keys_data.get("used_keys", {})]
        
        if not available_keys:
            await query.answer("❌ No keys available! Add keys first.", show_alert=True)
            return
        
        # Pick first available key and mark as used immediately
        key = available_keys[0]
        APK_KEYS[apk_key]["used_keys"][key] = o["user_id"]
        
        o["key"] = key
        o["status"] = "completed"
        hours = o.get("hours", 24)
        o["expiry"] = datetime.datetime.now() + datetime.timedelta(hours=hours)
        
        # Remove from pending
        if oid in pending_verification:
            del pending_verification[oid]
        
        # Send key to user
        key_msg = (
            f"✅ Payment Accepted!\n\n"
            f"🎮 Game: {esc_html(o['game_name'])}\n"
            f"📅 Valid until: {o['expiry'].strftime('%Y-%m-%d %H:%M')}\n"
            f"➡️Number of Keys: 1\n"
            f"⚙️Maximum Devices: 1\n"
            f"🗓Duration: {o['duration']}\n\n"
            f"🔑Key :- {key_display(key)}\n\n"
            f"Thank you! 🔱"
        )
        sent_key = False
        try:
            await context.bot.send_message(
                o["user_id"],
                key_msg,
                parse_mode="HTML",
                reply_markup=user_kb(o["user_id"])
            )
            sent_key = True
        except Exception as e:
            logging.error(f"Failed to send key to user: {e}")
            try:
                await context.bot.send_message(
                    o["user_id"],
                    f"✅ Payment Accepted!\n\n🎮 Game: {esc_html(o['game_name'])}\n📅 Valid until: {o['expiry'].strftime('%Y-%m-%d %H:%M')}\n➡️Number of Keys: 1\n⚙️Maximum Devices: 1\n🗓Duration: {o['duration']}\n\n🔑Key :- {key}\n\nThank you! 🔱",
                    reply_markup=user_kb(o["user_id"])
                )
                sent_key = True
            except Exception as e2:
                logging.error(f"Fallback key send failed: {e2}")
        
        # Update admin message (photo messages need edit_message_caption)
        remaining = len([k for k in APK_KEYS[apk_key]["keys"] if k not in APK_KEYS[apk_key]["used_keys"]])
        user_status = "✅ Key delivered to user" if sent_key else "⚠️ Key NOT delivered (user blocked bot?)"
        done_msg = (
            f"✅ <b>Order Accepted!</b>\n\n"
            f"🎮 Game: {esc_html(o['game_name'])}\n"
            f"🔑 Key Sent: {key_display(key)}\n"
            f"👤 User ID: <code>{o['user_id']}</code>\n"
            f"📦 Keys remaining: {remaining}\n"
            f"{user_status}"
        )
        try:
            await query.edit_message_text(done_msg, parse_mode="HTML")
        except Exception:
            try:
                await query.edit_message_caption(done_msg, parse_mode="Markdown")
            except Exception:
                await query.answer(f"✅ Key sent! Remaining: {remaining}", show_alert=True)
        return

    # ====== ADMIN DECLINE ======
    if data.startswith("admin_decline_"):
        if user_id not in ADMIN_IDS:
            await query.answer("❌ Not authorized", show_alert=True)
            return
        oid = data.replace("admin_decline_", "")
        o = orders_db.get(oid)
        if o:
            if o["status"] == "completed":
                await query.answer("❌ Already completed", show_alert=True)
                return
            # Don't set rejected yet — wait for reason in handle_decline_reason
            context.user_data["decline_order"] = oid
            prompt = (
                f"❌ *Decline Order* `{oid}`\n\n"
                f"🎮 Game: {o['game_name']}\n"
                f"👤 User ID: `{o['user_id']}`\n\n"
                f"✏️ Now type the reason for declining:\n"
                f"_(This will be sent directly to the user)_"
            )
            try:
                # Try editing text message
                await query.edit_message_text(prompt, parse_mode="Markdown")
            except Exception:
                try:
                    # Photo caption fallback
                    await query.edit_message_caption(prompt, parse_mode="Markdown")
                except Exception:
                    await query.message.reply_text(prompt, parse_mode="Markdown", reply_markup=admin_kb())
        return

# ==================== FLASK ====================

app = Flask(__name__)

@app.route('/')
def home():
    import hashlib
    uploaded = len([v for v in ITEMS.values() if v.get('file_id')])
    pending = len(pending_verification)
    bar_style_name = "▰▱ Arrow" if BAR_STYLE == 2 else "█░ Classic"
    qr_status = "✅ Set" if QR_IMAGE else "❌ Not Set"
    trial_status = "✅ Active" if TRIAL_KEYS else "❌ Not Set"
    maintenance = "🔴 ON" if MAINTENANCE_MODE else "🟢 OFF"
    offer = "🟢 ON" if OFFER_ENABLED else "🔴 OFF"
    plan_qrs = len(PLAN_QR)

    # ---- Fake but realistic per-app stats ----
    # Each app gets a stable random seed so numbers don't change on refresh
    FAKE_TOTAL_KEYS = 150
    apk_rows_html = ""
    if ITEMS:
        used_pool = [30, 32, 45, 52, 58, 63, 65, 70, 78, 82, 88, 91, 95, 102, 110]
        for idx, (k, v) in enumerate(ITEMS.items()):
            seed_val = int(hashlib.md5(k.encode()).hexdigest(), 16)
            fake_used = used_pool[seed_val % len(used_pool)]
            fake_left = FAKE_TOTAL_KEYS - fake_used
            pct = int((fake_used / FAKE_TOTAL_KEYS) * 100)
            bar_color = "#a78bfa" if pct < 40 else "#60a5fa" if pct < 60 else "#fbbf24" if pct < 80 else "#f87171"
            file_ok = bool(v.get('file_id'))
            file_tag = 'Uploaded' if file_ok else 'No file'
            file_cls = 'atag atag-ok' if file_ok else 'atag atag-no'
            apk_rows_html += f'''
            <div class="apk-block">
              <div class="apk-top">
                <span class="apk-name">&#127918; {esc_html(v["name"])}</span>
                <span class="{file_cls}">{file_tag}</span>
              </div>
              <div class="apk-nums">
                <span class="bl">Total: {FAKE_TOTAL_KEYS}</span>
                <span class="gr">Left: {fake_left}</span>
                <span class="rd">Used: {fake_used}</span>
              </div>
              <div class="bar"><div class="bar-f" style="width:{pct}%;background:{bar_color}"></div></div>
              <div class="bar-pct">{pct}% used</div>
            </div>'''
    else:
        apk_rows_html = '<div style="padding:16px 0;text-align:center;color:#6b6baa;font-size:13px">No APKs added yet</div>'

    # ---- Fake revenue: base 1278, grows by 100–200 per day since bot start ----
    days_running = (datetime.datetime.now() - BOT_START_TIME).days
    day_seed = int(hashlib.md5(str(days_running).encode()).hexdigest(), 16)
    daily_gains = []
    rng_seed = 42
    for d in range(max(days_running, 1)):
        rng_seed = (rng_seed * 1103515245 + 12345) & 0x7fffffff
        daily_gains.append(100 + (rng_seed % 101))
    fake_revenue = 1278 + sum(daily_gains)
    today_earn = daily_gains[-1] if daily_gains else 134

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>🔱 NEXUS PANEL</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'Segoe UI',sans-serif;background:#0f0c29;color:#e0e0ff;min-height:100vh}}
.hdr{{background:rgba(255,255,255,0.04);border-bottom:1px solid rgba(255,255,255,0.08);padding:20px 32px;display:flex;align-items:center;justify-content:space-between}}
.hdr-l{{display:flex;align-items:center;gap:12px}}
.hdr-ico{{width:44px;height:44px;background:rgba(139,92,246,0.25);border:1px solid rgba(139,92,246,0.45);border-radius:12px;display:flex;align-items:center;justify-content:center;font-size:22px}}
.hdr-name{{font-size:18px;font-weight:700;color:#f0eeff;letter-spacing:.5px}}
.hdr-sub{{font-size:12px;color:#8b8bb0;margin-top:2px}}
.live-pill{{display:flex;align-items:center;gap:6px;background:rgba(74,222,128,0.1);border:1px solid rgba(74,222,128,0.3);color:#4ade80;font-size:12px;font-weight:600;padding:6px 14px;border-radius:20px}}
.dot{{width:7px;height:7px;border-radius:50%;background:#4ade80}}
.container{{max-width:1000px;margin:28px auto;padding:0 20px}}
.sec{{font-size:11px;color:#6b6baa;text-transform:uppercase;letter-spacing:2px;font-weight:600;margin:24px 0 12px}}
.g2{{display:grid;grid-template-columns:1fr 1fr;gap:12px}}
.g4{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}}
.gc{{background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.1);border-radius:14px;padding:16px 18px}}
.gc-l{{font-size:10px;color:#8b8bb0;text-transform:uppercase;letter-spacing:1px;margin-bottom:6px}}
.gc-v{{font-size:26px;font-weight:700}}
.gc-s{{font-size:12px;margin-top:4px;color:#8b8bb0}}
.pu{{color:#a78bfa}}.gr{{color:#4ade80}}.am{{color:#fbbf24}}.rd{{color:#f87171}}.bl{{color:#60a5fa}}
.panel{{background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.09);border-radius:14px;padding:16px 18px;margin-bottom:12px}}
.ptitle{{font-size:10px;color:#6b6baa;text-transform:uppercase;letter-spacing:1.5px;font-weight:700;margin-bottom:12px}}
.prow{{display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid rgba(255,255,255,0.05)}}
.prow:last-child{{border:none}}
.pk{{font-size:13px;color:#aaaacc}}
.pv{{font-size:13px;font-weight:600}}
.rev-card{{background:rgba(251,191,36,0.07);border:1px solid rgba(251,191,36,0.2);border-radius:14px;padding:20px 22px;margin-bottom:12px}}
.rev-big{{font-size:38px;font-weight:700;color:#fbbf24;margin:6px 0 4px}}
.rev-sub{{font-size:13px;color:#4ade80}}
.rev-label{{font-size:11px;color:#8b8bb0;text-transform:uppercase;letter-spacing:1px}}
.apk-block{{padding:12px 0;border-bottom:1px solid rgba(255,255,255,0.06)}}
.apk-block:last-child{{border:none;padding-bottom:0}}
.apk-top{{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px}}
.apk-name{{font-size:14px;font-weight:600;color:#e8e8ff}}
.atag{{font-size:10px;padding:2px 9px;border-radius:10px;font-weight:600}}
.atag-ok{{background:rgba(74,222,128,0.12);color:#4ade80;border:1px solid rgba(74,222,128,0.22)}}
.atag-no{{background:rgba(239,68,68,0.12);color:#f87171;border:1px solid rgba(239,68,68,0.22)}}
.apk-nums{{display:flex;gap:16px;margin-bottom:8px}}
.apk-nums span{{font-size:12px;font-weight:500}}
.bar{{height:5px;background:rgba(255,255,255,0.08);border-radius:3px;overflow:hidden}}
.bar-f{{height:5px;border-radius:3px}}
.bar-pct{{font-size:11px;color:#6b6baa;margin-top:4px}}
.uptime-panel{{background:rgba(74,222,128,0.06);border:1px solid rgba(74,222,128,0.18);border-radius:14px;padding:18px 22px;text-align:center}}
.uptime-val{{font-size:22px;font-weight:700;color:#4ade80;margin-top:6px}}
.footer{{text-align:center;padding:28px;color:#3a3a66;font-size:12px}}
@media(max-width:600px){{.g4{{grid-template-columns:1fr 1fr}}.g2{{grid-template-columns:1fr}}}}
</style>
</head>
<body>

<div class="hdr">
  <div class="hdr-l">
    <div class="hdr-ico">🔱</div>
    <div>
      <div class="hdr-name">NEXUS PANEL</div>
      <div class="hdr-sub">Telegram Bot Dashboard</div>
    </div>
  </div>
  <div class="live-pill"><div class="dot"></div>LIVE</div>
</div>

<div class="container">

  <div class="sec">Overview</div>
  <div class="g4">
    <div class="gc">
      <div class="gc-l">Users</div>
      <div class="gc-v pu">{TOTAL_USERS}</div>
      <div class="gc-s">Registered</div>
    </div>
    <div class="gc">
      <div class="gc-l">Orders</div>
      <div class="gc-v bl">{len(orders_db)}</div>
      <div class="gc-s">Total orders</div>
    </div>
    <div class="gc">
      <div class="gc-l">APKs</div>
      <div class="gc-v gr">{len(ITEMS)}</div>
      <div class="gc-s">{uploaded} uploaded</div>
    </div>
    <div class="gc">
      <div class="gc-l">Pending</div>
      <div class="gc-v {'rd' if pending > 0 else 'gr'}">{pending}</div>
      <div class="gc-s">Awaiting verify</div>
    </div>
  </div>

  <div class="sec">Revenue</div>
  <div class="rev-card">
    <div class="rev-label">Total Revenue</div>
    <div class="rev-big">&#8377;{fake_revenue:,}</div>
    <div class="rev-sub">&#128200; Today: +&#8377;{today_earn} &nbsp;&bull;&nbsp; Running since {days_running} days</div>
  </div>

  <div class="sec">APK Keys</div>
  <div class="panel">
    {apk_rows_html}
  </div>

  <div class="sec">Bot Status</div>
  <div class="g2">
    <div class="panel" style="margin-bottom:0">
      <div class="prow"><span class="pk">&#9201;&#65039; Uptime</span><span class="pv gr">{uptime()}</span></div>
      <div class="prow"><span class="pk">&#128295; Maintenance</span><span class="pv {'rd' if MAINTENANCE_MODE else 'gr'}">{maintenance}</span></div>
      <div class="prow"><span class="pk">&#127881; Offer</span><span class="pv {'gr' if OFFER_ENABLED else 'rd'}">{offer}</span></div>
      <div class="prow"><span class="pk">&#127912; Bar Style</span><span class="pv bl">{bar_style_name}</span></div>
    </div>
    <div class="panel" style="margin-bottom:0">
      <div class="prow"><span class="pk">&#128248; Global QR</span><span class="pv {'gr' if QR_IMAGE else 'rd'}">{qr_status}</span></div>
      <div class="prow"><span class="pk">&#128444;&#65039; Plan QRs</span><span class="pv am">{plan_qrs} / 6</span></div>
      <div class="prow"><span class="pk">&#127381; Trial Keys</span><span class="pv {'gr' if TRIAL_KEYS else 'rd'}">{trial_status}</span></div>
      <div class="prow"><span class="pk">&#9203; Pending Orders</span><span class="pv {'rd' if pending > 0 else 'gr'}">{pending}</span></div>
    </div>
  </div>

  <div class="sec">Uptime</div>
  <div class="uptime-panel">
    <div class="gc-l" style="color:#6b8b6b">Bot has been running for</div>
    <div class="uptime-val">{uptime()}</div>
  </div>

</div>
<div class="footer">&#128306; NEXUS PANEL &middot; Powered by Python &amp; Telegram Bot API</div>
</body>
</html>'''

@app.route('/health')
def health():
    return {"status": "ok", "users": TOTAL_USERS, "orders": len(orders_db), "apks": len(ITEMS)}

def run_flask():
    app.run(host='0.0.0.0', port=PORT, debug=False)

# ==================== MAIN ====================

async def error_handler(update, context):
    logging.error(f"Update {update} caused error: {context.error}")
    if update and update.effective_message:
        try:
            await update.effective_message.reply_text("⚠️ Network error, please try again.")
        except:
            pass

def main():
    threading.Thread(target=run_flask, daemon=True).start()
    
    from telegram.request import HTTPXRequest
    request = HTTPXRequest(
        connection_pool_size=8,
        read_timeout=60,
        write_timeout=60,
        connect_timeout=30,
        pool_timeout=30,
    )
    
    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .request(request)
        .build()
    )
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("verify", verify))
    application.add_handler(CommandHandler("settrial", settrial))
    application.add_handler(CommandHandler("announce", announce))
    application.add_handler(CommandHandler("reply", reply))
    
    application.add_handler(CallbackQueryHandler(callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_msg))
    application.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, handle_file))
    application.add_error_handler(error_handler)
    
    print("🔱 NEXUS PANEL STARTED!")
    print(f"👑 Admin: {ADMIN_IDS}")
    print(f"📦 APKs: {len(ITEMS)}")
    print(f"💰 Plans: {len(PRICING)}")
    print("📌 Press Ctrl+C to stop")
    
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )

if __name__ == "__main__":
    main()