"""
Hiro's Telegram Chatbot (Final JSONBin Persistent Version)
----------------------------------------------------------
Enhanced version with admin-only controls, flexible scheduling (supports 12h or 24h formats),
and broadcast targeting for specific chat IDs. Now includes admin delivery confirmations.
"""

# =========================
# 1️⃣ IMPORTS & SETUP
# =========================
import os
import json
import pytz
import random
import logging
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv
from openai import OpenAI
from telegram import Update, InputFile
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, filters
)

# =========================
# 🔒 ADMIN & TARGET CONFIG
# =========================
ADMIN_CHAT_ID = 713470736   # Your Telegram chat_id
TARGET_CHAT_ID = 512984392  # Her Telegram chat_id (for scheduled messages)

def is_authorized(update: Update) -> bool:
    """Check if the user is the admin (you)."""
    return update.message.chat_id == ADMIN_CHAT_ID


# =========================
# LOGGING SETUP
# =========================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# =========================
# 2️⃣ LOAD ENV VARIABLES
# =========================
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TELEGRAM_TOKEN:
    raise ValueError("❌ TELEGRAM_TOKEN not found in environment")
JSONBIN_API_KEY = os.getenv("JSONBIN_API_KEY")
MEMORY_BIN_ID = os.getenv("MEMORY_BIN_ID")
LOGS_BIN_ID = os.getenv("LOGS_BIN_ID")
SCHEDULES_BIN_ID = os.getenv("SCHEDULES_BIN_ID")

MODEL_ID = "ft:gpt-4o-mini-2024-07-18:hiro-personal::CUF00Odk"
client = OpenAI(api_key=OPENAI_API_KEY)
SGT = pytz.timezone("Asia/Singapore")

# =========================
# 3️⃣ JSONBIN HELPERS
# =========================
def jsonbin_url(bin_id):
    return f"https://api.jsonbin.io/v3/b/{bin_id}"

def load_json_from_bin(bin_id):
    try:
        headers = {"X-Master-Key": JSONBIN_API_KEY}
        r = requests.get(jsonbin_url(bin_id), headers=headers)
        if r.status_code == 200:
            return r.json()["record"].get("data", [])
    except Exception as e:
        logger.error(f"Error reading bin {bin_id}: {e}")
    return []

def save_json_to_bin(bin_id, data):
    try:
        headers = {"Content-Type": "application/json", "X-Master-Key": JSONBIN_API_KEY}
        payload = json.dumps({"data": data})
        r = requests.put(jsonbin_url(bin_id), headers=headers, data=payload)
        if r.status_code not in (200, 201):
            logger.error(f"Failed to write bin {bin_id}: {r.text}")
    except Exception as e:
        logger.error(f"Error saving bin {bin_id}: {e}")

# =========================
# 4️⃣ MEMORY & LOGGING
# =========================
def update_memory(sender, message):
    memory = load_json_from_bin(MEMORY_BIN_ID)
    memory.append({"sender": sender, "message": message})
    if len(memory) > 200:
        memory = memory[-200:]
    save_json_to_bin(MEMORY_BIN_ID, memory)

def get_memory_context():
    memory = load_json_from_bin(MEMORY_BIN_ID)
    return "\n".join([f"{m['sender']}: {m['message']}" for m in memory])

def log_message(sender, message):
    logs = load_json_from_bin(LOGS_BIN_ID)
    logs.append({
        "timestamp": datetime.now(SGT).strftime("%Y-%m-%dT%H:%M:%S"),
        "sender": sender,
        "message": message
    })
    save_json_to_bin(LOGS_BIN_ID, logs)

# =========================
# 5️⃣ /SENDLOG (Admin only)
# =========================
async def sendlog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        await update.message.reply_text("❌ You are not authorized to use this command.")
        return

    logs = load_json_from_bin(LOGS_BIN_ID)
    total_msgs = len(logs)
    last_time = logs[-1]["timestamp"] if logs else "N/A"

    summary = (
        f"📊 Chat Log Summary\n"
        f"• Total messages: {total_msgs}\n"
        f"• Last conversation: {last_time} (SGT)"
    )
    await update.message.reply_text(summary)

    temp_file = "chat_logs.json"
    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(logs, f, ensure_ascii=False, indent=2)
    await context.bot.send_document(chat_id=ADMIN_CHAT_ID, document=InputFile(temp_file))

# =========================
# 6️⃣ SCHEDULER (Admin only)
# =========================
def load_schedules():
    return load_json_from_bin(SCHEDULES_BIN_ID)

def save_schedules(data):
    save_json_to_bin(SCHEDULES_BIN_ID, data)

async def send_scheduled_messages(context: ContextTypes.DEFAULT_TYPE):
    """Check due schedules every 30s, send to her, then confirm to admin."""
    schedules = load_schedules()
    now = datetime.now(SGT)
    remaining = []

    for sched in schedules:
        send_time = datetime.fromisoformat(sched["time"])
        if send_time <= now:
            # send to HER
            await context.bot.send_message(chat_id=sched["chat_id"], text=sched["message"])
            # confirmation to YOU (admin)
            pretty_time = send_time.astimezone(SGT).strftime("%Y-%m-%d %H:%M %Z")
            confirm = f"✅ Delivered to her at {pretty_time}\nMessage: “{sched['message']}”"
            try:
                await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=confirm)
            except Exception as e:
                logger.error(f"Failed to send admin confirmation: {e}")
        else:
            remaining.append(sched)

    save_schedules(remaining)

def parse_datetime_safely(date_str, time_str):
    """Try parsing both 24-hour and 12-hour time formats (e.g., 8am or 20:00)."""
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %I%p", "%Y-%m-%d %I:%M%p"):
        try:
            return datetime.strptime(f"{date_str} {time_str}", fmt)
        except ValueError:
            continue
    raise ValueError("Invalid time format. Use HH:MM (24h) or 8am / 8:00PM style.")

async def schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        await update.message.reply_text("❌ You are not authorized to use this command.")
        return

    try:
        if len(context.args) < 3:
            await update.message.reply_text("Usage: /schedule YYYY-MM-DD HH:MM message")
            return

        date_str = context.args[0]
        time_str = context.args[1]
        message = " ".join(context.args[2:])
        send_time = SGT.localize(parse_datetime_safely(date_str, time_str))
        now = datetime.now(SGT)

        if send_time <= now:
            await update.message.reply_text("That time already pass liao 😅 choose a future time.")
            return

        data = load_schedules()
        data.append({"time": send_time.isoformat(), "chat_id": TARGET_CHAT_ID, "message": message})
        save_schedules(data)

        await update.message.reply_text(
            f"✅ Scheduled for {send_time.strftime('%Y-%m-%d %H:%M %Z')}:\n“{message}” (will be sent to her)"
        )

    except Exception as e:
        await update.message.reply_text(f"⚠️ Error: {e}")

async def listschedules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        await update.message.reply_text("❌ You are not authorized to use this command.")
        return

    schedules = load_schedules()
    if not schedules:
        await update.message.reply_text("No scheduled messages.")
        return

    text = "\n".join([f"{s['time']}: {s['message']}" for s in schedules])
    await update.message.reply_text(f"🕒 Scheduled Messages:\n{text}")

async def deleteschedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        await update.message.reply_text("❌ You are not authorized to use this command.")
        return

    save_schedules([])
    await update.message.reply_text("✅ All scheduled messages deleted.")

# =========================
# 7️⃣ IDLE MESSAGE LOADER
# =========================
def load_idle_messages():
    try:
        if os.path.exists("idle_messages.txt"):
            with open("idle_messages.txt", "r", encoding="utf-8") as f:
                return [line.strip() for line in f if line.strip()]
    except Exception as e:
        logger.error(f"Error loading idle messages: {e}")
    return ["You still there? 😊", "Thinking about you a bit 😅", "Miss chatting with you already."]

# =========================
# 8️⃣ MESSAGE HANDLER
# =========================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return  # silently ignore

    user_message = update.message.text
    log_message("Her", user_message)
    update_memory("Her", user_message)

    context_text = get_memory_context()
    response = client.chat.completions.create(
        model=MODEL_ID,
        messages=[
            {"role": "system", "content": "You are Hiro, responding naturally and warmly."},
            {"role": "user", "content": context_text + f"\nHer: {user_message}\nHiro:"}
        ],
        max_tokens=150
    )

    reply_text = response.choices[0].message.content.strip()
    log_message("HiroBot", reply_text)
    update_memory("HiroBot", reply_text)
    await update.message.reply_text(reply_text)

    if random.random() < 0.1:
        idle_reply = random.choice(load_idle_messages())
        log_message("HiroBot", idle_reply)
        update_memory("HiroBot", idle_reply)
        await update.message.reply_text(idle_reply)

# =========================
# 🔟 MAIN ENTRY POINT
# =========================
def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("schedule", schedule))
    app.add_handler(CommandHandler("listschedules", listschedules))
    app.add_handler(CommandHandler("deleteschedule", deleteschedule))
    app.add_handler(CommandHandler("sendlog", sendlog))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    job_queue = app.job_queue
    job_queue.run_repeating(send_scheduled_messages, interval=30, first=10)

    logger.info("💬 Hiro mimic bot running (SGT).")
    app.run_polling()

if __name__ == "__main__":
    main()