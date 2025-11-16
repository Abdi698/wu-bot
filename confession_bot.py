import os
import sys
import sqlite3
import logging
from datetime import datetime
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, 
    CommandHandler, 
    CallbackQueryHandler, 
    MessageHandler, 
    filters, 
    ContextTypes, 
    ConversationHandler
)

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# --- Configuration ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_CHAT_IDS = [id.strip() for id in os.getenv("ADMIN_CHAT_ID", "").split(',') if id.strip()]
CHANNEL_ID = os.getenv("CHANNEL_ID")
BOT_USERNAME = os.getenv("BOT_USERNAME")

# Validate environment variables
if not BOT_TOKEN:
    print("❌ ERROR: BOT_TOKEN is required")
    sys.exit(1)
if not ADMIN_CHAT_IDS:
    print("❌ ERROR: ADMIN_CHAT_ID is required")
    sys.exit(1)
if not CHANNEL_ID:
    print("❌ ERROR: CHANNEL_ID is required")
    sys.exit(1)
if not BOT_USERNAME:
    print("❌ ERROR: BOT_USERNAME is required")
    sys.exit(1)

# Clean bot username
BOT_USERNAME = BOT_USERNAME.replace('@', '').strip()

# --- Logging Setup ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Constants ---
HELP_TEXT = """
🤫 *Confession Bot*

*💌 Submit Confession*: Share your anonymous confession
*📖 Browse*: Read approved confessions  
*💬 Comments*: Discuss confessions
*❓ Help*: View this guide

🔒 *Your anonymity is guaranteed*
All submissions are reviewed before posting.
"""

SELECTING_CATEGORY, WRITING_CONFESSION, BROWSING_CONFESSIONS, WRITING_COMMENT = range(4)

CATEGORY_MAP = {
    "relationship": "Love & Relationships", 
    "friendship": "Friendship", 
    "campus": "Academic Stress", 
    "general": "Other", 
    "vent": "Fear & Anxiety", 
    "secret": "Regrets"
}

# --- Flask App for Render Health Checks ---
app = Flask(__name__)

@app.route('/')
def health_check():
    return "🤫 Confession Bot is running!"

def run_flask():
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

# --- Keyboard Functions ---
def get_main_keyboard():
    buttons = [
        [InlineKeyboardButton("💌 Submit Confession", callback_data="start_confess")],
        [InlineKeyboardButton("📖 Browse Confessions", callback_data="browse_menu")],
        [InlineKeyboardButton("❓ Help", callback_data="help_info")]
    ]
    return InlineKeyboardMarkup(buttons)

def get_category_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💔 Love & Relationships", callback_data="cat_relationship")],
        [InlineKeyboardButton("👥 Friendship", callback_data="cat_friendship")],
        [InlineKeyboardButton("📚 Academic Stress", callback_data="cat_campus")],
        [InlineKeyboardButton("😨 Fear & Anxiety", callback_data="cat_vent")],
        [InlineKeyboardButton("😔 Regrets", callback_data="cat_secret")],
        [InlineKeyboardButton("🌟 Other", callback_data="cat_general")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_confess")]
    ])

def get_browse_keyboard():
    buttons = [
        [InlineKeyboardButton("📚 Latest", callback_data="browse_recent")],
        [InlineKeyboardButton("💔 Love & Relationships", callback_data="browse_relationship")],
        [InlineKeyboardButton("👥 Friendship", callback_data="browse_friendship")],
        [InlineKeyboardButton("📚 Academic Stress", callback_data="browse_campus")],
        [InlineKeyboardButton("😨 Fear & Anxiety", callback_data="browse_vent")],
        [InlineKeyboardButton("😔 Regrets", callback_data="browse_secret")],
        [InlineKeyboardButton("🌟 Other", callback_data="browse_general")],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(buttons)

def get_confession_navigation(confession_id, total, index):
    buttons = []
    if index > 1:
        buttons.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"prev_{confession_id}"))
    if index < total:
        buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"next_{confession_id}"))
    
    nav_row = [buttons] if buttons else []
    action_buttons = [
        [
            InlineKeyboardButton("💬 View Comments", callback_data=f"view_comments_{confession_id}"),
            InlineKeyboardButton("💬 Add Comment", callback_data=f"add_comment_{confession_id}")
        ],
        [InlineKeyboardButton("📚 Browse Categories", callback_data="browse_menu")],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
    ]
    
    if nav_row:
        return InlineKeyboardMarkup([*nav_row, *action_buttons])
    else:
        return InlineKeyboardMarkup(action_buttons)

def get_admin_keyboard(confession_id):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Approve", callback_data=f"approve_{confession_id}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"reject_{confession_id}")
        ]
    ])

def get_comments_management(confession_id):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 Add Comment", callback_data=f"add_comment_{confession_id}")],
        [InlineKeyboardButton("⬅️ Back to Confession", callback_data=f"back_browse_{confession_id}")],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
    ])

def get_channel_post_keyboard(confession_id):
    url = f"https://t.me/{BOT_USERNAME}?start=viewconf_{confession_id}"
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("💬 Comment & Discuss", url=url)
    ]])

# --- Database Management ---
class DatabaseManager:
    def __init__(self):
        self.init_database()
    
    def init_database(self):
        conn = None
        try:
            conn = sqlite3.connect('confessions.db', check_same_thread=False)
            cursor = conn.cursor()
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS confessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    username TEXT,
                    category TEXT,
                    confession_text TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    status TEXT DEFAULT 'pending',
                    channel_message_id INTEGER
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS comments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    confession_id INTEGER,
                    user_id INTEGER,
                    username TEXT,
                    comment_text TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (confession_id) REFERENCES confessions(id)
                )
            ''')
            
            conn.commit()
            print("✅ Database initialized successfully")
        except Exception as e:
            logger.error(f"❌ Database initialization error: {e}")
        finally:
            if conn:
                conn.close()

    def save_confession(self, user_id, username, category, confession_text):
        conn = None
        try:
            conn = sqlite3.connect('confessions.db', check_same_thread=False)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO confessions (user_id, username, category, confession_text)
                VALUES (?, ?, ?, ?)
            ''', (user_id, username, category, confession_text))
            confession_id = cursor.lastrowid
            conn.commit()
            return confession_id
        except Exception as e:
            logger.error(f"❌ Error saving confession: {e}")
            return None
        finally:
            if conn:
                conn.close()

    def update_confession_status(self, confession_id, status, channel_message_id=None):
        conn = None
        try:
            conn = sqlite3.connect('confessions.db', check_same_thread=False)
            cursor = conn.cursor()
            if channel_message_id is not None:
                cursor.execute(
                    'UPDATE confessions SET status = ?, channel_message_id = ? WHERE id = ?', 
                    (status, channel_message_id, confession_id)
                )
            else:
                cursor.execute('UPDATE confessions SET status = ? WHERE id = ?', (status, confession_id))
            conn.commit()
        except Exception as e:
            logger.error(f"❌ Error updating confession: {e}")
        finally:
            if conn:
                conn.close()

    def get_confession(self, confession_id):
        conn = None
        try:
            conn = sqlite3.connect('confessions.db', check_same_thread=False)
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM confessions WHERE id = ?', (confession_id,))
            return cursor.fetchone()
        except Exception as e:
            logger.error(f"❌ Error getting confession: {e}")
            return None
        finally:
            if conn:
                conn.close()
    
    def get_approved_confessions(self, category=None):
        conn = None
        try:
            conn = sqlite3.connect('confessions.db', check_same_thread=False)
            cursor = conn.cursor()
            if category and category != "Recent":
                cursor.execute(
                    'SELECT id, confession_text, category, timestamp FROM confessions WHERE status = "approved" AND category = ? ORDER BY id DESC', 
                    (category,)
                )
            else:
                cursor.execute(
                    'SELECT id, confession_text, category, timestamp FROM confessions WHERE status = "approved" ORDER BY id DESC'
                )
            return cursor.fetchall()
        except Exception as e:
            logger.error(f"❌ Error fetching approved confessions: {e}")
            return []
        finally:
            if conn:
                conn.close()

    def save_comment(self, confession_id, user_id, username, comment_text):
        conn = None
        try:
            conn = sqlite3.connect('confessions.db', check_same_thread=False)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO comments (confession_id, user_id, username, comment_text)
                VALUES (?, ?, ?, ?)
            ''', (confession_id, user_id, username, comment_text))
            conn.commit()
            return cursor.lastrowid
        except Exception as e:
            logger.error(f"❌ Error saving comment: {e}")
            return None
        finally:
            if conn:
                conn.close()

    def get_comments(self, confession_id):
        conn = None
        try:
            conn = sqlite3.connect('confessions.db', check_same_thread=False)
            cursor = conn.cursor()
            cursor.execute(
                'SELECT username, comment_text, timestamp FROM comments WHERE confession_id = ? ORDER BY timestamp ASC', 
                (confession_id,)
            )
            return cursor.fetchall()
        except Exception as e:
            logger.error(f"❌ Error fetching comments: {e}")
            return []
        finally:
            if conn:
                conn.close()

    def get_comments_count(self, confession_id):
        conn = None
        try:
            conn = sqlite3.connect('confessions.db', check_same_thread=False)
            cursor = conn.cursor()
            cursor.execute(
                'SELECT COUNT(*) FROM comments WHERE confession_id = ?', 
                (confession_id,)
            )
            return cursor.fetchone()[0]
        except Exception as e:
            logger.error(f"❌ Error counting comments: {e}")
            return 0
        finally:
            if conn:
                conn.close()

# Initialize database
db = DatabaseManager()

# --- Helper Functions ---
def escape_markdown_text(text):
    escape_chars = r'_*[]()`>#+-.!|{}=~-'
    for char in escape_chars:
        text = text.replace(char, f'\\{char}')
    return text

def format_channel_post(confession_id, category, confession_text):
    safe_confession_text = escape_markdown_text(confession_text)
    comments_count = db.get_comments_count(confession_id)
    return (
        f"*Confession #{confession_id}*\n\n"
        f"{safe_confession_text}\n\n"
        f"Category: {category}\n"
        f"Comments: 💬 {comments_count}"
    )

def format_browsing_confession(confession_data, index, total_confessions):
    confession_id, text, category, timestamp = confession_data
    try:
        dt = datetime.fromisoformat(timestamp)
        date_str = dt.strftime("%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        date_str = "recently"
    comments_count = db.get_comments_count(confession_id)
    return (
        f"📝 *Confession #{confession_id}* ({index + 1}/{total_confessions})\n\n"
        f"*{category}* - {date_str}\n\n"
        f"{text}\n\n"
        f"💬 Comments: {comments_count}"
    )

def format_comments_list(confession_id, comments_list):
    header = f"💬 *Comments for Confession #{confession_id}* ({len(comments_list)} total)\n\n"
    if not comments_list:
        return header + "No comments yet. Be the first one!"
    comment_blocks = []
    for i, (username, text, timestamp) in enumerate(comments_list):
        safe_comment_text = escape_markdown_text(text)
        anon_name = f"User {i+1}"
        time_str = ""
        try:
            dt = datetime.fromisoformat(timestamp.split('.')[0])
            time_str = dt.strftime('%H:%M %b %d')
        except Exception:
            time_str = "recently"
        comment_blocks.append(f"👤 *{anon_name}* ({time_str}):\n» {safe_comment_text}\n")
    return header + "\n---\n".join(comment_blocks)

# --- Handler Functions ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    welcome_text = "🤫 *Confession Bot*\n\nWelcome! Share your thoughts anonymously or explore what others have shared."
    await update.message.reply_text(welcome_text, reply_markup=get_main_keyboard(), parse_mode='Markdown')
    return ConversationHandler.END

async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    welcome_text = "🤫 *Confession Bot*\n\nWelcome back! Use the keyboard below."
    await query.edit_message_text(welcome_text, parse_mode='Markdown', reply_markup=get_main_keyboard())
    return ConversationHandler.END

async def help_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(HELP_TEXT, parse_mode='Markdown', reply_markup=get_main_keyboard())
    return ConversationHandler.END

# --- Confession Submission ---
async def start_confession(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    await query.edit_message_text("📂 *Select a category for your confession:*", reply_markup=get_category_keyboard(), parse_mode='Markdown')
    return SELECTING_CATEGORY

async def select_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    key = query.data.replace("cat_", "")
    category = CATEGORY_MAP.get(key, 'Other')
    context.user_data['category'] = category
    await query.edit_message_text(f"✅ *Category:* {category}\n\n📝 *Now write your confession:*\n\nType your confession below (10-1000 characters):", parse_mode='Markdown')
    return WRITING_CONFESSION

async def receive_confession(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    username = update.effective_user.first_name or "Anonymous"
    confession_text = update.message.text.strip()
    category = context.user_data.get('category', 'General')
    
    if not (10 <= len(confession_text) <= 1000):
        await update.message.reply_text("❌ *Please ensure your confession is between 10 and 1000 characters.*\n\nTry again:", parse_mode='Markdown')
        return WRITING_CONFESSION
    
    confession_id = db.save_confession(user_id, username, category, confession_text)
    if not confession_id:
        await update.message.reply_text("❌ *Error submitting confession.* Please try again later.", parse_mode='Markdown')
        context.user_data.clear()
        return ConversationHandler.END

    admin_message = (
        f"🆕 *Confession #{confession_id} is PENDING*\n\n"
        f"👤 *User:* {username} (ID: {user_id})\n"
        f"📂 *Category:* {category}\n"
        f"📝 *Text:* {escape_markdown_text(confession_text)}\n\n"
        f"*Admin Action:*"
    )
    
    try:
        for admin_id in ADMIN_CHAT_IDS:
            try:
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=admin_message,
                    reply_markup=get_admin_keyboard(confession_id), 
                    parse_mode='Markdown',
                    disable_web_page_preview=True
                )
            except Exception as e:
                logger.error(f"Failed to send admin message to {admin_id}: {e}")
        
        await update.message.reply_text("✅ *Confession Submitted!*\n\nYour confession has been sent for admin review. You'll be notified of the outcome. 🔒", parse_mode='Markdown', reply_markup=get_main_keyboard())
    except Exception as e:
        logger.error(f"Failed to send admin messages: {e}")
        await update.message.reply_text("❌ *Error sending admin notification.* The confession is saved but pending.", parse_mode='Markdown', reply_markup=get_main_keyboard())
    
    context.user_data.clear()
    return ConversationHandler.END

async def cancel_confession(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("❌ Confession cancelled.", reply_markup=get_main_keyboard())
    context.user_data.clear()
    return ConversationHandler.END

# --- Admin Functions ---
async def handle_admin_approval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id_str = str(query.from_user.id)
    if user_id_str not in ADMIN_CHAT_IDS:
        await query.answer("❌ Only admins can perform this action.", show_alert=True)
        return
    
    action, confession_id_str = query.data.split('_', 1) 
    confession_id = int(confession_id_str)
    confession = db.get_confession(confession_id)
    
    if not confession:
        await query.edit_message_text(f"❌ Confession #{confession_id} not found.")
        return
    
    user_id = confession[1]
    category = confession[3]
    confession_text = confession[4]
    
    if action == 'approve':
        try:
            channel_text = format_channel_post(confession_id, category, confession_text)
            channel_message = await context.bot.send_message(
                chat_id=CHANNEL_ID,
                text=channel_text,
                reply_markup=get_channel_post_keyboard(confession_id), 
                parse_mode='Markdown'
            )
            db.update_confession_status(confession_id, 'approved', channel_message.message_id)
            user_message = "🎉 *Your confession has been APPROVED and is live on the channel!*"
            status_text = "APPROVED"
            status_emoji = "✅"
            
            try:
                await context.bot.send_message(chat_id=user_id, text=user_message, parse_mode='Markdown')
            except Exception as e:
                logger.warning(f"Could not notify user {user_id}: {e}")
                
        except Exception as e:
            logger.error(f"Failed to post to channel: {e}")
            await query.answer("❌ Failed to post to channel. Check bot permissions and CHANNEL_ID.", show_alert=True)
            return
    elif action == 'reject':
        db.update_confession_status(confession_id, 'rejected')
        user_message = "❌ *Your confession was NOT APPROVED.* You can submit another one!"
        status_text = "REJECTED"
        status_emoji = "❌"
        
        try:
            await context.bot.send_message(chat_id=user_id, text=user_message, parse_mode='Markdown')
        except Exception as e:
            logger.warning(f"Could not notify user {user_id}: {e}")

    await query.edit_message_text(f"{status_emoji} *Confession {status_text}!*\n\nConfession #{confession_id} has been {status_text.lower()}.\nUser has been notified.", parse_mode='Markdown')

# --- Browsing Functions ---
async def browse_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message:
        await update.message.reply_text("📚 *Browse Confessions by Category:* \n\nSelect a category or *Latest*:", reply_markup=get_browse_keyboard(), parse_mode='Markdown')
    else:
        query = update.callback_query
        await query.answer()
        await query.edit_message_text("📚 *Browse Confessions by Category:* \n\nSelect a category or *Latest*:", reply_markup=get_browse_keyboard(), parse_mode='Markdown')
    return BROWSING_CONFESSIONS

async def start_browse_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    browse_key = query.data.replace("browse_", "") 
    category_name = CATEGORY_MAP.get(browse_key) 
    context.user_data['browse_category'] = category_name
    context.user_data['current_index'] = 0 
    confessions = db.get_approved_confessions(category=category_name)
    context.user_data['confessions_list'] = confessions
    
    if not confessions:
        await query.edit_message_text(f"❌ No approved confessions found for *{category_name or 'Latest'}*.", parse_mode='Markdown', reply_markup=get_browse_keyboard())
        return BROWSING_CONFESSIONS
        
    await display_confession(update, context, via_callback=True)
    return BROWSING_CONFESSIONS

async def display_confession(update: Update, context: ContextTypes.DEFAULT_TYPE, via_callback=False):
    confessions = context.user_data.get('confessions_list', [])
    current_index = context.user_data.get('current_index', 0)
    
    if not confessions: 
        if via_callback:
            await update.callback_query.edit_message_text("❌ No confessions found.", reply_markup=get_browse_keyboard())
        else:
            await update.message.reply_text("❌ No confessions found.", reply_markup=get_browse_keyboard())
        return 
    
    confession_data = confessions[current_index]
    confession_id = confession_data[0]
    formatted_text = format_browsing_confession(confession_data, current_index, len(confessions))
    
    if via_callback:
        try:
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=update.effective_message.message_id,
                text=formatted_text,
                reply_markup=get_confession_navigation(confession_id, len(confessions), current_index + 1),
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.warning(f"Error editing message during navigation: {e}")
    else:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=formatted_text,
            reply_markup=get_confession_navigation(confession_id, len(confessions), current_index + 1),
            parse_mode='Markdown'
        )

async def navigate_confession(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    action, _ = query.data.split('_')
    current_index = context.user_data.get('current_index', 0)
    confessions_list = context.user_data.get('confessions_list', [])
    
    if action == 'next' and current_index < len(confessions_list) - 1:
        context.user_data['current_index'] += 1
    elif action == 'prev' and current_index > 0:
        context.user_data['current_index'] -= 1
    
    await display_confession(update, context, via_callback=True)
    return BROWSING_CONFESSIONS

# --- Commenting Functions ---
async def view_comments(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    try:
        confession_id = int(query.data.split('_')[2])
    except (IndexError, ValueError):
        await query.edit_message_text("❌ Error: Could not find that confession. Please try browsing again.", reply_markup=get_main_keyboard())
        return ConversationHandler.END

    comments_list = db.get_comments(confession_id)
    formatted_text = format_comments_list(confession_id, comments_list)
    await query.edit_message_text(text=formatted_text, parse_mode='Markdown', reply_markup=get_comments_management(confession_id))
    return BROWSING_CONFESSIONS

async def back_to_confession_view(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await display_confession(update, context, via_callback=True)
    return BROWSING_CONFESSIONS

async def request_comment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    try:
        confession_id = int(query.data.split('_')[2])
    except (IndexError, ValueError):
        await query.edit_message_text("❌ Error: Could not find that confession. Please try browsing again.", reply_markup=get_main_keyboard())
        return ConversationHandler.END
    
    context.user_data['commenting_on_id'] = confession_id
    await query.edit_message_text("📝 *Please type your comment below:*\n\n(Your comment will be posted anonymously. Max 500 chars).", parse_mode='Markdown', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cancel_comment")]]))
    return WRITING_COMMENT

async def receive_comment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    comment_text = update.message.text.strip()
    user = update.effective_user
    confession_id = context.user_data.get('commenting_on_id')

    if not confession_id:
        await update.message.reply_text("❌ Error: I lost track of which confession you're commenting on. Please browse again.", reply_markup=get_main_keyboard())
        return ConversationHandler.END

    if not (5 <= len(comment_text) <= 500):
        await update.message.reply_text("❌ *Please ensure your comment is between 5 and 500 characters.*\n\nTry again:", parse_mode='Markdown')
        return WRITING_COMMENT

    try:
        db.save_comment(confession_id, user.id, user.first_name or "Anonymous", comment_text)
        await update.message.reply_text("✅ *Your comment has been added successfully!*", parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error saving comment: {e}")
        await update.message.reply_text("❌ An error occurred while saving your comment. Please try again later.")
    
    await update.message.reply_text("Returning to the main menu:", reply_markup=get_main_keyboard())
    context.user_data.clear()
    return ConversationHandler.END

async def cancel_comment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("❌ Comment cancelled. Returning to main menu.", reply_markup=get_main_keyboard())
    context.user_data.clear()
    return ConversationHandler.END

# --- Main Application ---
def main():
    application = Application.builder().token(BOT_TOKEN).build()

    # Conversation Handler
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler('start', start),
            CallbackQueryHandler(start_confession, pattern='^start_confess$'),
            CallbackQueryHandler(browse_menu, pattern='^browse_menu$'),
            CallbackQueryHandler(main_menu, pattern='^main_menu$'),
            CallbackQueryHandler(help_info, pattern='^help_info$'),
        ],
        states={
            SELECTING_CATEGORY: [
                CallbackQueryHandler(select_category, pattern='^cat_'),
                CallbackQueryHandler(cancel_confession, pattern='^cancel_confess$')
            ],
            WRITING_CONFESSION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_confession),
            ],
            BROWSING_CONFESSIONS: [
                CallbackQueryHandler(start_browse_category, pattern='^browse_'),
                CallbackQueryHandler(navigate_confession, pattern='^next_|^prev_'),
                CallbackQueryHandler(main_menu, pattern='^main_menu$'),
                CallbackQueryHandler(browse_menu, pattern='^browse_menu$'),
                CallbackQueryHandler(request_comment, pattern='^add_comment_'),
                CallbackQueryHandler(view_comments, pattern='^view_comments_'),
                CallbackQueryHandler(back_to_confession_view, pattern='^back_browse_')
            ],
            WRITING_COMMENT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_comment),
                CallbackQueryHandler(cancel_comment, pattern='^cancel_comment$')
            ]
        },
        fallbacks=[
            CommandHandler('start', start),
            CallbackQueryHandler(main_menu, pattern='^main_menu$'),
        ],
        per_message=False
    )

    application.add_handler(conv_handler)
    application.add_handler(CallbackQueryHandler(handle_admin_approval, pattern='^approve_|^reject_'))

    print("🤖 Confession Bot Starting...")
    print(f"✅ Bot Username: @{BOT_USERNAME}")
    print(f"✅ Channel ID: {CHANNEL_ID}")
    print(f"✅ Admin IDs: {ADMIN_CHAT_IDS}")
    
    # Start Flask in background for Render health checks
    import threading
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # Start bot polling
    application.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
