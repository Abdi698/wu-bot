# File name: confession_bot.py

import sys
import os
import atexit

# Prevent multiple instances on Render - ENHANCED VERSION
lock_file_path = '/tmp/bot_running.lock'

def cleanup():
    """Cleanup lock file on exit"""
    try:
        if os.path.exists(lock_file_path):
            os.remove(lock_file_path)
            print("✅ Cleanup completed - lock file removed")
    except Exception as e:
        print(f"⚠️ Cleanup warning: {e}")

# Register cleanup function
atexit.register(cleanup)

# Check for existing instance
try:
    if os.path.exists(lock_file_path):
        # Check if the process is actually still running
        with open(lock_file_path, 'r') as f:
            pid = f.read().strip()
        try:
            # Try to check if the process is still active
            os.kill(int(pid), 0)
            print("❌ Another bot instance is already running. Exiting.")
            sys.exit(0)
        except (ProcessLookupError, ValueError):
            # Process is dead, remove stale lock file
            os.remove(lock_file_path)
            print("🔄 Removed stale lock file")
    
    # Create new lock file with current process ID
    with open(lock_file_path, 'w') as f:
        f.write(str(os.getpid()))
        
except Exception as e:
    print(f"⚠️ Lock file check warning: {e}")

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
import logging
import sqlite3
from datetime import datetime
from dotenv import load_dotenv

# --- Import Keyboards ---
try:
    from keyboards import (
        get_main_keyboard, 
        get_category_keyboard, 
        get_browse_keyboard, 
        get_confession_navigation, 
        get_admin_keyboard, 
        get_comments_management,
        get_channel_post_keyboard,
        get_settings_keyboard 
    )
except ImportError:
    print("WARNING: 'keyboards.py' not found. Using built-in keyboards.")
    # Define complete keyboards
    def get_main_keyboard(channel_link=None): 
        buttons = [
            [InlineKeyboardButton("💌 Submit Confession", callback_data="start_confess")],
            [InlineKeyboardButton("📖 Browse Confessions", callback_data="browse_menu")],
            [InlineKeyboardButton("💬 Comments", callback_data="comments_info")],
            [InlineKeyboardButton("❓ Help", callback_data="help_info")]
        ]
        if channel_link:
            buttons.append([InlineKeyboardButton("📢 View Channel", url=channel_link)])
        return InlineKeyboardMarkup(buttons)
    
    def get_category_keyboard(): 
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("Academic Stress", callback_data="cat_campus")],
            [InlineKeyboardButton("Friendship", callback_data="cat_friendship")],
            [InlineKeyboardButton("Love & Relationships", callback_data="cat_relationship")],
            [InlineKeyboardButton("Regrets", callback_data="cat_secret")],
            [InlineKeyboardButton("Achievements", callback_data="cat_general")],
            [InlineKeyboardButton("Fear & Anxiety", callback_data="cat_vent")],
            [InlineKeyboardButton("Other", callback_data="cat_general")],
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel_confess")]
        ])
    
    def get_browse_keyboard(show_back=False): 
        buttons = [
            [InlineKeyboardButton("📚 Latest", callback_data="browse_recent")],
            [InlineKeyboardButton("💔 Love & Relationships", callback_data="browse_relationship")],
            [InlineKeyboardButton("👥 Friendship", callback_data="browse_friendship")],
            [InlineKeyboardButton("📚 Academic Stress", callback_data="browse_campus")],
            [InlineKeyboardButton("😨 Fear & Anxiety", callback_data="browse_vent")],
            [InlineKeyboardButton("😔 Regrets", callback_data="browse_secret")],
            [InlineKeyboardButton("🌟 Other", callback_data="browse_general")]
        ]
        if show_back:
            buttons.append([InlineKeyboardButton("⬅️ Back to Main", callback_data="main_menu")])
        return InlineKeyboardMarkup(buttons)
    
    def get_confession_navigation(c_id, total, index): 
        buttons = []
        if index > 1:
            buttons.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"prev_{c_id}"))
        if index < total:
            buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"next_{c_id}"))
        
        nav_row = [buttons] if buttons else []
        
        action_buttons = [
            [
                InlineKeyboardButton("💬 View Comments", callback_data=f"view_comments_{c_id}"),
                InlineKeyboardButton("💬 Add Comment", callback_data=f"add_comment_{c_id}")
            ],
            [InlineKeyboardButton("📚 Browse Categories", callback_data="browse_menu")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
        ]
        
        if nav_row:
            return InlineKeyboardMarkup([*nav_row, *action_buttons])
        else:
            return InlineKeyboardMarkup(action_buttons)
    
    def get_admin_keyboard(c_id): 
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Approve", callback_data=f"approve_{c_id}"),
                InlineKeyboardButton("❌ Reject", callback_data=f"reject_{c_id}")
            ],
            [InlineKeyboardButton("⏸️ Set Pending", callback_data=f"pending_{c_id}")]
        ])
    
    def get_comments_management(c_id): 
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("💬 Add Comment", callback_data=f"add_comment_{c_id}")],
            [InlineKeyboardButton("⬅️ Back to Confession", callback_data=f"back_browse_{c_id}")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
        ])
    
    def get_channel_post_keyboard(c_id, username): 
        return InlineKeyboardMarkup([[
            InlineKeyboardButton("💬 Comment & Discuss", url=f"https://t.me/{username}?start=viewconf_{c_id}")
        ]])
    
    def get_settings_keyboard(): 
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("🔔 Notifications", callback_data="settings_notifications")],
            [InlineKeyboardButton("🌙 Dark Mode", callback_data="settings_darkmode")],
            [InlineKeyboardButton("⬅️ Back", callback_data="back_main")]
        ])


# Load environment variables
load_dotenv()

# --- Configuration ---
BOT_TOKEN = os.getenv("BOT_TOKEN") 
ADMIN_CHAT_ID_RAW = os.getenv("ADMIN_CHAT_ID") or os.getenv("ADMIN_IDS") 
ADMIN_CHAT_ID = ADMIN_CHAT_ID_RAW.split(',')[0].strip() if ADMIN_CHAT_ID_RAW else None

try:
    CHANNEL_ID = int(os.getenv("CHANNEL_ID")) 
except (TypeError, ValueError):
    CHANNEL_ID = None 

BOT_USERNAME = os.getenv("BOT_USERNAME")

if not all([BOT_TOKEN, ADMIN_CHAT_ID, CHANNEL_ID, BOT_USERNAME]):
    print("FATAL ERROR: One or more required environment variables are missing or invalid.")
    print(f"BOT_TOKEN: {'✅' if BOT_TOKEN else '❌'}")
    print(f"ADMIN_CHAT_ID: {'✅' if ADMIN_CHAT_ID else '❌'}")
    print(f"CHANNEL_ID: {'✅' if CHANNEL_ID else '❌'}")
    print(f"BOT_USERNAME: {'✅' if BOT_USERNAME else '❌'}")
    sys.exit(1)
    
# --- Logging Setup ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Constants ---
HELP_TEXT = """
❓ *Bot Help & Guidelines*

*💌 Submit Confession*: Share your anonymous confession
*📖 Browse*: Read approved confessions and comments  
*💬 Comments*: Discuss confessions (via Browse feature)
*❓ Help*: View this guide

🔒 *Your anonymity is guaranteed*
"""

SELECTING_CATEGORY, WRITING_CONFESSION, BROWSING_CONFESSIONS, WRITING_COMMENT = range(4)

CATEGORY_MAP = {
    "relationship": "Love & Relationships", "friendship": "Friendship", 
    "campus": "Academic Stress", "general": "Other", 
    "vent": "Fear & Anxiety", "secret": "Regrets", "recent": "Recent"
}

# --- Database Management ---
class DatabaseManager:
    def __init__(self):
        self.init_database()
    
    def init_database(self):
        """Initialize database tables."""
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

    def save_confession(self, user_id, username, category, confession_text, channel_message_id=None):
        """Save confession to database."""
        conn = None
        try:
            conn = sqlite3.connect('confessions.db', check_same_thread=False)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO confessions (user_id, username, category, confession_text, channel_message_id)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, username, category, confession_text, channel_message_id))
            
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
        """Update confession status."""
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
        """Get confession by ID."""
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
        """Fetches approved confessions."""
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
        """Save a new comment to the database."""
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
        """Fetch all comments for a specific confession."""
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
        """Get the total number of comments for a confession."""
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

def format_channel_post(confession_id: int, category: str, confession_text: str) -> str:
    """Formats the text for the channel post."""
    comments_count = db.get_comments_count(confession_id)
    
    post_header = f"Confession #{confession_id}"
    category_tag = f"#{category.replace(' ', '_').replace('&', 'and')}" 
    
    channel_text = (
        f"*{post_header}*\n\n"
        f"{confession_text}\n\n"
        f"Category: {category_tag}\n"
        f"Comments: 💬 {comments_count}"
    )
    return channel_text

def format_browsing_confession(confession_data, index, total_confessions):
    """Formats a single confession for browsing."""
    confession_id, text, category, timestamp = confession_data
    
    try:
        dt = datetime.fromisoformat(timestamp)
        date_str = dt.strftime("%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        date_str = timestamp
        
    comments_count = db.get_comments_count(confession_id)
    
    formatted_text = (
        f"📝 *Confession #{confession_id}* ({index + 1}/{total_confessions})\n\n"
        f"*{category}* - {date_str}\n\n"
        f"{text}\n\n"
        f"💬 Comments: {comments_count}"
    )
    return formatted_text

def format_comments_list(confession_id, comments_list):
    """Formats the list of comments for display."""
    header = f"💬 *Comments for Confession #{confession_id}* ({len(comments_list)} total)\n\n"
    
    if not comments_list:
        return header + "No comments yet. Be the first one!"
        
    comment_blocks = []
    
    for i, (username, text, timestamp) in enumerate(comments_list):
        anon_name = f"User {i+1}"
        
        time_str = ""
        try:
            dt = datetime.fromisoformat(timestamp.split('.')[0])
            time_str = dt.strftime('%H:%M %b %d')
        except Exception:
            time_str = "recently"

        comment_block = (
            f"👤 *{anon_name}* ({time_str}):\n"
            f"» {text}\n"
        )
        comment_blocks.append(comment_block)
            
    return header + "\n---\n".join(comment_blocks)

# --- Enhanced Deep Link Handler ---
async def handle_deep_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles deep links like /start viewconf_123 - IMPROVED VERSION."""
    if not context.args:
        return await start(update, context)
    
    payload = context.args[0]
    
    if not payload.startswith('viewconf_'):
        return await start(update, context)
    
    try:
        confession_id = int(payload.split('_')[1])
    except (IndexError, ValueError):
        await update.message.reply_text(
            "❌ Invalid confession link.", 
            reply_markup=get_main_keyboard(channel_link=f"https://t.me/{BOT_USERNAME}")
        )
        return ConversationHandler.END

    # Get confession data
    confession_full = db.get_confession(confession_id)
    
    if not confession_full or confession_full[6] != 'approved':
        await update.message.reply_text(
            "❌ This confession is not available or not approved yet.", 
            reply_markup=get_main_keyboard(channel_link=f"https://t.me/{BOT_USERNAME}")
        )
        return ConversationHandler.END

    # Prepare confession data for browsing
    confession_data = (confession_full[0], confession_full[4], confession_full[3], confession_full[5])
    
    # Store in context for navigation
    context.user_data['confessions_list'] = [confession_data]
    context.user_data['current_index'] = 0 
    context.user_data['from_deep_link'] = True
    
    # Send welcome message and display confession
    await update.message.reply_text(
        "🔗 *You were linked to this confession from the channel*\n\n"
        "You can read comments or add your own below:",
        parse_mode='Markdown'
    )

    await display_confession(update, context, via_callback=False)
    
    return BROWSING_CONFESSIONS

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send welcome message and main keyboard."""
    
    # Clear user data when starting fresh
    if not context.args:
        context.user_data.clear()

    # Handle deep links
    if context.args:
        return await handle_deep_link(update, context)

    welcome_text = (
        "🤫 *Confession Bot*\n\n"
        "Welcome! Share your thoughts anonymously or explore what others have shared."
    )
    
    await update.message.reply_text(
        welcome_text, 
        reply_markup=get_main_keyboard(channel_link=f"https://t.me/{BOT_USERNAME}"), 
        parse_mode='Markdown'
    )
    return ConversationHandler.END

async def handle_text_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles text button clicks."""
    text = update.message.text
    
    if text == "💌 Submit Confession":
        await update.message.reply_text(
            "Click the button below to start your confession:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📝 Start Confession", callback_data="start_confess")]])
        )
        return ConversationHandler.END
        
    elif text == "📖 Browse":
        return await browse_menu(update, context)
        
    elif text == "💬 Comments":
        await update.message.reply_text(
            "ℹ️ *How to Comment*\n\n"
            "To read or add comments, please use the **📖 Browse** button, find a confession, and then use the 'View Comments' or 'Add Comment' buttons.",
            parse_mode='Markdown',
            reply_markup=get_main_keyboard(channel_link=f"https://t.me/{BOT_USERNAME}")
        )
        return ConversationHandler.END
        
    elif text == "❓ Help":
        await update.message.reply_text(
            HELP_TEXT,
            parse_mode='Markdown',
            reply_markup=get_main_keyboard(channel_link=f"https://t.me/{BOT_USERNAME}")
        )
        return ConversationHandler.END
        
    elif text == "⚙️ Settings":
        await update.message.reply_text(
            "⚙️ *Settings Menu*\n\n"
            "These features are not yet implemented, but will be available in the future.",
            reply_markup=get_settings_keyboard(),
            parse_mode='Markdown'
        )
        return ConversationHandler.END
    
    return ConversationHandler.END

async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Return to main menu from an inline callback."""
    query = update.callback_query
    await query.answer()
    
    welcome_text = "🤫 *Confession Bot*\n\nWelcome back! Use the keyboard below."
    
    try:
        await query.edit_message_text(
            welcome_text, 
            parse_mode='Markdown',
            reply_markup=get_main_keyboard(channel_link=f"https://t.me/{BOT_USERNAME}")
        )
    except Exception as e:
        logger.warning(f"main_menu edit failed: {e}")
        
    return ConversationHandler.END

async def handle_settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles callbacks from the settings menu."""
    query = update.callback_query
    
    if query.data == "settings_notifications":
        await query.answer("🔔 Notification settings are not yet implemented.", show_alert=True)
    elif query.data == "settings_darkmode":
        await query.answer("🌙 Dark mode settings are not yet implemented.", show_alert=True)

# --- Confession Submission Logic ---
async def start_confession(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the confession process."""
    query = update.callback_query
    await query.answer()
    
    context.user_data.clear()
    
    await query.edit_message_text(
        "📂 *Select a category for your confession:*",
        reply_markup=get_category_keyboard(),
        parse_mode='Markdown'
    )
    
    return SELECTING_CATEGORY

async def select_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle category selection."""
    query = update.callback_query
    await query.answer()
    
    key = query.data.replace("cat_", "")
    category = CATEGORY_MAP.get(key, 'Other')
    context.user_data['category'] = category
    
    await query.edit_message_text(
        f"✅ *Category:* {category}\n\n"
        "📝 *Now write your confession:*\n\n"
        "Type your confession below (10-1000 characters):",
        parse_mode='Markdown'
    )
    
    return WRITING_CONFESSION

async def receive_confession(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive confession text, save to DB, and send admin link."""
    user_id = update.effective_user.id
    username = update.effective_user.first_name or "Anonymous"
    confession_text = update.message.text.strip()
    category = context.user_data.get('category', 'General')
    
    if not (10 <= len(confession_text) <= 1000):
        await update.message.reply_text(
            "❌ *Please ensure your confession is between 10 and 1000 characters.*\n\n"
            "Try again:",
            parse_mode='Markdown'
        )
        return WRITING_CONFESSION
    
    confession_id = db.save_confession(user_id, username, category, confession_text)
    if not confession_id:
        await update.message.reply_text("❌ *Error submitting confession.* Please try again later.", parse_mode='Markdown')
        context.user_data.clear()
        return ConversationHandler.END

    admin_message = (
        f"🆕 *Confession #*{confession_id} is *PENDING*\n\n"
        f"👤 *User:* {username} (ID: {user_id})\n"
        f"📂 *Category:* {category}\n"
        f"📝 *Text:* {confession_text}\n\n"
        f"*Admin Action:*"
    )
    
    try:
        logger.info(f"Attempting to send admin notification to Chat ID: {ADMIN_CHAT_ID}") 
        await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=admin_message,
            reply_markup=get_admin_keyboard(confession_id), 
            parse_mode='Markdown',
            disable_web_page_preview=True
        )
        
        await update.message.reply_text(
            "✅ *Confession Submitted!*\n\n"
            "Your confession has been sent for admin review. You'll be notified of the outcome. 🔒",
            parse_mode='Markdown',
            reply_markup=get_main_keyboard(channel_link=f"https://t.me/{BOT_USERNAME}") 
        )
        
    except Exception as e:
        logger.error(f"Failed to send admin message to {ADMIN_CHAT_ID}: {e}")
        await update.message.reply_text(
            "❌ *Error sending admin notification.* The confession is saved but pending.",
            parse_mode='Markdown',
            reply_markup=get_main_keyboard(channel_link=f"https://t.me/{BOT_USERNAME}")
        )
    
    context.user_data.clear()
    return ConversationHandler.END

async def handle_admin_approval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle admin approval/rejection."""
    query = update.callback_query
    await query.answer()
    
    if str(query.from_user.id) not in ADMIN_CHAT_ID: 
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
    
    user_message = ""
    status_text = ""
    status_emoji = ""
    
    if action == 'approve':
        try:
            channel_text = format_channel_post(confession_id, category, confession_text)
            
            channel_message = await context.bot.send_message(
                chat_id=CHANNEL_ID,
                text=channel_text,
                reply_markup=get_channel_post_keyboard(confession_id, BOT_USERNAME), 
                parse_mode='Markdown'
            )
            
            db.update_confession_status(confession_id, 'approved', channel_message.message_id)
            
            user_message = "🎉 *Your confession has been APPROVED and is live on the channel!*"
            status_text = "APPROVED"
            status_emoji = "✅"
            
        except Exception as e:
            logger.error(f"Failed to post to channel: {e}")
            await query.answer("❌ Failed to post to channel. Check bot permissions and CHANNEL_ID.", show_alert=True)
            return
            
    elif action == 'reject':
        db.update_confession_status(confession_id, 'rejected')
        user_message = "❌ *Your confession was NOT APPROVED.* You can submit another one!"
        status_text = "REJECTED"
        status_emoji = "❌"
    
    elif action == 'pending':
        db.update_confession_status(confession_id, 'pending')
        status_text = "SET BACK TO PENDING"
        status_emoji = "⏸️"
        
        return await query.edit_message_text(
            f"{status_emoji} *Confession {status_text}!*\n\n"
            f"Confession #{confession_id} is back in the queue.",
            parse_mode='Markdown'
        )

    try:
        if user_message:
            await context.bot.send_message(chat_id=user_id, text=user_message, parse_mode='Markdown')
    except Exception as e:
        logger.warning(f"Could not notify user {user_id}: {e}")
    
    await query.edit_message_text(
        f"{status_emoji} *Confession {status_text}!*\n\n"
        f"Confession #{confession_id} has been {status_text.lower()}.\n"
        f"User has been notified.",
        parse_mode='Markdown'
    )

async def cancel_confession(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the confession process."""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "❌ Confession cancelled.", 
        reply_markup=get_main_keyboard(channel_link=f"https://t.me/{BOT_USERNAME}")
    )
    context.user_data.clear()
    return ConversationHandler.END

# --- Browsing Logic ---
async def browse_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Shows the browsing category menu."""
    if update.message:
        await update.message.reply_text(
            "📚 *Browse Confessions by Category:* \n\nSelect a category or *Latest*:",
            reply_markup=get_browse_keyboard(),
            parse_mode='Markdown'
        )
    else:
        query = update.callback_query
        await query.answer()
        await query.edit_message_text(
            "📚 *Browse Confessions by Category:* \n\nSelect a category or *Latest*:",
            reply_markup=get_browse_keyboard(),
            parse_mode='Markdown'
        )
    return BROWSING_CONFESSIONS

async def start_browse_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Fetches and displays the first confession for a selected category."""
    query = update.callback_query
    await query.answer()
    
    browse_key = query.data.replace("browse_", "") 
    category_name = CATEGORY_MAP.get(browse_key) 
    
    context.user_data['browse_category'] = category_name
    context.user_data['current_index'] = 0 
    
    confessions = db.get_approved_confessions(category=category_name)
    context.user_data['confessions_list'] = confessions
    
    if not confessions:
        await query.edit_message_text(
            f"❌ No approved confessions found for *{category_name or 'Latest'}*.",
            parse_mode='Markdown',
            reply_markup=get_browse_keyboard(show_back=True) 
        )
        return BROWSING_CONFESSIONS
        
    await display_confession(update, context, via_callback=True)
    return BROWSING_CONFESSIONS

async def display_confession(update: Update, context: ContextTypes.DEFAULT_TYPE, via_callback=False):
    """Generic function to display the current confession based on index."""
    confessions = context.user_data.get('confessions_list', [])
    current_index = context.user_data.get('current_index', 0)
    
    if not confessions: 
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
                reply_markup=get_confession_navigation(
                    confession_id, 
                    len(confessions), 
                    current_index + 1
                ),
                parse_mode='Markdown'
            )
        except Exception as e:
             logger.warning(f"Error editing message during navigation: {e}")
    else:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=formatted_text,
            reply_markup=get_confession_navigation(
                confession_id, 
                len(confessions), 
                current_index + 1
            ),
            parse_mode='Markdown'
        )

async def navigate_confession(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles 'next' and 'previous' buttons."""
    query = update.callback_query
    await query.answer()
    
    action, _ = query.data.split('_')
    current_index = context.user_data.get('current_index', 0)
    confessions = context.user_data.get('confessions_list', [])
    total_confessions = len(confessions)
    
    if total_confessions <= 1:
        await query.answer("Only one confession available in this view.")
        return BROWSING_CONFESSIONS

    new_index = current_index
    if action == 'next' and current_index < total_confessions - 1:
        new_index += 1
    elif action == 'prev' and current_index > 0:
        new_index -= 1
    else:
        await query.answer("End of the line!")
        return BROWSING_CONFESSIONS
        
    context.user_data['current_index'] = new_index
    await display_confession(update, context, via_callback=True)
    return BROWSING_CONFESSIONS

# --- Comment Logic ---
async def view_comments(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Fetches and displays all comments for a confession."""
    query = update.callback_query
    await query.answer()
    
    confession_id = int(query.data.split('_')[-1])
    
    comments = db.get_comments(confession_id)
    logger.info(f"Handler received {len(comments)} comments for confession {confession_id}.")

    formatted_comments = format_comments_list(confession_id, comments)
    
    context.user_data['browsing_message_id'] = update.effective_message.message_id
    context.user_data['browsing_chat_id'] = update.effective_chat.id
    
    await query.edit_message_text(
        formatted_comments,
        parse_mode='Markdown',
        reply_markup=get_comments_management(confession_id)
    )
    return BROWSING_CONFESSIONS

async def start_add_comment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Starts the conversation flow to add a comment."""
    query = update.callback_query
    await query.answer()
    
    confession_id = int(query.data.split('_')[-1])
    context.user_data['comment_confession_id'] = confession_id
    
    await query.edit_message_text(
        "💬 *Write Your Anonymous Comment*\n\n"
        "Type your comment below (max 200 characters). This will be posted immediately.",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel Comment", callback_data=f"cancel_comment_{confession_id}")]])
    )
    return WRITING_COMMENT

async def receive_comment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receives the comment text, saves it, and updates the comment view."""
    confession_id = context.user_data.get('comment_confession_id')
    comment_text = update.message.text.strip()
    user_id = update.effective_user.id
    username = update.effective_user.first_name or "Anonymous"
    
    if not confession_id:
        await update.message.reply_text("❌ Error: Confession context lost.", reply_markup=get_main_keyboard(channel_link=f"https://t.me/{BOT_USERNAME}"))
        context.user_data.clear()
        return ConversationHandler.END
    
    if not (1 <= len(comment_text) <= 200):
        await update.message.reply_text(
            "❌ *Please ensure your comment is between 1 and 200 characters.*\n\n"
            "Try again or press 'Cancel Comment' below.",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel Comment", callback_data=f"cancel_comment_{confession_id}")]])
        )
        return WRITING_COMMENT
        
    db.save_comment(confession_id, user_id, username, comment_text)
    
    try:
        confession_data = db.get_confession(confession_id)
        if confession_data and confession_data[6] == 'approved':
            channel_message_id = confession_data[7]
            
            new_channel_text = format_channel_post(
                confession_id, 
                confession_data[3],
                confession_data[4]
            )
            
            await context.bot.edit_message_text(
                chat_id=CHANNEL_ID,
                message_id=channel_message_id,
                text=new_channel_text,
                reply_markup=get_channel_post_keyboard(confession_id, BOT_USERNAME), 
                parse_mode='Markdown'
            )
    except Exception as e:
        logger.error(f"Failed to update channel post comment count for #{confession_id}: {e}")
        
    await update.message.reply_text(
        "✅ *Comment posted anonymously!* Find it by browsing the confession again.",
        parse_mode='Markdown',
        reply_markup=get_main_keyboard(channel_link=f"https://t.me/{BOT_USERNAME}")
    )
    context.user_data.clear()
    return ConversationHandler.END

async def cancel_comment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancels the comment process."""
    query = update.callback_query
    await query.answer()
    
    confession_id = int(query.data.split('_')[-1])
    
    confessions = context.user_data.get('confessions_list', [])
    current_index = context.user_data.get('current_index', 0)
    
    if confessions:
        confession_data = confessions[current_index]
        formatted_text = format_browsing_confession(confession_data, current_index, len(confessions))
        
        await query.edit_message_text(
            formatted_text,
            reply_markup=get_confession_navigation(
                confession_id, 
                len(confessions), 
                current_index + 1
            ),
            parse_mode='Markdown'
        )
    else:
        await query.edit_message_text(
            "❌ Comment submission cancelled.",
            reply_markup=get_main_keyboard(channel_link=f"https://t.me/{BOT_USERNAME}")
        )
    
    context.user_data.clear()
    return BROWSING_CONFESSIONS
    
async def back_to_browse(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Returns to the original confession view after viewing comments."""
    query = update.callback_query
    await query.answer()
    
    confession_id = int(query.data.split('_')[-1])
    
    confessions = context.user_data.get('confessions_list', [])
    current_index = context.user_data.get('current_index', 0)
    
    if not confessions:
        await query.edit_message_text(
            "Session expired. Please use the main menu keyboard to start browsing again.",
            reply_markup=get_main_keyboard(channel_link=f"https://t.me/{BOT_USERNAME}")
        )
        return ConversationHandler.END

    confession_data = confessions[current_index]
    
    formatted_text = format_browsing_confession(confession_data, current_index, len(confessions))
    
    await query.edit_message_text(
        formatted_text,
        reply_markup=get_confession_navigation(
            confession_id, 
            len(confessions), 
            current_index + 1
        ),
        parse_mode='Markdown'
    )
    
    return BROWSING_CONFESSIONS

# --- Help and Info Handlers ---
async def show_help_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shows help information."""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        HELP_TEXT,
        parse_mode='Markdown',
        reply_markup=get_main_keyboard(channel_link=f"https://t.me/{BOT_USERNAME}")
    )

async def show_comments_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shows comments information."""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "ℹ️ *How to Comment*\n\n"
        "To read or add comments, please use the **📖 Browse** button, find a confession, and then use the 'View Comments' or 'Add Comment' buttons.",
        parse_mode='Markdown',
        reply_markup=get_main_keyboard(channel_link=f"https://t.me/{BOT_USERNAME}")
    )

# --- Fallback and Error Handling ---
async def fallback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fallback for unsupported messages while in a conversation state."""
    if update.message:
        await update.message.reply_text(
            "I didn't understand that. Please use the buttons or /start to begin.",
            reply_markup=get_main_keyboard(channel_link=f"https://t.me/{BOT_USERNAME}")
        )
    return ConversationHandler.END

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Log the error and send a message to the admin."""
    logger.error("Update '%s' caused error '%s'", update, context.error)
    
    if update and update.effective_chat:
        await update.effective_chat.send_message(
            "⚠️ An unexpected error occurred. The bot administrator has been notified.",
            reply_markup=get_main_keyboard(channel_link=f"https://t.me/{BOT_USERNAME}")
        )
        
    try:
        admin_error_message = f"🚨 BOT ERROR: {context.error}\n\nUpdate causing the error:\n{update}"
        await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID, 
            text=admin_error_message[:4096],
            parse_mode=None
        )
    except Exception as e:
        logger.error(f"Failed to send critical error notification to admin: {e}")

# --- MAIN FUNCTION WITH WEBHOOK FIX ---
def main() -> None:
    """Start the bot with enhanced instance management."""
    
    if not BOT_TOKEN:
        logger.error("Bot token is missing. Exiting.")
        return
        
    # Build application
    application = Application.builder().token(BOT_TOKEN).build()

    # Add all handlers
    submission_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_confession, pattern='^start_confess$')],
        states={
            SELECTING_CATEGORY: [
                CallbackQueryHandler(select_category, pattern='^cat_'),
                CallbackQueryHandler(cancel_confession, pattern='^cancel_confess$')
            ],
            WRITING_CONFESSION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_confession),
                CallbackQueryHandler(cancel_confession, pattern='^cancel_confess$')
            ]
        },
        fallbacks=[
            CommandHandler('start', start),
            MessageHandler(filters.TEXT | filters.COMMAND, fallback_handler)
        ],
        allow_reentry=True
    )
    application.add_handler(submission_handler)

    browsing_handler = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex('^📖 Browse$'), browse_menu),
            CallbackQueryHandler(browse_menu, pattern='^browse_menu$'),
        ],
        states={
            BROWSING_CONFESSIONS: [
                CallbackQueryHandler(start_browse_category, pattern='^browse_'),
                CallbackQueryHandler(navigate_confession, pattern='^(next|prev)_'),
                CallbackQueryHandler(view_comments, pattern='^view_comments_'),
                CallbackQueryHandler(start_add_comment, pattern='^add_comment_'),
                CallbackQueryHandler(back_to_browse, pattern='^back_browse_'),
                CallbackQueryHandler(cancel_comment, pattern='^cancel_comment_'),
                CallbackQueryHandler(main_menu, pattern='^back_browse_menu$'),
            ],
            WRITING_COMMENT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_comment),
                CallbackQueryHandler(cancel_comment, pattern='^cancel_comment_'),
            ]
        },
        fallbacks=[
            CommandHandler('start', start),
            CallbackQueryHandler(main_menu, pattern='^main_menu$'),
            MessageHandler(filters.TEXT | filters.COMMAND, fallback_handler)
        ],
        allow_reentry=True
    )
    application.add_handler(browsing_handler)
    
    # Other handlers
    application.add_handler(CallbackQueryHandler(handle_admin_approval, pattern='^(approve|reject|pending)_'))
    application.add_handler(CallbackQueryHandler(show_help_info, pattern='^help_info$'))
    application.add_handler(CallbackQueryHandler(show_comments_info, pattern='^comments_info$'))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_button))
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", start))
    application.add_handler(CallbackQueryHandler(handle_settings_callback, pattern='^settings_'))
    application.add_handler(CallbackQueryHandler(main_menu, pattern='^main_menu$|^back_main$'))
    application.add_error_handler(error_handler)

    # --- Webhook setup for Render ---
    RENDER_EXTERNAL_URL = os.getenv('RENDER_EXTERNAL_URL')
    
    if RENDER_EXTERNAL_URL:
        # Production: Use webhooks
        PORT = int(os.getenv('PORT', 10000))
        webhook_url = f"{RENDER_EXTERNAL_URL}/{BOT_TOKEN}"
        
        async def post_init(application):
            try:
                # Delete any existing webhook first
                await application.bot.delete_webhook()
                # Set new webhook
                await application.bot.set_webhook(webhook_url)
                logger.info(f"✅ Webhook successfully set to: {webhook_url}")
                print(f"✅ Webhook configured successfully")
            except Exception as e:
                logger.error(f"❌ Failed to set webhook: {e}")
                print(f"❌ Webhook setup failed: {e}")
            
        async def post_shutdown(application):
            try:
                await application.bot.delete_webhook()
                logger.info("✅ Webhook removed during shutdown")
                print("✅ Webhook removed during shutdown")
            except Exception as e:
                logger.error(f"❌ Error during webhook shutdown: {e}")
                print(f"❌ Error during webhook shutdown: {e}")
            
        print(f"🚀 Starting webhook on port {PORT}")
        print(f"🌐 Webhook URL: {webhook_url}")
        
        try:
            application.run_webhook(
                listen="0.0.0.0",
                port=PORT,
                webhook_url=webhook_url,
                secret_token='WEBHOOK_SECRET',
                post_init=post_init,
                post_shutdown=post_shutdown
            )
        except Exception as e:
            logger.error(f"❌ Webhook failed: {e}")
            print(f"❌ Webhook failed, switching to polling: {e}")
            # Fallback to polling if webhook fails
            print("🔄 Starting with polling as fallback...")
            application.run_polling(
                allowed_updates=Update.ALL_TYPES,
                close_loop=False
            )
    else:
        # Development: Use polling
        print("🔧 Development mode: Starting with polling...")
        application.run_polling(
            allowed_updates=Update.ALL_TYPES,
            close_loop=False
        )

if __name__ == '__main__':
    print("🤖 Starting Ethio Student Confessions Bot...")
    print("✅ Instance lock check passed")
    main()
