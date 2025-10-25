import os
import json
import random
import logging
import pytz
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    CommandHandler,
    ContextTypes,
    filters,
)
from openai import OpenAI
import asyncio
from dotenv import load_dotenv

load_dotenv()

# --- Logging setup ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# --- Environment variables ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

client = OpenAI(api_key=OPENAI_API_KEY)

# --- Your fine-tuned model ID (replace when ready) ---
FINE_TUNE_MODEL = "ft:gpt-4o-mini-2024-07-18:hiro-personal::CUF00Odk"

# --- Timezone setup ---
SINGAPORE_TZ = pytz.timezone("Asia/Singapore")

# --- Schedule file ---
SCHEDULE_FILE = "schedules.json"

# --- Load schedules from file ---
def load_schedules():
    if os.path.exists(SCHEDULE_FILE):
        with open(SCHEDULE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

# --- Save schedules to file ---
def save_schedules(schedules):
    with open(SCHEDULE_FILE, "w", encoding="utf-8") as f:
        json.dump(schedules, f, indent=2)

# --- Schedule handler ---
async def send_scheduled_messages(app):
    while True:
        now = datetime.now(SINGAPORE_TZ)
        schedules = load_schedules()
        remaining = []

        for s in schedules:
            send_time = datetime.fromisoformat(s["time"])
            if now >= send_time:
                try:
                    await app.bot.send_message(chat_id=s["chat_id"], text=s["message"])
                    logger.info(f"Sent scheduled message: {s['message']}")
                except Exception as e:
                    logger.error(f"Failed to send message: {e}")
            else:
                remaining.append(s)

        save_schedules(remaining)
        await asyncio.sleep(30)  # check every 30s

# --- Add new schedule command ---
async def schedule_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if len(context.args) < 3:
            await update.message.reply_text("Usage: /schedule YYYY-MM-DD HH:MM message")
            return

        date_str, time_str, *msg_parts = context.args
        message = " ".join(msg_parts)
        dt_str = f"{date_str} {time_str}"
        dt = SINGAPORE_TZ.localize(datetime.strptime(dt_str, "%Y-%m-%d %H:%M"))

        schedules = load_schedules()
        schedules.append({
            "chat_id": update.message.chat_id,
            "time": dt.isoformat(),
            "message": message
        })
        save_schedules(schedules)

        await update.message.reply_text(f"Scheduled message at {dt_str} SG time.")
        logger.info(f"New schedule added for {dt_str}: {message}")

    except Exception as e:
        await update.message.reply_text("Something went wrong, please check your format.")
        logger.error(e)

# --- List schedules command ---
async def list_schedules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    schedules = load_schedules()
    if not schedules:
        await update.message.reply_text("No scheduled messages.")
        return

    text = "\n".join(
        [f"{i+1}. {datetime.fromisoformat(s['time']).strftime('%Y-%m-%d %H:%M')} → {s['message']}"
         for i, s in enumerate(schedules)]
    )
    await update.message.reply_text("📅 Scheduled messages:\n" + text)

# --- Delete schedule command ---
async def delete_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        index = int(context.args[0]) - 1
        schedules = load_schedules()
        if 0 <= index < len(schedules):
            removed = schedules.pop(index)
            save_schedules(schedules)
            await update.message.reply_text(f"Deleted: {removed['message']}")
        else:
            await update.message.reply_text("Invalid index.")
    except Exception as e:
        await update.message.reply_text("Usage: /deleteschedule <index>")
        logger.error(e)

# --- Normal reply (fine-tuned) ---
async def reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text
    logger.info(f"Received message: {user_message}")

    # ~10% chance of sending idle message first
    if random.random() < 0.1:
        idle_messages = [
            "Hey, I'm in the middle of something right now. I’ll text you soon, okay?",
            "Sorry, I'm a little busy at the moment. Will reply properly in a bit.",
            "Give me a short while, I’ll message you soon."
        ]
        await update.message.reply_text(random.choice(idle_messages))
        return

    try:
        completion = client.chat.completions.create(
            model=FINE_TUNE_MODEL,
            messages=[
                {"role": "system", "content": "You are Hiro, replying naturally to your girlfriend in a kind and genuine tone."},
                {"role": "user", "content": user_message},
            ],
            temperature=0.8,
            max_tokens=150
        )

        reply_text = completion.choices[0].message.content.strip()
        await update.message.reply_text(reply_text)
        logger.info(f"Replied: {reply_text}")

    except Exception as e:
        logger.error(f"Error: {e}")
        await update.message.reply_text("Hmm, something went wrong just now. Try again later?")

# --- Main setup ---
async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("schedule", schedule_command))
    app.add_handler(CommandHandler("listschedules", list_schedules))
    app.add_handler(CommandHandler("deleteschedule", delete_schedule))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, reply))

    asyncio.create_task(send_scheduled_messages(app))
    logger.info("💬 Hiro mimic bot running (SGT).")
    await app.run_polling()

if __name__ == "__main__":
    import platform
    import sys
    if sys.platform == "darwin" and platform.system() == "Darwin":
        # macOS: event loop fix
        import asyncio
        try:
            asyncio.get_event_loop().run_until_complete(main())
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(main())
    else:
        asyncio.run(main())
