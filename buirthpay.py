import os
import asyncio
from telegram import Update, Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
from pymongo import MongoClient
from datetime import datetime, timedelta
from random import choice
from dotenv import load_dotenv

load_dotenv()

# Environment variables
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_DB_URI")
DEFAULT_NOTIFICATION_TIME = datetime.strptime("09:00:00", "%H:%M:%S").time()

# MongoDB setup
client = MongoClient(MONGO_URI)
db = client["birthday_bot"]
users_collection = db["users"]
quotes_collection = db["quotes"]

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
        "/add_quote [QUOTE] - Add a custom birthday quote (admins only).\n"
        "/set_time [HH:MM] - Set the daily notification time (admins only).\n"
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
        "/add_quote [QUOTE] - Add a custom birthday quote (admins only).\n"
        "/set_time [HH:MM] - Set the daily notification time (admins only).\n"
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
        await message.reply_text(
            f"🎂 @{user.username}, kindly register your birthday to receive personalized reminders and wishes! "
            f"Click the button below to register in private chat.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("Register in PM", url=f"t.me/{context.bot.username}")]]
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

# Notify users and groups
async def notify_users_and_groups():
    bot = Bot(BOT_TOKEN)
    today = datetime.now().date()
    tomorrow = today + timedelta(days=1)

    # Notify users about upcoming birthdays
    birthdays_tomorrow = list(users_collection.find({"birthday": tomorrow.isoformat()}))
    if birthdays_tomorrow:
        birthday_users = ", ".join([f"@{user['username']}" for user in birthdays_tomorrow])
        all_users = list(users_collection.find())
        for user in all_users:
            try:
                await bot.send_message(
                    chat_id=user["user_id"],
                    text=f"🎉 Reminder: Tomorrow is the birthday of {birthday_users}! Don't forget to wish them! 🎂",
                )
            except Exception as e:
                print(f"Error in notifying user {user['user_id']}: {e}")

# Send birthday wishes
async def send_wishes():
    bot = Bot(BOT_TOKEN)
    today = datetime.now().date()
    birthdays_today = list(users_collection.find({"birthday": today.isoformat()}))
    all_quotes = [quote["text"] for quote in quotes_collection.find()]

    for user in birthdays_today:
        random_quote = choice(all_quotes) if all_quotes else "Happy Birthday! 🎂"
        try:
            await bot.send_message(
                chat_id=user["user_id"],
                text=(f"🎉 Happy Birthday, @{user['username']}! 🎂\n{random_quote}\n\nFrom - SVD"),
            )
        except Exception as e:
            print(f"Error sending birthday wish to {user['user_id']}: {e}")

# Add custom quote
async def add_quote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Please provide a quote to add.")
        return

    quote = " ".join(context.args)
    quotes_collection.insert_one({"text": quote})
    await update.message.reply_text(f"Quote added: {quote}")

# Set notification time
async def set_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Please provide the time in HH:MM format.")
        return

    try:
        global DEFAULT_NOTIFICATION_TIME
        DEFAULT_NOTIFICATION_TIME = datetime.strptime(context.args[0], "%H:%M").time()
        await update.message.reply_text(f"Notification time set to {DEFAULT_NOTIFICATION_TIME.strftime('%H:%M')}.")
    except ValueError:
        await update.message.reply_text("Invalid time format. Please use HH:MM.")

# Schedule daily reminders
def start_schedulers():
    async def daily_task():
        while True:
            now = datetime.now()
            next_run = datetime.combine(now.date(), DEFAULT_NOTIFICATION_TIME)
            if now.time() > DEFAULT_NOTIFICATION_TIME:
                next_run += timedelta(days=1)
            sleep_duration = (next_run - now).total_seconds()
            await asyncio.sleep(sleep_duration)
            await notify_users_and_groups()
            await send_wishes()

    asyncio.create_task(daily_task())

# Main function
def main():
    application = Application.builder().token(BOT_TOKEN).build()

    # Command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("register_birthday", register_birthday))
    application.add_handler(CommandHandler("add_quote", add_quote))
    application.add_handler(CommandHandler("set_time", set_time))

    # Message handler for keyword detection
    application.add_handler(MessageHandler(filters.TEXT & filters.ChatType.GROUP, keyword_detection))

    # Start the bot
    application.run_polling()

    # Start schedulers after the bot starts
    start_schedulers()

if __name__ == "__main__":
    main()
