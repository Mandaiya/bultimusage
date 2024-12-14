import os
import asyncio
from telegram import (
    Update,
    Bot,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ChatMember,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from pymongo import MongoClient
from datetime import datetime, timedelta
import threading
from dotenv import load_dotenv

load_dotenv()

# Environment variables
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_DB_URI")

# MongoDB setup
client = MongoClient(MONGO_URI)
db = client["birthday_bot"]
users_collection = db["users"]

# /start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_message = (
        "🎉 Hello! I'm your Birthday Reminder Bot! 🎂\n\n"
        "Here's what I can do:\n"
        "- Keep track of your birthday.\n"
        "- Notify everyone a day before your birthday.\n"
        "- Let everyone celebrate with you on your special day!\n\n"
        "Commands:\n"
        "/register_birthday [YYYY-MM-DD] - Register your birthday.\n"
        "/help - Get this help message.\n\n"
        "Add me to a group to notify others about birthdays!"
    )
    await update.message.reply_text(welcome_message)

# /help command
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_message = (
        "🎂 **Birthday Bot Commands** 🎂\n\n"
        "/start - Learn about this bot.\n"
        "/register_birthday [YYYY-MM-DD] - Register your birthday.\n"
        "/help - Get this help message.\n\n"
        "Add me to a group to celebrate birthdays together!"
    )
    await update.message.reply_text(help_message)

# Keyword detection in groups
async def keyword_detection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    user = message.from_user
    keywords = ["birthday", "Birthday", "bornday", "Bornday"]

    if any(keyword in message.text for keyword in keywords):
        # Respond to the specific message in the group
        await message.reply_text(
            "🎂 Kindly register your birthday to receive personalized wishes!\n"
            "Click below to register in private chat.",
            reply_markup=InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton("Register in PM", url=f"t.me/{context.bot.username}")]
                ]
            ),
        )

# Register birthday
async def register_birthday(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if len(context.args) != 1:
        await update.message.reply_text(
            "Please provide your birthday in the format: YYYY-MM-DD\nExample: /register_birthday 1995-07-14"
        )
        return

    try:
        birthday = datetime.strptime(context.args[0], "%Y-%m-%d").date()
    except ValueError:
        await update.message.reply_text("Invalid date format. Please use YYYY-MM-DD.")
        return

    user_data = {
        "user_id": user.id,
        "username": user.username or f"User_{user.id}",
        "birthday": birthday.isoformat(),
    }

    users_collection.update_one(
        {"user_id": user.id}, {"$set": user_data}, upsert=True
    )

    await update.message.reply_text(f"Your birthday has been registered as {birthday}. 🎉")

# Notify users about upcoming birthdays
async def notify_users():
    bot = Bot(BOT_TOKEN)
    today = datetime.now().date()
    tomorrow = today + timedelta(days=1)

    # Get all chats where the bot is present
    all_chats = list(users_collection.find({"birthday": {"$exists": True}}))
    processed_users = set()

    # Notify users about upcoming birthdays
    birthdays_tomorrow = list(users_collection.find({"birthday": tomorrow.isoformat()}))
    for chat in all_chats:
        try:
            chat_members = await bot.get_chat_administrators(chat["chat_id"])
            for member in chat_members:
                if member.user.id not in processed_users and birthdays_tomorrow:
                    birthday_users = ", ".join(
                        [f"@{user['username']}" for user in birthdays_tomorrow]
                    )
                    await bot.send_message(
                        chat_id=member.user.id,
                        text=f"🎉 Reminder: Tomorrow is the birthday of {birthday_users}! Don't forget to wish them! 🎂",
                    )
                    processed_users.add(member.user.id)
        except Exception as e:
            print(f"Error in notifying users: {e}")

# Birthday Wishing System
async def send_wishes():
    bot = Bot(BOT_TOKEN)
    today = datetime.now().date()
    birthdays_today = list(users_collection.find({"birthday": today.isoformat()}))

    # Send personalized birthday wishes
    for user in birthdays_today:
        try:
            await bot.send_message(
                chat_id=user["user_id"],
                text=(
                    f"🎉 Happy Birthday, @{user['username']}! 🎂\n"
                    "Have an amazing day filled with joy and surprises!\n\n"
                    "From - SVD"
                ),
            )
        except Exception as e:
            print(f"Error sending birthday wish: {e}")

# Schedule daily reminders
def start_schedulers():
    def daily_tasks():
        while True:
            now = datetime.now()
            next_run = (datetime.combine(now.date(), datetime.min.time()) + timedelta(days=1))
            sleep_duration = (next_run - now).total_seconds()

            # Sleep until midnight
            threading.Timer(sleep_duration, lambda: asyncio.run(notify_users())).start()
            threading.Timer(sleep_duration, lambda: asyncio.run(send_wishes())).start()

    thread = threading.Thread(target=daily_tasks, daemon=True)
    thread.start()

# Main function
def main():
    application = Application.builder().token(BOT_TOKEN).build()

    # Command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("register_birthday", register_birthday))

    # Message handler for keyword detection
    application.add_handler(MessageHandler(filters.TEXT & filters.ChatType.GROUP, keyword_detection))

    # Start the bot
    application.run_polling()

    # Start schedulers
    start_schedulers()

if __name__ == "__main__":
    main()
