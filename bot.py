
import os
import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    ContextTypes, MessageHandler, filters
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# ===========================
# CONFIG & INITIAL SETUP
# ===========================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "713470736"))

if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN or TELEGRAM_TOKEN missing from environment variables.")

scheduler = AsyncIOScheduler()
scheduler.start()

# ===========================
# AUTHORIZATION CHECK
# ===========================
def is_authorized(update: Update) -> bool:
    user_id = None
    if update.effective_user:
        user_id = update.effective_user.id
    elif update.callback_query:
        user_id = update.callback_query.from_user.id
    return user_id == ADMIN_CHAT_ID

# ===========================
# COMMAND HANDLERS
# ===========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hehe hii 👋 I’m Hiro’s bot! 💕")

async def show_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        await update.message.reply_text("🚫 Sorry, only my admin can use this command!")
        return

    keyboard = [
        [InlineKeyboardButton("🔄 Refresh", callback_data="refresh")],
        [InlineKeyboardButton("🗓 List Schedules", callback_data="list_schedules")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "🛠 Available Commands:
"
        "/help — Show this help menu
"
        "/schedule_list — Show all scheduled messages",
        reply_markup=reply_markup
    )

# ===========================
# CALLBACK HANDLER
# ===========================

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()  # Acknowledge to remove 'Loading...'

    data = query.data
    user_id = query.from_user.id

    # Only admin can use these callbacks
    if user_id != ADMIN_CHAT_ID:
        await query.answer("🚫 You’re not authorized to use this option.", show_alert=True)
        return

    if data == "refresh":
        await query.edit_message_text("✅ Refreshed successfully!")
    elif data == "list_schedules":
        await query.edit_message_text("🗓 (Example) No schedules found right now!")
    else:
        await query.edit_message_text("🤔 Unknown action. Try again.")

# ===========================
# FALLBACK HANDLER
# ===========================

async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hehe I blur liao 😅 I don’t quite get what you mean… maybe try /help baby? 💕"
    )

# ===========================
# MAIN FUNCTION
# ===========================

def main():
    logger.info("🚀 Starting Hiro Telegram bot...")
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", show_help))
    application.add_handler(CallbackQueryHandler(handle_callback))
    application.add_handler(MessageHandler(filters.COMMAND, unknown_command))

    application.run_polling()

if __name__ == "__main__":
    main()
