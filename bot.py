import os
import random
import string
from datetime import datetime, timedelta
from flask import Flask, request
from pymongo import MongoClient
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from dotenv import load_dotenv
import requests
import threading
import asyncio

# === Load environment variables ===
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
SHORTNER_API = os.getenv("SHORTNER_API")
BASE_URL = os.getenv("FLASK_URL", "https://yourdomain.com")  # Render or other base domain
HOW_TO_VERIFY_URL = os.getenv("HOW_TO_VERIFY_URL", "https://your-help-link.com")

client = MongoClient(MONGO_URI)
db = client['likebot']
verifications = db['verifications']

# === Flask app for verification ===
flask_app = Flask(__name__)

@flask_app.route("/verify/<code>")
def verify(code):
    user = verifications.find_one({"code": code})
    if user and not user.get("verified"):
        verifications.update_one({"code": code}, {
            "$set": {"verified": True, "verified_at": datetime.utcnow()}
        })
        return "✅ Verification successful! You can now return to the bot."
    return "❌ Link expired or already verified."

# === Telegram /like command ===
async def like_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not context.args:
        await update.message.reply_text("❌ Please use the correct format:\n/like ind <uid>")
        return

    uid = "-".join(context.args)
    username = user.first_name or "User"

    # Generate unique code
    code = ''.join(random.choices(string.ascii_letters + string.digits, k=12))
    verify_url = f"{BASE_URL}/verify/{code}"

    # Shorten the URL
    try:
        short_api = f"https://shortner.in/api?api={SHORTNER_API}&url={verify_url}"
        response = requests.get(short_api).json()
        if response.get("status") != "success":
            raise Exception(response.get("message", "Unknown error"))
        short_link = response["shortenedUrl"]
    except Exception as e:
        short_link = verify_url  # fallback to direct link

    # Save in database
    verifications.insert_one({
        "user_id": user.id,
        "uid": uid,
        "code": code,
        "verified": False,
        "created_at": datetime.utcnow(),
        "expires_at": datetime.utcnow() + timedelta(hours=6)
    })

    # Send loading then verification message
    loading_msg = await update.message.reply_text("⏳ Generating your verification link...")
    message_text = (
        f"🔒 *Verification Required*\n\n"
        f"Hello {username},\n\n"
        f"Verify to get 1 more request. This is free.\n"
        f"🔗 {short_link}\n\n"
        f"⚠️ Link expires in 6 hours"
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Verify Now", url=short_link)],
        [InlineKeyboardButton("❓ How to Verify?", url=HOW_TO_VERIFY_URL)]
    ])
    await loading_msg.edit_text(message_text, reply_markup=keyboard, parse_mode='Markdown')

# === Launch bot and Flask together ===
def run():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("like", like_command))

    # Run Flask in background thread
    threading.Thread(target=flask_app.run, kwargs={"host": "0.0.0.0", "port": 5000}).start()

    print("🤖 Bot is running...")
    app.run_polling()

if __name__ == '__main__':
    run()