"""
Hiro's Telegram Chatbot (Final JSONBin Persistent Version)
----------------------------------------------------------
This bot mimics your tone using your fine-tuned OpenAI model and remembers the conversation
even after reboots using JSONBin cloud storage. It reads idle messages from a text file,
handles scheduled messages, and can send chat logs on request.
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

# Logging for visibility on Render
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# =========================
# 2️⃣ LOAD ENV VARIABLES
# =========================
# The .env file should contain:
# OPENAI_API_KEY=sk-...
# BOT_TOKEN=...
# JSONBIN_API_KEY=...
# MEMORY_BIN_ID=...
# LOGS_BIN_ID=...
# SCHEDULES_BIN_ID=...
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TELEGRAM_TOKEN:
    raise ValueError("❌ TELEGRAM_TOKEN not found in environment")
JSONBIN_API_KEY = os.getenv("JSONBIN_API_KEY")
MEMORY_BIN_ID = os.getenv("MEMORY_BIN_ID")
LOGS_BIN_ID = os.getenv("LOGS_BIN_ID")
SCHEDULES_BIN_ID = os.getenv("SCHEDULES_BIN_ID")

print("🔍 DEBUG: TELEGRAM_TOKEN loaded:", bool(os.getenv("TELEGRAM_TOKEN")))
print("🔍 DEBUG: OPENAI_API_KEY loaded:", bool(os.getenv("OPENAI_API_KEY")))
print("🔍 DEBUG: JSONBIN_API_KEY loaded:", bool(os.getenv("JSONBIN_API_KEY")))

# Fine-tuned model ID
MODEL_ID = "ft:gpt-4o-mini-2024-07-18:hiro-personal::CUF00Odk"

# Initialize OpenAI client
client = OpenAI(api_key=OPENAI_API_KEY)

# Timezone for all timestamps
SGT = pytz.timezone("Asia/Singapore")

# Telegram user ID allowed to use /sendlog
OWNER_ID = 713470736


# =========================
# 3️⃣ JSONBIN HELPERS
# =========================
# These handle cloud read/write operations so data persists through reboots.

def jsonbin_url(bin_id):
    return f"https://api.jsonbin.io/v3/b/{bin_id}"

def load_json_from_bin(bin_id):
    """Reads JSON data from JSONBin."""
    try:
        headers = {"X-Master-Key": JSONBIN_API_KEY}
        r = requests.get(jsonbin_url(bin_id), headers=headers)
        if r.status_code == 200:
            return r.json()["record"].get("data", [])
    except Exception as e:
        logger.error(f"Error reading bin {bin_id}: {e}")
    return []

def save_json_to_bin(bin_id, data):
    """Writes JSON data to JSONBin."""
    try:
        headers = {
            "Content-Type": "application/json",
            "X-Master-Key": JSONBIN_API_KEY
        }
        payload = json.dumps({"data": data})
        r = requests.put(jsonbin_url(bin_id), headers=headers, data=payload)
        if r.status_code not in (200, 201):
            logger.error(f"Failed to write bin {bin_id}: {r.text}")
    except Exception as e:
        logger.error(f"Error saving bin {bin_id}: {e}")


# =========================
# 4️⃣ MEMORY MANAGEMENT
# =========================
def update_memory(sender, message):
    """Adds message to memory (only her + bot). Keeps last 200 messages."""
    memory = load_json_from_bin(MEMORY_BIN_ID)
    memory.append({"sender": sender, "message": message})
    if len(memory) > 200:
        memory = memory[-200:]
    save_json_to_bin(MEMORY_BIN_ID, memory)

def get_memory_context():
    """Returns the conversation as text context for OpenAI."""
    memory = load_json_from_bin(MEMORY_BIN_ID)
    return "\n".join([f"{m['sender']}: {m['message']}" for m in memory])


# =========================
# 5️⃣ LOGGING SYSTEM
# =========================
def log_message(sender, message):
    """Logs each message with timestamp to JSONBin."""
    logs = load_json_from_bin(LOGS_BIN_ID)
    logs.append({
        "timestamp": datetime.now(SGT).strftime("%Y-%m-%dT%H:%M:%S"),
        "sender": sender,
        "message": message
    })
    save_json_to_bin(LOGS_BIN_ID, logs)


# =========================
# 6️⃣ /SENDLOG COMMAND
# =========================
async def sendlog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends chat log summary and file (owner-only)."""
    user_id = update.message.from_user.id
    if user_id != OWNER_ID:
        await update.message.reply_text("You’re not authorized to use this command.")
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

    # Save logs temporarily to send as a file
    temp_file = "chat_logs.json"
    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(logs, f, ensure_ascii=False, indent=2)
    await context.bot.send_document(chat_id=OWNER_ID, document=InputFile(temp_file))


# =========================
# 7️⃣ SCHEDULER FUNCTIONS
# =========================
def load_schedules():
    return load_json_from_bin(SCHEDULES_BIN_ID)

def save_schedules(data):
    save_json_to_bin(SCHEDULES_BIN_ID, data)

async def send_scheduled_messages(context: ContextTypes.DEFAULT_TYPE):
    """Sends due messages every 30 seconds."""
    schedules = load_schedules()
    now = datetime.now(SGT)
    remaining = []

    for sched in schedules:
        send_time = datetime.fromisoformat(sched["time"])
        if send_time <= now:
            await context.bot.send_message(chat_id=sched["chat_id"], text=sched["message"])
        else:
            remaining.append(sched)

    save_schedules(remaining)

async def schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/schedule <minutes> <message>"""
    try:
        minutes = int(context.args[0])
        message = " ".join(context.args[1:])
        send_time = datetime.now(SGT) + timedelta(minutes=minutes)
        data = load_schedules()
        data.append({"time": send_time.isoformat(), "chat_id": update.message.chat_id, "message": message})
        save_schedules(data)
        await update.message.reply_text(f"Scheduled message in {minutes} minutes.")
    except Exception as e:
        await update.message.reply_text(f"Usage: /schedule <minutes> <message>\nError: {e}")

async def listschedules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    schedules = load_schedules()
    if not schedules:
        await update.message.reply_text("No scheduled messages.")
        return
    text = "\n".join([f"{s['time']}: {s['message']}" for s in schedules])
    await update.message.reply_text(f"🕒 Scheduled Messages:\n{text}")

async def deleteschedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    save_schedules([])
    await update.message.reply_text("All scheduled messages deleted.")


# =========================
# 8️⃣ LOAD IDLE MESSAGES
# =========================
def load_idle_messages():
    """Reads idle messages from idle_messages.txt (one per line)."""
    try:
        if os.path.exists("idle_messages.txt"):
            with open("idle_messages.txt", "r", encoding="utf-8") as f:
                lines = [line.strip() for line in f.readlines() if line.strip()]
                if lines:
                    return lines
    except Exception as e:
        logger.error(f"Error loading idle messages: {e}")

    # Default fallback messages if file missing
    return [
        "You still there? 😊",
        "Thinking about you a bit 😅",
        "Miss chatting with you already."
    ]


# =========================
# 9️⃣ MESSAGE HANDLER
# =========================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles incoming user messages and replies with fine-tuned model."""
    user_message = update.message.text

    # Log + update memory
    log_message("Her", user_message)
    update_memory("Her", user_message)

    # Retrieve conversation history
    context_text = get_memory_context()

    # Get reply from OpenAI
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

    # Idle message chance (10%)
    if random.random() < 0.1:
        idle_msgs = load_idle_messages()
        idle_reply = random.choice(idle_msgs)
        log_message("HiroBot", idle_reply)
        update_memory("HiroBot", idle_reply)
        await update.message.reply_text(idle_reply)


# =========================
# 🔟 MAIN ENTRY POINT
# =========================
def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("schedule", schedule))
    app.add_handler(CommandHandler("listschedules", listschedules))
    app.add_handler(CommandHandler("deleteschedule", deleteschedule))
    app.add_handler(CommandHandler("sendlog", sendlog))

    # Messages
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Schedule job every 30 seconds
    job_queue = app.job_queue
    job_queue.run_repeating(send_scheduled_messages, interval=30, first=10)

    logger.info("💬 Hiro mimic bot running (SGT).")
    app.run_polling()   # ✅ No "await" needed here!


if __name__ == "__main__":
    main()