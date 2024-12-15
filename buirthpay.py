import os
import asyncio
import random
from telegram import (
    Update,
    Bot,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ChatPermissions,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from pymongo import MongoClient
from datetime import datetime, timedelta, time
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
groups_collection = db["groups"]
quotes_collection = db["quotes"]
group_settings_collection = db["group_settings"]

# Default notification time
DEFAULT_NOTIFICATION_TIME = time(9, 0)  # 9:00 AM

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
        "Admin Commands (Group Admins/Owners Only):\n"
        "/add_quote [quote] - Add a birthday message quote.\n"
        "/set_time [HH:MM] - Set birthday notification time (24-hour format).\n"
    )
    await update.message.reply_text(help_message)

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

    await update.message.reply_text(
        f"Your birthday has been registered as {birthday}. 🎉 "
        "We'll notify you and your friends on your special day!"
    )

# Add birthday quotes
async def add_quote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Please provide a quote to add.")
        return

    quote = " ".join(context.args)
    quotes_collection.insert_one({"quote": quote})

    await update.message.reply_text("Quote added successfully! 🎉")

# Set notification time
async def set_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat

    if chat.type not in ["group", "supergroup"]:
        await update.message.reply_text("This command can only be used in groups.")
        return

    member = await context.bot.get_chat_member(chat.id, user.id)
    if member.status not in ["administrator", "creator"]:
        await update.message.reply_text("Only group admins can set the notification time.")
        return

    if len(context.args) != 1:
        await update.message.reply_text("Please provide the time in HH:MM format.")
        return

    try:
        notification_time = datetime.strptime(context.args[0], "%H:%M").time()
    except ValueError:
        await update.message.reply_text("Invalid time format. Please use HH:MM.")
        return

    group_settings_collection.update_one(
        {"chat_id": chat.id},
        {"$set": {"notification_time": notification_time.isoformat()}},
        upsert=True,
    )

    await update.message.reply_text(
        f"Notification time set to {notification_time.strftime('%H:%M')} successfully! 🎉"
    )

# Notify users and groups
async def notify_users_and_groups():
    bot = Bot(BOT_TOKEN)
    today = datetime.now().date()

    # Fetch birthdays today
    birthdays_today = list(users_collection.find({"birthday": today.isoformat()}))

    # Send messages to users
    for user in birthdays_today:
        try:
            random_quote = quotes_collection.aggregate([{"$sample": {"size": 1}}])
            quote = random_quote.next()["quote"] if random_quote else "🎂 Happy Birthday! Have an amazing day! 🎉"
            await bot.send_message(
                chat_id=user["user_id"],
                text=f"{quote}\n\nFrom - SVD"
            )
        except Exception as e:
            print(f"Error sending user birthday message: {e}")

    # Notify groups
    groups = groups_collection.find()
    for group in groups:
        try:
            group_settings = group_settings_collection.find_one({"chat_id": group["chat_id"]})
            notification_time = (
                datetime.strptime(group_settings["notification_time"], "%H:%M").time()
                if group_settings and "notification_time" in group_settings
                else DEFAULT_NOTIFICATION_TIME
            )

            now = datetime.now().time()
            if now >= notification_time:
                birthday_users = ", ".join([f"@{user['username']}" for user in birthdays_today])
                if birthday_users:
                    await bot.send_message(
                        chat_id=group["chat_id"],
                        text=f"🎉 Today is the birthday of {birthday_users}! 🎂 Let's celebrate! 🎉"
                    )
        except Exception as e:
            print(f"Error notifying group: {e}")

# Scheduler for daily tasks
def start_schedulers():
    async def daily_task():
        while True:
            now = datetime.now()
            next_run = (datetime.combine(now.date(), DEFAULT_NOTIFICATION_TIME))
            if now.time() > DEFAULT_NOTIFICATION_TIME:
                next_run += timedelta(days=1)
            sleep_duration = (next_run - now).total_seconds()
            await asyncio.sleep(sleep_duration)
            await notify_users_and_groups()

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

    # Start schedulers
    start_schedulers()

    # Run bot
    application.run_polling()

if __name__ == "__main__":
    main()
