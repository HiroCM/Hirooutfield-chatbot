"""
Hiro's Telegram Chatbot (Final JSONBin Persistent Version)
----------------------------------------------------------
Enhanced for 1:1 warmth with Jennifer (aka "babe / baby / my love"), and admin-only tools.

Highlights:
- Admin-only scheduling with inline buttons (view, edit time, edit message, delete)
- Clean list view with previews; compact UI
- One-field-per-edit flow with confirmation + Back buttons
- Sends scheduled messages ONLY to TARGET_CHAT_ID (her), with affectionate auto-ack (5–10s later)
- Human-like reply pacing: short multi-bubble responses with typing simulation
- Light tone matching & emoji sprinkle (subtle); playful but not overdone
- Debug mode: skip memory/logs for admin; toggle via /debug_on /debug_off
- /lastseen to check when she last chatted (from Logs bin)
- /help shows all commands
- Safe error handling & guardrails (SG timezone)
"""

# =========================
# 1️⃣ IMPORTS & SETUP
# =========================
import os
import json
import pytz
import time
import random
import logging
import requests
import asyncio
from datetime import datetime, timedelta
from dotenv import load_dotenv
from openai import OpenAI

from telegram.ext import Application, CommandHandler, MessageHandler, filters

from dotenv import load_dotenv
import os

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")

# ✅ Create the app instance BEFORE adding handlers
app = Application.builder().token(TOKEN).build()

from telegram import (
    Update,
    InputFile,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.constants import ChatAction
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# =========================
# 🔒 ADMIN & TARGET CONFIG
# =========================
ADMIN_CHAT_ID = 713470736   # Your Telegram chat_id
TARGET_CHAT_ID = 512984392  # Jennifer's Telegram chat_id (for ALL scheduled messages)

def is_admin(update: Update) -> bool:
    """Check if the chat is from admin (you)."""
    try:
        return (update.effective_chat and update.effective_chat.id == ADMIN_CHAT_ID)
    except Exception:
        return False

# In-memory admin edit state (simple, ephemeral)
ADMIN_STATE = {}  # {chat_id: {"mode": "edit_time"|"edit_msg", "index": int}}

# Debug mode (skip admin memory/logging when True)
DEBUG_MODE = False

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
# 3️⃣ PERSONALIZATION KNOBS
# =========================
# Nickname variants (randomly chosen per outward message to Jennifer)
NICKNAMES = ["babe", "baby", "my love" , "babycakes"]

# Light emoji palette; occasionally duplicated
EMOJIS_SOFT = ["🥺", "🥰", "❤️", "💗", "🫶", "✨", "😊"]
EMOJIS_LAUGH = ["😂", "😆", "🤣"]

# Jennifer background — edit freely (kept in system prompt)
GIRLFRIEND_PROFILE = {
    "name": "Jennifer",
    "nicknames": NICKNAMES,
    "short_bio": (
        "Loving, sensitive, and warm. She appreciates reassurance and gentle affection. "
        "She prefers being called 'babe', 'baby', or 'my love' — avoid 'Jennifer'."
        "She has 6 cats that are named 'Maya', 'Emmie', 'Jasmine', 'Narnia', 'Cookie', 'Koko'."
        "She and Hiro treats koko like their son."
        "She works as pre school teacher, and she calls her children her 'kids'."
    ),
}

# =========================
# 4️⃣ JSONBIN HELPERS
# =========================
def jsonbin_url(bin_id):
    return f"https://api.jsonbin.io/v3/b/{bin_id}"

def load_json_from_bin(bin_id):
    try:
        headers = {"X-Master-Key": JSONBIN_API_KEY}
        r = requests.get(jsonbin_url(bin_id), headers=headers, timeout=15)
        if r.status_code == 200:
            return r.json()["record"].get("data", [])
        else:
            logger.error(f"JSONBin GET {bin_id} failed: {r.status_code} {r.text}")
    except Exception as e:
        logger.error(f"Error reading bin {bin_id}: {e}")
    return []

def save_json_to_bin(bin_id, data):
    try:
        headers = {"Content-Type": "application/json", "X-Master-Key": JSONBIN_API_KEY}
        payload = json.dumps({"data": data})
        r = requests.put(jsonbin_url(bin_id), headers=headers, data=payload, timeout=15)
        if r.status_code not in (200, 201):
            logger.error(f"JSONBin PUT {bin_id} failed: {r.status_code} {r.text}")
    except Exception as e:
        logger.error(f"Error saving bin {bin_id}: {e}")

# =========================
# 5️⃣ MEMORY & LOGGING
# =========================
def update_memory(sender, message):
    """Append to memory (limit ~200)."""
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

def last_seen_from_logs() -> str:
    """Return pretty last-seen time for 'Her' based on logs."""
    logs = load_json_from_bin(LOGS_BIN_ID)
    last = None
    for row in reversed(logs):
        if row.get("sender") == "Her":
            last = row.get("timestamp")
            break
    if not last:
        return "N/A"
    try:
        dt = datetime.strptime(last, "%Y-%m-%dT%H:%M:%S")
        dt = SGT.localize(dt)
        return dt.strftime("%d %b %Y, %I:%M %p %Z")  # Singapore-friendly
    except Exception:
        return last

# =========================
# 6️⃣ SYSTEM PROMPT BUILDER
# =========================
def build_system_prompt():
    nick_str = ", ".join(GIRLFRIEND_PROFILE.get("nicknames", []))
    return (
        "You are 'Hiro' (a loving boyfriend) talking in first-person to his girlfriend on Telegram.\n"
        "You are a bot version of Hiro — be upfront if asked — but all feelings expressed are *Hiro's real feelings*.\n"
        f"About her: {GIRLFRIEND_PROFILE['short_bio']}\n"
        f"Address her as one of: {nick_str}; avoid using her full name.\n"
        "Tone: warm, reassuring, slightly playful at times; avoid overdoing flirty lines.\n"
        "Keep messages natural and human — use short messages when appropriate; occasionally send a slightly longer reflective message.\n"
        "Avoid sounding repetitive. If she seems sad or missing Hiro, increase tenderness and reassurance that Hiro will be back soon."
    )

# =========================
# 7️⃣ SCHEDULER (Admin-only)
# =========================
def load_schedules():
    return load_json_from_bin(SCHEDULES_BIN_ID)

def save_schedules(data):
    save_json_to_bin(SCHEDULES_BIN_ID, data)

def parse_datetime_safely(date_str, time_str):
    """Accept 24h 'HH:MM' or 12h '8am'/'8:30PM'."""
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %I%p", "%Y-%m-%d %I:%M%p"):
        try:
            return datetime.strptime(f"{date_str} {time_str}", fmt)
        except ValueError:
            continue
    raise ValueError("Invalid time. Use 24h HH:MM or 12h like 8am / 8:30PM.")

# Affectionate auto-ack variants (sent 5–10s after scheduled msg)
ACK_VARIANTS = [
    "Just wanted you to know this is really me talking through the bot, {nick} — I’ll be back on the 29th evening. Promise.",
    "That came straight from my heart, {nick}. I can’t wait to see you on the 29th night.",
    "Reading your reply means a lot to me, {nick}. Counting down to the 29th evening together.",
    "If you’re feeling lonely, hold on to me a little longer, {nick}. I’m back on the 29th evening.",
    "I’m always with you in spirit, {nick}. See you 29th evening — I miss you so much.",
    "Thank you for reading that, {nick}. I’m coming back to you on the 29th evening.",
    "It’s me, your Hiro, always. Hang in there till the 29th evening, {nick}.",
    "I love you, {nick}. I’ll be back on the 29th evening — one day closer every minute.",
]

def pick_nickname():
    return random.choice(NICKNAMES)

def sprinkle_emojis(text: str) -> str:
    """Occasionally add single/double/triple emojis; keep subtle."""
    roll = random.random()
    if roll < 0.6:
        return text  # most messages unchanged
    palette = EMOJIS_SOFT if random.random() < 0.8 else EMOJIS_LAUGH
    emo = random.choice(palette)
    repeat = 1 if random.random() < 0.7 else (2 if random.random() < 0.9 else 3)
    return f"{text} {' '.join([emo]*repeat)}"

async def send_scheduled_messages(context: ContextTypes.DEFAULT_TYPE):
    """Every 30s: deliver due messages to her, then confirm to admin and auto-ack to her."""
    schedules = load_schedules()
    now = datetime.now(SGT)
    remaining = []

    for idx, sched in enumerate(schedules):
        try:
            send_time = datetime.fromisoformat(sched["time"])
        except Exception:
            logger.error(f"Bad schedule time at index {idx}: {sched!r}")
            continue

        if send_time <= now:
            # Deliver to HER only
            try:
                text = sched["message"]
                await context.bot.send_message(chat_id=TARGET_CHAT_ID, text=text)
                # Auto-ack after 5–10 seconds
                await asyncio.sleep(random.randint(5, 10))
                ack = random.choice(ACK_VARIANTS).format(nick=pick_nickname())
                ack = sprinkle_emojis(ack)
                await context.bot.send_message(chat_id=TARGET_CHAT_ID, text=ack)
            except Exception as e:
                logger.error(f"Failed sending scheduled message: {e}")

            # Confirmation to admin
            try:
                pretty_time = send_time.astimezone(SGT).strftime("%d %b %Y, %I:%M %p %Z")
                confirm = f"✅ Delivered to her at {pretty_time}\n— “{sched['message']}”"
                await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=confirm)
            except Exception as e:
                logger.error(f"Failed to send admin confirmation: {e}")
        else:
            remaining.append(sched)

    save_schedules(remaining)

# Inline keyboards
def schedule_list_markup(page_items):
    rows = []
    for i, item in page_items:
        t = datetime.fromisoformat(item["time"]).astimezone(SGT).strftime("%d %b, %I:%M %p")
        preview = (item["message"][:38] + "…") if len(item["message"]) > 40 else item["message"]
        rows.append([InlineKeyboardButton(f"{i}. {t} — {preview}", callback_data=f"view:{i}")])
    return InlineKeyboardMarkup(rows + [[InlineKeyboardButton("Refresh ♻️", callback_data="list:refresh")]])

def detail_markup(index):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🕒 Edit time", callback_data=f"edit_time:{index}")],
        [InlineKeyboardButton("✏️ Edit message", callback_data=f"edit_msg:{index}")],
        [InlineKeyboardButton("🗑️ Delete", callback_data=f"delete:{index}")],
        [InlineKeyboardButton("⬅️ Back to list", callback_data="list:back")]
    ])

# =========================
# 8️⃣ COMMANDS (Admin-only where relevant)
# =========================
async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    txt = (
        "🛠️ *Hiro Bot — Admin Commands*\n\n"
        "/schedule YYYY-MM-DD HH:MM <message>\n"
        "    Create a new schedule (SG time). 12h like 8pm also works.\n\n"
        "/schedule_list\n"
        "    Show compact list with buttons to view/edit/delete.\n\n"
        "/lastseen\n"
        "    Show when she last messaged the bot.\n\n"
        "/sendlog\n"
        "    Send chat logs JSON file to you.\n\n"
        "/debug_on  |  /debug_off\n"
        "    Toggle debug mode (skip admin memory/logging when ON).\n"
    )
    await update.message.reply_text(txt, disable_web_page_preview=True, parse_mode="HTML")

async def cmd_debug_on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global DEBUG_MODE
    if not is_admin(update):
        return
    DEBUG_MODE = True
    await update.message.reply_text("🧪 Debug mode *ON* — admin messages won’t be saved to memory/logs.", parse_mode="HTML")

async def cmd_debug_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global DEBUG_MODE
    if not is_admin(update):
        return
    DEBUG_MODE = False
    await update.message.reply_text("🧪 Debug mode *OFF* — normal behavior restored.", parse_mode="HTML")

async def cmd_lastseen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    await update.message.reply_text(f"🕒 Last seen (her): {last_seen_from_logs()}")

async def cmd_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    try:
        if len(context.args) < 3:
            await update.message.reply_text("Usage: /schedule YYYY-MM-DD HH:MM message  (or HHam/HHpm)")
            return
        date_str, time_str = context.args[0], context.args[1]
        message = " ".join(context.args[2:])
        send_dt = parse_datetime_safely(date_str, time_str)
        send_dt = SGT.localize(send_dt)
        now = datetime.now(SGT)
        if send_dt <= now:
            await update.message.reply_text("That time already pass liao 😅 choose a future time.")
            return

        data = load_schedules()
        data.append({"time": send_dt.isoformat(), "chat_id": TARGET_CHAT_ID, "message": message})
        save_schedules(data)

        pretty = send_dt.strftime("%d %b %Y, %I:%M %p %Z")
        await update.message.reply_text(f"✅ Scheduled for {pretty}\n— “{message}”\n\nUse /schedule_list to manage.")

    except Exception as e:
        await update.message.reply_text(f"⚠️ Error: {e}")

async def cmd_schedule_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    items = load_schedules()
    if not items:
        await update.message.reply_text("No scheduled messages.")
        return
    page = list(enumerate(items))
    await update.message.reply_text("🗓️ Scheduled Messages:", reply_markup=schedule_list_markup(page))

async def cmd_deleteschedule_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    save_schedules([])
    await update.message.reply_text("✅ All scheduled messages deleted.")

# =========================
# 9️⃣ CALLBACK HANDLERS (inline buttons)
# =========================
async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not (update.callback_query and update.effective_chat and update.effective_chat.id == ADMIN_CHAT_ID):
        # ignore non-admin callbacks
        return

    q = update.callback_query
    await q.answer()
    data = q.data or ""

    items = load_schedules()
    if data.startswith("list"):
        if not items:
            await q.edit_message_text("No scheduled messages.")
            return
        page = list(enumerate(items))
        await q.edit_message_text("🗓️ Scheduled Messages:", reply_markup=schedule_list_markup(page))
        return

    if data.startswith("view:"):
        idx = int(data.split(":")[1])
        if idx < 0 or idx >= len(items):
            await q.edit_message_text("That item no longer exists.")
            return
        item = items[idx]
        t_str = datetime.fromisoformat(item["time"]).astimezone(SGT).strftime("%A, %d %B %Y at %I:%M %p %Z")
        text = f"*Schedule {idx}*\n• When: {t_str}\n• To: her (fixed)\n• Message:\n{item['message']}"
        await q.edit_message_text(text, reply_markup=detail_markup(idx), parse_mode="HTML")
        return

    if data.startswith("edit_time:"):
        idx = int(data.split(":")[1])
        if idx < 0 or idx >= len(items):
            await q.edit_message_text("That item no longer exists.")
            return
        ADMIN_STATE[ADMIN_CHAT_ID] = {"mode": "edit_time", "index": idx}
        await q.edit_message_text(
            f"Editing time for #{idx}.\n\nReply with *one line*:\n`YYYY-MM-DD HH:MM`  (24h)  *or*  `YYYY-MM-DD 8:30PM`",
            parse_mode="HTML"
        )
        return

    if data.startswith("edit_msg:"):
        idx = int(data.split(":")[1])
        if idx < 0 or idx >= len(items):
            await q.edit_message_text("That item no longer exists.")
            return
        ADMIN_STATE[ADMIN_CHAT_ID] = {"mode": "edit_msg", "index": idx}
        await q.edit_message_text(
            f"Editing message for #{idx}.\n\nReply with the *new message* (one message).",
            parse_mode="HTML"
        )
        return

    if data.startswith("delete:"):
        idx = int(data.split(":")[1])
        if idx < 0 or idx >= len(items):
            await q.edit_message_text("That item no longer exists.")
            return
        # delete
        removed = items.pop(idx)
        save_schedules(items)
        await q.edit_message_text("🗑️ Deleted. Use /schedule_list to refresh.")
        # Optional: notify admin what was deleted
        logger.info(f"Deleted schedule idx {idx}: {removed!r}")
        return

# =========================
# 🆘 /HELP COMMAND (ADMIN ONLY)
# =========================
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

async def show_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return  # ignore non-admin users

    keyboard = [
        [InlineKeyboardButton("📅 Schedule", callback_data="help_schedule")],
        [InlineKeyboardButton("🕒 List", callback_data="help_list")],
        [InlineKeyboardButton("🧹 Delete All", callback_data="help_delete")],
        [InlineKeyboardButton("📂 Logs", callback_data="help_logs")],
        [InlineKeyboardButton("👀 Last Seen", callback_data="help_seen")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    msg = await update.message.reply_text(
        "🧭 **HiroBot Admin Help Menu**\n\n"
        "Tap any button to learn what each command does.",
        reply_markup=reply_markup,
        parse_mode="HTML"
    )

    # Auto-delete help message after 30 seconds to keep chat clean
    await asyncio.sleep(30)
    try:
        await msg.delete()
    except:
        pass

async def help_button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data

    explanations = {
        "help_schedule": "📅 `/schedule YYYY-MM-DD HH:MM message`\nCreate a message to send to her at a specific time.",
        "help_list": "🕒 `/listschedules`\nView all scheduled messages.",
        "help_delete": "🧹 `/deleteschedule`\nClear *all* scheduled messages.",
        "help_logs": "📂 `/sendlog`\nSend full conversation logs as a JSON file.",
        "help_seen": "👀 `/lastseen`\nCheck when she last interacted with the bot."
    }

    await query.answer()  # close the loading spinner
    await query.edit_message_text(
        text=explanations.get(data, "Unknown command."),
        parse_mode="HTML"
    )


# =========================
# 🎛 CALLBACK HANDLER FOR /HELP BUTTONS
# =========================
async def help_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Responds to button clicks from /help and resets the 30s timer."""
    query = update.callback_query
    await query.answer()

    # Cancel existing timer and restart countdown
    if query.message.message_id in active_help_timers:
        active_help_timers[query.message.message_id].cancel()
        del active_help_timers[query.message.message_id]

    button_map = {
        "help_schedule": "Use /schedule YYYY-MM-DD HH:MM <message> to schedule a message for Babe ❤️",
        "help_list": "Run /listschedules to view all upcoming messages and edit them easily.",
        "help_delete": "Run /deleteschedule to clear *all* scheduled messages.",
        "help_logs": "Use /sendlog to get a chat log summary + JSON export.",
        "help_lastseen": "Use /lastseen to see when Babe last messaged the bot 🕓",
        "help_debug": "Run /debug on or /debug off to toggle memory tracking.",
    }

    message = button_map.get(query.data, "Command not recognized.")

    await query.edit_message_text(f"ℹ️ {message}", parse_mode="HTML")

    # Restart auto-hide timer for 30s again
    async def reset_timer():
        await asyncio.sleep(30)
        if query.message:
            try:
                await query.message.delete()
            except:
                pass

    active_help_timers[query.message.message_id] = asyncio.create_task(reset_timer())
    
# =========================
# 🔟 MESSAGE HANDLER (Chat)
# =========================
def should_use_playful(text: str) -> bool:
    """Tiny heuristic; throttle playful tone if sensitive words appear."""
    lowered = text.lower()
    if any(w in lowered for w in ["sad", "tired", "miss", "alone", "cry", "crying", "upset", "angry", "scared", "worried"]):
        return False
    return random.random() < 0.35  # modest chance

async def human_send(bot, chat_id: int, parts: list[str]):
    """Send multi-part like a human: typing & short pauses. Avoid clutter by not sending separate 'typing' messages."""
    for i, p in enumerate(parts):
        # simulate typing
        try:
            await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        except Exception:
            pass
        await asyncio.sleep(random.uniform(0.6, 1.4) if len(p) < 80 else random.uniform(1.2, 2.0))
        await bot.send_message(chat_id=chat_id, text=p)

async def handle_admin_edit_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """If admin is in an edit state, consume the next message as input and apply change. Returns True if handled."""
    if not is_admin(update):
        return False
    state = ADMIN_STATE.get(ADMIN_CHAT_ID)
    if not state:
        return False

    items = load_schedules()
    idx = state.get("index", -1)
    if idx < 0 or idx >= len(items):
        await update.message.reply_text("That schedule no longer exists. Use /schedule_list.")
        ADMIN_STATE.pop(ADMIN_CHAT_ID, None)
        return True

    try:
        if state.get("mode") == "edit_time":
            # Expect "YYYY-MM-DD HH:MM" OR "YYYY-MM-DD 8:30PM"
            text = update.message.text.strip()
            parts = text.split()
            if len(parts) != 2:
                await update.message.reply_text("Please send exactly: `YYYY-MM-DD HH:MM` (24h) or `YYYY-MM-DD 8:30PM`", parse_mode="HTML")
                return True
            new_dt = parse_datetime_safely(parts[0], parts[1])
            new_dt = SGT.localize(new_dt)
            if new_dt <= datetime.now(SGT):
                await update.message.reply_text("The new time is in the past. Try again.")
                return True
            items[idx]["time"] = new_dt.isoformat()
            save_schedules(items)
            ADMIN_STATE.pop(ADMIN_CHAT_ID, None)
            pretty = new_dt.strftime("%A, %d %B %Y at %I:%M %p %Z")
            await update.message.reply_text(f"✅ Time updated.\nNew time: {pretty}",
                                            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back to list", callback_data="list:back")]]))
            return True

        elif state.get("mode") == "edit_msg":
            new_msg = update.message.text.strip()
            if not new_msg:
                await update.message.reply_text("Message cannot be empty. Try again.")
                return True
            items[idx]["message"] = new_msg
            save_schedules(items)
            ADMIN_STATE.pop(ADMIN_CHAT_ID, None)
            await update.message.reply_text("✅ Message updated.",
                                            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back to list", callback_data="list:back")]]))
            return True

    except Exception as e:
        ADMIN_STATE.pop(ADMIN_CHAT_ID, None)
        await update.message.reply_text(f"⚠️ Could not apply change: {e}")
        return True

    return False

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles incoming messages. Admin: may chat, but memory/logging depends on DEBUG_MODE.
       Her: memory+logs updated; multi-bubble natural replies."""
    user_text = update.message.text or ""

    # If admin is editing, intercept first
    handled = await handle_admin_edit_reply(update, context)
    if handled:
        return

    # Determine sender role
    is_sender_admin = is_admin(update)
    sender_label = "Admin" if is_sender_admin else ("Her" if update.effective_chat.id == TARGET_CHAT_ID else "Other")

    # Logging / Memory policy
    if sender_label == "Her":
        log_message("Her", user_text)
        update_memory("Her", user_text)
    elif sender_label == "Admin":
        if not DEBUG_MODE:
            # If you want to persist admin chats when *not* debugging, set these True:
            pass
        # else skip saving

    # Build prompt & get model reply
    sys_prompt = build_system_prompt()

    # Context (only for her, or for admin when not debugging)
    context_txt = get_memory_context() if (sender_label == "Her" or (sender_label == "Admin" and not DEBUG_MODE)) else ""

    try:
        resp = client.chat.completions.create(
            model=MODEL_ID,
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": context_txt + f"\n{sender_label}: {user_text}\nHiro:"}
            ],
            max_tokens=220,
            temperature=0.7,
        )
        full_text = (resp.choices[0].message.content or "").strip()
    except Exception as e:
        logger.error(f"OpenAI error: {e}")
        await update.message.reply_text("Sorry love, I got a bit jammed there. Mind sending that again?")
        return

    # Natural multi-bubble: split by double newline or sentence-ish
    parts = [p.strip() for p in full_text.split("\n\n") if p.strip()]
    if not parts:
        parts = [full_text]

    # Gently sprinkle emojis & adjust playfulness
    out = []
    playful_ok = should_use_playful(user_text)
    for p in parts[:3]:  # cap to 3 bubbles
        if len(p) < 220 and random.random() < 0.35:
            p = sprinkle_emojis(p)
        if not playful_ok:
            # strip over-playful patterns lightly (very basic)
            p = p.replace(";)", "🙂")
        out.append(p)

    # Save outgoing for her
    if sender_label == "Her":
        for p in out:
            log_message("HiroBot", p)
            update_memory("HiroBot", p)

    await human_send(context.bot, update.effective_chat.id, out)

# =========================
# 1️⃣1️⃣ /SENDLOG (Admin)
# =========================
async def sendlog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return

    logs = load_json_from_bin(LOGS_BIN_ID)
    total_msgs = len(logs)
    last_time = logs[-1]["timestamp"] if logs else "N/A"
    summary = f"📊 Chat Log Summary\n• Total messages: {total_msgs}\n• Last conversation: {last_time} (SGT)"
    await update.message.reply_text(summary)

    temp_file = "chat_logs.json"
    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(logs, f, ensure_ascii=False, indent=2)
    await context.bot.send_document(chat_id=ADMIN_CHAT_ID, document=InputFile(temp_file))

# =========================
# 1️⃣2️⃣ MAIN
# =========================
def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("debug_on", cmd_debug_on))
    app.add_handler(CommandHandler("debug_off", cmd_debug_off))
    app.add_handler(CommandHandler("lastseen", cmd_lastseen))
    app.add_handler(CommandHandler("schedule", cmd_schedule))
    app.add_handler(CommandHandler("schedule_list", cmd_schedule_list))
    app.add_handler(CommandHandler("deleteschedule", cmd_deleteschedule_all))
    app.add_handler(CommandHandler("sendlog", sendlog))
    app.add_handler(CommandHandler("help", show_help))
    app.add_handler(CallbackQueryHandler(handle_schedule_callback))
    app.add_handler(CallbackQueryHandler(help_button_callback))

    # Inline callbacks
    app.add_handler(CallbackQueryHandler(on_callback))

    # Messages
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Job: check scheduled deliveries
    job_queue = app.job_queue
    job_queue.run_repeating(send_scheduled_messages, interval=30, first=10)

    logger.info("💬 Hiro mimic bot running (SGT).")
    

# --------------------------------------
# Unknown command fallback (playful tone)
# --------------------------------------
async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = "Hehe I blur liao 😅 I don’t quite get what you mean… maybe try /help baby? 💕"
    await update.message.reply_text(msg)

app.add_handler(MessageHandler(filters.COMMAND, unknown_command))

# ---- Run bot ----
app.run_polling()


if __name__ == "__main__":
    main()
