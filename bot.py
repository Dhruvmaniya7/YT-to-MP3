import logging
import os
import time
import asyncio
import yt_dlp
from functools import wraps
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes,
    ConversationHandler, CallbackQueryHandler
)

# --- ⚙️ CONFIGURATION ⚙️ ---
CREATOR_NAME = "shadow maniya"
CONNECT_LINK = "https://dhruvmaniyaportfolio.vercel.app/"
ALLOWED_USER_IDS = [1368109334]
BOT_TOKEN = os.getenv("BOT_TOKEN")

# --- NEW: Define states for our conversation ---
ASK_RENAME, GET_NEW_NAME = range(2)

# --- Bot Setup ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Authorization Decorator ---
def restricted_access(func):
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        if user_id not in ALLOWED_USER_IDS:
            logger.warning(f"Unauthorized access denied for {user_id}.")
            await context.bot.send_message(chat_id=update.effective_chat.id, text="❌ Access Denied.")
            return
        return await func(update, context, *args, **kwargs)
    return wrapped

# --- Reusable Download Logic ---
async def download_and_send_audio(chat_id, url, custom_filename, context: ContextTypes.DEFAULT_TYPE):
    processing_message = await context.bot.send_message(chat_id=chat_id, text="🔄 Starting process...")
    
    # Use a lambda for the progress hook to pass arguments
    progress_hook = lambda d: asyncio.ensure_future(update_progress_message(d, context, processing_message))

    ydl_opts = {
        'format': 'bestaudio/best',
        'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '320'}],
        # NEW: Use the custom_filename if provided, otherwise use the video title
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
        if mp3_file_path and os.path.exists(mp3_file_path):
            os.remove(mp3_file_path)
        if 'error' not in locals().get('error_message', '').lower():
             await processing_message.delete()

# --- Conversation Handlers ---
@restricted_access
async def handle_new_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Entry point for the conversation. Asks the user if they want to rename."""
    url = update.message.text
    context.user_data['url'] = url  # Store the URL to use later

    keyboard = [
        [InlineKeyboardButton("✅ Keep Original Title", callback_data='keep_original')],
        [InlineKeyboardButton("✏️ Rename File", callback_data='rename_file')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text("I've received your link. What would you like to name the file?", reply_markup=reply_markup)
    return ASK_RENAME

async def ask_rename_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the user's choice from the inline buttons."""
    query = update.callback_query
    await query.answer()
    
    url = context.user_data.get('url')
    if not url:
        await query.edit_message_text(text="Sorry, something went wrong. Please send the link again.")
        return ConversationHandler.END

    if query.data == 'keep_original':
        await query.edit_message_text(text="Great! Using the original title.")
        # Pass None for custom_filename to use the default title
        await download_and_send_audio(query.message.chat_id, url, None, context)
        return ConversationHandler.END
    elif query.data == 'rename_file':
        await query.edit_message_text(text="Okay, please send me the new name for your MP3 file.")
        return GET_NEW_NAME

async def get_new_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receives the new filename and starts the download."""
    new_filename = update.message.text
    url = context.user_data.get('url')
    
    await update.message.reply_text(f"Got it! I'll name the file: `{new_filename}`", parse_mode=ParseMode.MARKDOWN)
    await download_and_send_audio(update.message.chat_id, url, new_filename, context)
    return ConversationHandler.END

# --- Other Commands and Helpers ---
@restricted_access
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # This start function remains the same, with the welcome image
    user_name = update.effective_user.first_name
    photo_url = "https://i.imgur.com/8V5Xk2j.png"
    welcome_caption = (
        f"👋 Hello, {user_name}!\n\nI am a private YouTube to MP3 converter bot, created by *{CREATOR_NAME}*.\n\n"
        "Send me a YouTube video link to begin.\n\n⚠️ *Disclaimer*: This tool is for personal use only."
    )
    await context.bot.send_photo(
        chat_id=update.effective_chat.id, photo=photo_url, caption=welcome_caption,
        parse_mode=ParseMode.MARKDOWN
    )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancels the current conversation."""
    await update.message.reply_text("Operation cancelled.")
    return ConversationHandler.END

async def update_progress_message(d, context: ContextTypes.DEFAULT_TYPE, message):
    if d['status'] == 'downloading':
        now = time.time()
        if now - context.bot_data.get('last_update', 0) < 2: return
        progress_text = (f"Downloading...\n📈 **Progress**: `{d['_percent_str']}`\n"
                         f"💨 **Speed**: `{d['_speed_str']}`\n⏳ **ETA**: `{d['_eta_str']}`")
        try:
            await context.bot.edit_message_text(text=progress_text, chat_id=message.chat_id, 
                                                message_id=message.message_id, parse_mode=ParseMode.MARKDOWN)
            context.bot_data['last_update'] = now
        except Exception as e:
            if "Message is not modified" not in str(e): logger.warning(f"Could not edit message: {e}")
    elif d['status'] == 'finished':
        await context.bot.edit_message_text(text="✅ Download finished. Now converting...", 
                                            chat_id=message.chat_id, message_id=message.message_id)

# --- Main Bot Execution ---
def main():
    if not BOT_TOKEN:
        print("FATAL ERROR: BOT_TOKEN environment variable not found.")
        return
    
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # NEW: Setup the ConversationHandler
    conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.TEXT & ~filters.COMMAND, handle_new_link)],
        states={
            ASK_RENAME: [CallbackQueryHandler(ask_rename_callback)],
            GET_NEW_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_new_name)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
        conversation_timeout=300 # 5 minute timeout
    )
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(conv_handler) # Add the conversation handler
    
    print("Bot is up and running with conversation support...")
    application.run_polling()

if __name__ == '__main__':
    main()