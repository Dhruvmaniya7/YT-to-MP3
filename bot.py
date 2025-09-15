import logging
import os
import time
import asyncio
import yt_dlp
from functools import wraps
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# --- ⚙️ CONFIGURATION - EDIT THESE VALUES ⚙️ ---
# Your details for attribution and the connect link
CREATOR_NAME = "shadow maniya"
CONNECT_LINK = "https://dhruvmaniyaportfolio.vercel.app/" 

# --- 🔐 ADD YOUR USER ID FOR PRIVATE ACCESS 🔐 ---
# Paste the User ID you got from @userinfobot here.
# For multiple users: [123456789, 987654321]
ALLOWED_USER_IDS = [1368109334] # <--- CHANGE THIS

# --- Bot Setup ---
# Load the bot token from the server environment for security
BOT_TOKEN = os.getenv("BOT_TOKEN")

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Authorization Decorator ---
def restricted_access(func):
    """Decorator to restrict usage of a handler to allowed user IDs."""
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        if user_id not in ALLOWED_USER_IDS:
            logger.warning(f"Unauthorized access denied for {user_id}.")
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="❌ Access Denied. You are not authorized to use this bot."
            )
            return
        return await func(update, context, *args, **kwargs)
    return wrapped

# --- Command Handlers ---
@restricted_access
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = update.effective_user.first_name
    welcome_message = (
        f"👋 Hello, {user_name}!\n\n"
        f"I am a private YouTube to MP3 converter bot, created by *{CREATOR_NAME}*.\n\n"
        "Send me a YouTube video link to begin.\n\n"
        "⚠️ *Disclaimer*: This tool is for personal use only. Please respect copyright laws."
    )
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=welcome_message,
        parse_mode=ParseMode.MARKDOWN
    )

# --- Real-Time Progress Hook ---
async def progress_hook(d, context: ContextTypes.DEFAULT_TYPE, message):
    if d['status'] == 'downloading':
        now = time.time()
        if now - context.bot_data.get('last_update', 0) < 2:
            return
        progress_text = (
            f"Downloading...\n"
            f"📈 **Progress**: `{d['_percent_str']}`\n"
            f"💨 **Speed**: `{d['_speed_str']}`\n"
            f"⏳ **ETA**: `{d['_eta_str']}`"
        )
        try:
            await context.bot.edit_message_text(
                text=progress_text, chat_id=message.chat_id, message_id=message.message_id,
                parse_mode=ParseMode.MARKDOWN
            )
            context.bot_data['last_update'] = now
        except Exception as e:
            if "Message is not modified" not in str(e): logger.warning(f"Could not edit message: {e}")
    elif d['status'] == 'finished':
        await context.bot.edit_message_text(
            text="✅ Download finished. Now converting...",
            chat_id=message.chat_id, message_id=message.message_id
        )

# --- Core Functionality ---
@restricted_access
async def process_youtube_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text
    processing_message = await update.message.reply_text("🔄 Starting process...")
    ydl_opts = {
        'format': 'bestaudio/best',
        'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '320'}],
        'outtmpl': '%(title)s.%(ext)s', 'noplaylist': True, 'logger': logger,
        'progress_hooks': [(lambda d: asyncio.ensure_future(progress_hook(d, context, processing_message)))]
    }
    mp3_file_path = None
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            file_name = ydl.prepare_filename(info_dict)
            mp3_file_path = os.path.splitext(file_name)[0] + '.mp3'
        
        await processing_message.edit_text("⬆️ Uploading to Telegram...")
        audio_caption = f"🎵 **{info_dict.get('title', 'Audio')}**\n\n⚠️ Remember to respect copyright laws."
        with open(mp3_file_path, 'rb') as audio_file:
            await context.bot.send_audio(
                chat_id=update.effective_chat.id, audio=audio_file, title=info_dict.get('title', 'Audio'),
                duration=info_dict.get('duration', 0), caption=audio_caption, parse_mode=ParseMode.MARKDOWN
            )
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"✅ Task complete! Connect with *{CREATOR_NAME}* here: {CONNECT_LINK}",
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        error_message = f"❌ **An error occurred**\n\nIt might be a private, invalid, or geo-restricted link.\n\n`{str(e)}`"
        await processing_message.edit_text(error_message, parse_mode=ParseMode.MARKDOWN)
        logger.error(f"Error processing link: {e}", exc_info=True)
    finally:
        if mp3_file_path and os.path.exists(mp3_file_path):
            os.remove(mp3_file_path)
        if 'error' not in locals().get('error_message', '').lower():
             await processing_message.delete()

# --- Main Bot Execution ---
def main():
    if not BOT_TOKEN:
        print("FATAL ERROR: BOT_TOKEN environment variable not found.")
        return
        
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, process_youtube_link))
    print("Bot is up and running...")
    application.run_polling()

if __name__ == '__main__':

    main()
