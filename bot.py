import logging
import os
import time
import asyncio
import re
import yt_dlp
from functools import wraps
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes,
    ConversationHandler, CallbackQueryHandler
)

# --- ⚙️ CONFIGURATION & CONSTANTS ⚙️ ---
CREATOR_NAME = "shadow maniya"
CONNECT_LINK = "https://dhruvmaniyaportfolio.vercel.app/"
WELCOME_IMAGE_URL = "https://i.ibb.co/bMNj87bT/download.jpg"

# --- 💡 BOT SETTINGS 💡 ---
MAX_DURATION = 900  # Maximum video duration in seconds (900s = 15 minutes)
CONVERSATION_TIMEOUT = 300 # 5 minute timeout for conversations

# --- ✨ ANIMATIONS ✨ ---
PROCESSING_ANIMATION = ["⚙️ Processing", "⚙️⚙️ Processing.", "⚙️⚙️⚙️ Processing..", "⚙️⚙️⚙️⚙️ Processing..."]

# --- Bot Setup ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
ASK_RENAME, GET_NEW_NAME = range(2)
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Reusable Download Logic ---
async def download_and_send_audio(chat_id, url, custom_filename, context: ContextTypes.DEFAULT_TYPE):
    processing_message = await context.bot.send_message(chat_id=chat_id, text="🔄 Preparing to download...")
    
    progress_hook = lambda d: asyncio.ensure_future(update_progress_message(d, context, processing_message))
    
    ydl_opts = {
        'format': 'bestaudio/best',
        'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '320'}],
        'outtmpl': f"{custom_filename}.%(ext)s" if custom_filename else '%(title)s.%(ext)s',
        'noplaylist': True, 'logger': logger, 'progress_hooks': [progress_hook]
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
                chat_id=chat_id, audio=audio_file, title=os.path.basename(mp3_file_path).replace('.mp3', ''),
                duration=info_dict.get('duration', 0), caption=audio_caption, parse_mode=ParseMode.MARKDOWN
            )
        await context.bot.send_message(
            chat_id=chat_id, text=f"✅ Task complete! Connect with *{CREATOR_NAME}* here: {CONNECT_LINK}",
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        error_message = f"❌ **An error occurred**\n\n`{str(e)}`"
        await processing_message.edit_text(error_message, parse_mode=ParseMode.MARKDOWN)
        logger.error(f"Error processing link: {e}", exc_info=True)
    finally:
        if mp3_file_path and os.path.exists(mp3_file_path): os.remove(mp3_file_path)
        if 'error' not in locals().get('error_message', '').lower(): await processing_message.delete()

# --- Conversation Handlers ---
async def handle_new_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Entry point: Validates link and checks duration before asking to rename."""
    url = update.message.text
    
    youtube_regex = (r'(https?://)?(www\.)?'
                     r'(youtube|youtu|youtube-nocookie)\.(com|be)/'
                     r'(watch\?v=|embed/|v/|.+\?v=)?([^&=%\?]{11})')
    if not re.match(youtube_regex, url):
        await update.message.reply_text("⚠️ This doesn't look like a valid YouTube link. Please try again.")
        return ConversationHandler.END

    pre_check_message = await update.message.reply_text("🔍 Checking video details...")
    
    try:
        with yt_dlp.YoutubeDL({'noplaylist': True, 'quiet': True}) as ydl:
            info_dict = ydl.extract_info(url, download=False)
            duration = info_dict.get('duration', 0)
        
        if duration > MAX_DURATION:
            # --- THIS IS THE UPDATED ONE-LINE ERROR MESSAGE ---
            error_message = f"❌ *Video is too long!* This bot can only process videos under {MAX_DURATION // 60} minutes to avoid errors and long waits."
            await pre_check_message.edit_text(text=error_message, parse_mode=ParseMode.MARKDOWN)
            return ConversationHandler.END

    except Exception as e:
        await pre_check_message.edit_text(f"❌ Could not check the video. It might be private or invalid.\n\n`{str(e)}`")
        logger.error(f"Pre-check failed for {url}: {e}")
        return ConversationHandler.END

    await pre_check_message.delete()
    context.user_data['url'] = url
    keyboard = [[InlineKeyboardButton("✅ Keep Original Title", callback_data='keep_original')],
                [InlineKeyboardButton("✏️ Rename File", callback_data='rename_file')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Video is valid! What would you like to name the file?", reply_markup=reply_markup)
    return ASK_RENAME

async def ask_rename_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    url = context.user_data.get('url')
    if not url:
        await query.edit_message_text(text="Sorry, I lost the link. Please send it again.")
        return ConversationHandler.END

    if query.data == 'keep_original':
        await query.edit_message_text(text="Great! Using the original title.")
        await download_and_send_audio(query.message.chat_id, url, None, context)
        return ConversationHandler.END
    elif query.data == 'rename_file':
        await query.edit_message_text(text="Okay, please send me the new name for your MP3 file.")
        return GET_NEW_NAME

async def get_new_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_filename = update.message.text.strip()
    new_filename = re.sub(r'[\\/*?:"<>|]', "", new_filename)
    url = context.user_data.get('url')
    
    await update.message.reply_text(f"Got it! I'll name the file: `{new_filename}`", parse_mode=ParseMode.MARKDOWN)
    await download_and_send_audio(update.message.chat_id, url, new_filename, context)
    return ConversationHandler.END

# --- Other Commands and Helpers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = update.effective_user.first_name
    welcome_caption = (f"👋 Hello, {user_name}!\n\nI am a YouTube to MP3 converter bot, created by *{CREATOR_NAME}*.\n\n"
                       "Send me a YouTube video link to begin.\n\n⚠️ *Disclaimer*: This tool is for personal use only.")
    await context.bot.send_photo(chat_id=update.effective_chat.id, photo=WELCOME_IMAGE_URL, caption=welcome_caption,
                                 parse_mode=ParseMode.MARKDOWN)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Operation cancelled.")
    return ConversationHandler.END

async def update_progress_message(d, context: ContextTypes.DEFAULT_TYPE, message):
    if d['status'] == 'downloading':
        now = time.time()
        if now - context.bot_data.get('last_update', 0) < 2: return
        progress_text = (f"Downloading...\n📈 **Progress**: `{d['_percent_str']}`\n"
                         f"💨 **Speed**: `{d['_speed_str']}`\n⏳ **ETA**: `{d['_eta_str']}`")
        try: await context.bot.edit_message_text(text=progress_text, chat_id=message.chat_id, message_id=message.message_id, parse_mode=ParseMode.MARKDOWN)
        except: pass
    elif d['status'] == 'finished':
        for frame in PROCESSING_ANIMATION:
            try:
                await context.bot.edit_message_text(text=frame, chat_id=message.chat_id, message_id=message.message_id)
                await asyncio.sleep(0.5)
            except: break

# --- Main Bot Execution ---
def main():
    if not BOT_TOKEN:
        print("FATAL ERROR: BOT_TOKEN environment variable not found.")
        return
    
    application = ApplicationBuilder().token(BOT_TOKEN).connect_timeout(30).read_timeout(30).write_timeout(30).build()
    
    conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.TEXT & ~filters.COMMAND, handle_new_link)],
        states={
            ASK_RENAME: [CallbackQueryHandler(ask_rename_callback)],
            GET_NEW_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_new_name)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
        conversation_timeout=CONVERSATION_TIMEOUT
    )
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(conv_handler)
    
    print("🚀 Bot is up and running with all features!")
    application.run_polling()

if __name__ == '__main__':
    main()
