# File name: confession_bot.py

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
import os
from dotenv import load_dotenv

# --- Conversation States and Categories ---
SELECTING_CATEGORY, WRITING_CONFESSION, BROWSING_CONFESSIONS, WRITING_COMMENT = range(4)

CATEGORIES_LIST = [
    "Academic Stress", "Friendship", "Love & Relationships", 
    "Regrets", "Achievements", "Fear & Anxiety", "Other"
]

CATEGORY_MAP = {
    "relationship": "Love & Relationships", "friendship": "Friendship", 
    "campus": "Academic Stress", "general": "Other", 
    "vent": "Fear & Anxiety", "secret": "Regrets", "recent": "Recent",
    "achievements": "Achievements", "other": "Other" 
}


# --- Import Keyboards (Assuming you have a 'keyboards.py' file) ---
# NOTE: If you don't have this file, you will need to define the keyboard functions 
# (get_main_keyboard, get_category_keyboard, etc.) directly in this file.
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
    print("WARNING: 'keyboards.py' not found. Define dummy keyboards or create the file.")
    # Define dummy keyboards to prevent crash if file is missing (for demonstration)
    def get_main_keyboard(): 
        # Standard main menu buttons (assuming ReplyKeyboardMarkup is handled by calling code)
        return InlineKeyboardMarkup([[InlineKeyboardButton("Start", callback_data="start")]])
    
    def get_category_keyboard(): 
        # CORRECTED SYNTAX ERROR HERE
        buttons = []
        for key, name in CATEGORY_MAP.items():
            if key != "recent":
                # Line 62: Corrected from `buttons.append([InlineKeyboardButton(...)])` 
                # to `buttons.append([InlineKeyboardButton(...)])`
                buttons.append([InlineKeyboardButton(name, callback_data=f"cat_{key}")]]) 
        return InlineKeyboardMarkup(buttons or [[InlineKeyboardButton("Other", callback_data="cat_other")]])
        
    def get_browse_keyboard(show_back=False): 
        buttons = [[InlineKeyboardButton("Latest", callback_data="browse_recent")]]
        if show_back:
            buttons.append([InlineKeyboardButton("🔙 Back to Browse Menu", callback_data="back_browse")])
        return InlineKeyboardMarkup(buttons)
        
    def get_confession_navigation(c_id, total, index): 
        nav_row = []
        if index > 1:
            nav_row.append(InlineKeyboardButton("⬅️ Prev", callback_data="prev_conf"))
        if index < total:
            nav_row.append(InlineKeyboardButton("Next ➡️", callback_data="next_conf"))
        return InlineKeyboardMarkup([
            nav_row,
            [InlineKeyboardButton("💬 View Comments", callback_data=f"view_comments_{c_id}")],
            [InlineKeyboardButton("📝 Add Comment", callback_data=f"add_comment_{c_id}")],
            [InlineKeyboardButton("🔙 Back to Browse Menu", callback_data="back_browse")]
        ])
        
    def get_admin_keyboard(c_id): 
        return InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Approve", callback_data=f"approve_{c_id}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"reject_{c_id}")
        ]])
        
    def get_comments_management(c_id): 
        return InlineKeyboardMarkup([[InlineKeyboardButton("📝 Add Comment", callback_data=f"add_comment_{c_id}"), InlineKeyboardButton("🔙 Back to Confession", callback_data=f"go_to_conf_{c_id}")]])
        
    def get_channel_post_keyboard(c_id, username): 
        return InlineKeyboardMarkup([[InlineKeyboardButton("Comment Here 💬", url=f"t.me/{username}?start=viewconf_{c_id}")]])
        
    def get_settings_keyboard(): 
        return InlineKeyboardMarkup([[
            InlineKeyboardButton("🔔 Notifications", callback_data="settings_notifications"),
            InlineKeyboardButton("🌙 Dark Mode", callback_data="settings_darkmode"),
            InlineKeyboardButton("🔙 Back to Main Menu", callback_data="back_main")
        ]])


# Load environment variables (from .env file)
load_dotenv()

# --- Configuration (READING FROM .ENV) ---
BOT_TOKEN = os.getenv("BOT_TOKEN") 
ADMIN_CHAT_ID_RAW = os.getenv("ADMIN_CHAT_ID") or os.getenv("ADMIN_IDS") 
ADMIN_CHAT_ID = [id.strip() for id in ADMIN_CHAT_ID_RAW.split(',')] if ADMIN_CHAT_ID_RAW else []

try:
    CHANNEL_ID = int(os.getenv("CHANNEL_ID")) 
except (TypeError, ValueError):
    CHANNEL_ID = None 

BOT_USERNAME = os.getenv("BOT_USERNAME")

if not all([BOT_TOKEN, ADMIN_CHAT_ID, CHANNEL_ID, BOT_USERNAME]):
    print("FATAL ERROR: One or more required environment variables (BOT_TOKEN, ADMIN_CHAT_ID/ADMIN_IDS, CHANNEL_ID, BOT_USERNAME) are missing or invalid.")
    import sys
    sys.exit(1)
    
# --- Logging Setup ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Help Text Constant ---
HELP_TEXT = """
❓ *Bot Help & Guidelines*

Here's how to use the bot:

* **💌 Submit Confession**: Press this button to start the anonymous submission process.
    1.  Choose a category.
    2.  Write your confession.
    3.  It will be sent to an admin for review.
    4.  You will be notified if it's approved or rejected.

* **📖 Browse**: Read confessions that have already been approved.
    1.  Select a category or "Latest".
    2.  Use the ⬅️ and ➡️ buttons to navigate.
    3.  Click "View Comments" to read what others have said.
    4.  Click "Add Comment" to write your own anonymous reply.

* **💬 Comments**: This button is just a reminder! To read or add comments, you must use the **📖 Browse** feature and find a confession first.

* **⚙️ Settings**: (Coming Soon) Manage your bot preferences.

🔒 *Your anonymity is our priority. User IDs are stored to send you approval/rejection notices and are never shared.*
"""


# --- Database Management ---
class DatabaseManager:
    def __init__(self):
        self.init_database()
    
    def init_database(self):
        """Initialize database and ensure the schema is correct, creating comments table."""
        conn = None
        try:
            conn = sqlite3.connect('confessions.db', check_same_thread=False)
            cursor = conn.cursor()
            
            # Confessions Table
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
            
            # Comments Table
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
        """Update confession status and optionally the channel_message_id."""
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
        """Get confession by ID. Returns the full row."""
        conn = None
        try:
            conn = sqlite3.connect('confessions.db', check_same_thread=False)
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM confessions WHERE id = ?', (confession_id,))
            result = cursor.fetchone()
            return result
        except Exception as e:
            logger.error(f"❌ Error getting confession: {e}")
            return None
        finally:
            if conn:
                conn.close()
    
    def get_approved_confessions(self, category=None):
        """Fetches approved confessions, optionally filtered by category, ordered by recency."""
        conn = None
        try:
            conn = sqlite3.connect('confessions.db', check_same_thread=False)
            cursor = conn.cursor()
            
            if category and category != "Recent":
                # Filter by exact category name
                cursor.execute(
                    'SELECT id, confession_text, category, timestamp FROM confessions WHERE status = "approved" AND category = ? ORDER BY id DESC', 
                    (category,)
                )
            else:
                # Default to fetching all recent approved confessions
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
            # Select username, comment_text, and timestamp
            cursor.execute(
                'SELECT username, comment_text, timestamp FROM comments WHERE confession_id = ? ORDER BY timestamp ASC', 
                (confession_id,)
            )
            comments = cursor.fetchall()
            logger.info(f"DB fetched {len(comments)} comments for confession {confession_id}.")

            return comments
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
    """Formats the text for the channel post with the required UI elements and comments count."""
    
    comments_count = db.get_comments_count(confession_id) # Fetches count directly
    
    post_header = f"Confession from Anonymous #{confession_id}"
    category_tag = f"#{category.replace(' ', '_').replace('&', 'and')}" 
    
    channel_text = (
        f"*{post_header}*\n\n"
        f"{confession_text}\n\n"
        f"Category: {category_tag}\n"
        f"Comments: 💬 {comments_count}" # Display comment count
    )
    return channel_text

def format_browsing_confession(confession_data, index, total_confessions):
    """Formats a single confession for browsing."""
    # Data is (id, text, category, timestamp)
    confession_id, text, category, timestamp = confession_data
    
    try:
        dt = datetime.fromisoformat(timestamp)
        date_str = dt.strftime("%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        date_str = timestamp
        
    comments_count = db.get_comments_count(confession_id)
    
    formatted_text = (
        f"📝 *Confession #{confession_id}* ({index + 1}/{total_confessions})\n\n"
        f"*{category}* - Shared {date_str}\n\n"
        f"{text}\n\n"
        f"💬 Comments: {comments_count}"
    )
    return formatted_text

def format_comments_list(confession_id, comments_list):
    """Formats the list of comments for display. Added error handling for resilient formatting."""
    header = f"💬 *Comments for Confession #{confession_id}* ({len(comments_list)} total)\n\n"
    
    if not comments_list:
        return header + "No comments yet. Be the first one!"
        
    comment_blocks = []
    
    for i, comment_tuple in enumerate(comments_list):
        try:
            # We expect (username, text, timestamp) from the get_comments query
            username, text, timestamp = comment_tuple 
            
            # Anonymize the name for display
            anon_name = f"User {i+1}"
            
            time_str = ""
            try:
                dt = datetime.fromisoformat(timestamp.split('.')[0])
                time_str = dt.strftime('%H:%M %b %d')
            except Exception:
                time_str = "just now"

            comment_block = (
                f"👤 *{anon_name}* ({time_str}):\n"
                f"» {text}\n"
            )
            comment_blocks.append(comment_block)
            
        except ValueError as e:
            logger.error(f"❌ Error unpacking comment tuple for Confession #{confession_id}: {e} -> {comment_tuple}")
            comment_blocks.append(f"❌ *[Comment #{i+1} failed to load due to data structure error]*")
            continue 
            
    return header + "\n---\n".join(comment_blocks)

# --- Handler Functions (Start and Main Menu) ---

async def handle_deep_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles deep links like /start viewconf_123."""
    payload = context.args[0]
    
    if not payload.startswith('viewconf_'):
        return ConversationHandler.END # Not a deep link we handle here
    
    try:
        confession_id = int(payload.split('_')[1])
    except (IndexError, ValueError):
        await update.message.reply_text("❌ Invalid confession link.", reply_markup=get_main_keyboard())
        return ConversationHandler.END

    confession_full = db.get_confession(confession_id)
    
    if not confession_full or confession_full[6] != 'approved': # Index 6 is status
        await update.message.reply_text("❌ Sorry, that confession is not approved or does not exist.", reply_markup=get_main_keyboard())
        return ConversationHandler.END

    # Data structure (id, text, category, timestamp)
    confession_data = (confession_full[0], confession_full[4], confession_full[3], confession_full[5])
    
    # Store this single confession as the list for browsing 
    context.user_data['confessions_list'] = [confession_data]
    context.user_data['current_index'] = 0 
    
    await update.message.reply_text(
        "You were redirected from the channel post:",
        parse_mode='Markdown'
    )

    # Use display_confession to send the message with the proper navigation keyboard
    await display_confession(update, context, via_callback=False)
    
    return BROWSING_CONFESSIONS # Enter browsing state


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send welcome message and main keyboard when /start is issued, and check for deep link."""
    
    if not context.args:
        context.user_data.clear()

    if context.args:
        return await handle_deep_link(update, context)

    welcome_text = (
        "🤫 *Confession Bot*\n\n"
        "Welcome! Use the menu below to submit a confession, browse posts, or check settings."
    )
    
    await update.message.reply_text(
        welcome_text, 
        reply_markup=get_main_keyboard(), 
        parse_mode='Markdown'
    )
    return ConversationHandler.END # End any pending conversation


async def handle_text_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles text button clicks from the ReplyKeyboardMarkup, including Help and Settings."""
    text = update.message.text
    
    if text == "💌 Submit Confession":
        # Start the submission conversation via callback query from an inline button
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
            reply_markup=get_main_keyboard()
        )
        return ConversationHandler.END
        
    elif text == "❓ Help":
        await update.message.reply_text(
            HELP_TEXT,
            parse_mode='Markdown',
            reply_markup=get_main_keyboard()
        )
        return ConversationHandler.END
        
    elif text == "⚙️ Settings":
        await update.message.reply_text(
            "⚙️ *Settings Menu*\n\n"
            "Manage bot preferences.",
            reply_markup=get_settings_keyboard(), 
            parse_mode='Markdown'
        )
        return ConversationHandler.END
    
    return ConversationHandler.END


async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Return to main menu from an inline callback (e.g., from Settings or Cancel)."""
    query = update.callback_query
    await query.answer()
    
    welcome_text = "🤫 *Confession Bot*\n\nWelcome back! Use the keyboard below."
    
    try:
        await query.edit_message_text(
            welcome_text, 
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.warning(f"main_menu edit failed (often OK if message is identical): {e}")
        
    return ConversationHandler.END


async def handle_settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles callbacks from the settings menu (currently placeholders)."""
    query = update.callback_query
    
    if query.data == "settings_notifications":
        await query.answer("🔔 Notification settings are not yet implemented.", show_alert=True)
    elif query.data == "settings_darkmode":
        await query.answer("🌙 Dark mode settings are not yet implemented.", show_alert=True)
    
    # The 'back_main' button is handled by the main_menu handler (pattern="^back_main$")

# --- Confession Submission Logic ---

async def start_confession(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the confession process by prompting for category selection (Inline Callback)."""
    query = update.callback_query
    await query.answer()
    
    context.user_data.clear() # Ensure user data is clean for a new submission
    
    await query.edit_message_text(
        "📂 *Select a category for your confession:*",
        reply_markup=get_category_keyboard(),
        parse_mode='Markdown'
    )
    
    return SELECTING_CATEGORY

async def select_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle category selection and move to writing state."""
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
    
    # 1. SAVE TO DB
    confession_id = db.save_confession(user_id, username, category, confession_text)
    if not confession_id:
        await update.message.reply_text("❌ *Error submitting confession.* Please try again later.", parse_mode='Markdown')
        context.user_data.clear()
        return ConversationHandler.END

    # 2. SEND ADMIN APPROVAL MESSAGE
    admin_message = (
        f"🆕 *Confession #*{confession_id} is *PENDING*\n\n"
        f"👤 *User:* {username} (ID: {user_id})\n"
        f"📂 *Category:* {category}\n"
        f"📝 *Text:* {confession_text}\n\n"
        f"*Admin Action:*"
    )
    
    try:
        # Loop through all ADMIN_CHAT_ID list members
        for admin_id in ADMIN_CHAT_ID:
            logger.info(f"Attempting to send admin notification to Chat ID: {admin_id}") 
            await context.bot.send_message(
                chat_id=admin_id,
                text=admin_message,
                reply_markup=get_admin_keyboard(confession_id), 
                parse_mode='Markdown',
                disable_web_page_preview=True
            )
        
        await update.message.reply_text(
            "✅ *Confession Submitted!*\n\n"
            "Your confession has been sent for admin review. You'll be notified of the outcome. 🔒",
            parse_mode='Markdown',
            reply_markup=get_main_keyboard() 
        )
        
    except Exception as e:
        logger.error(f"Failed to send admin message: {e}")
        await update.message.reply_text(
            "❌ *Error sending admin notification.* The confession is saved but pending. (Check logs for the full API error)",
            parse_mode='Markdown',
            reply_markup=get_main_keyboard()
        )
    
    context.user_data.clear()
    return ConversationHandler.END

async def handle_admin_approval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle admin approval/rejection."""
    query = update.callback_query
    await query.answer()
    
    # CRITICAL: Check if the user is in the ADMIN_CHAT_ID list
    # Note: query.from_user.id is an integer, ADMIN_CHAT_ID elements are strings
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
            # Format channel text, which now includes the comment count (which is 0 initially)
            channel_text = format_channel_post(confession_id, category, confession_text)
            
            # Post the message to the channel WITH THE DEEP LINK BUTTON
            channel_message = await context.bot.send_message(
                chat_id=CHANNEL_ID,
                text=channel_text,
                reply_markup=get_channel_post_keyboard(confession_id, BOT_USERNAME), 
                parse_mode='Markdown'
            )
            
            # Update DB with approved status and channel message ID
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
        
        # Do not notify user if manually set back to pending
        return await query.edit_message_text(
            f"{status_emoji} *Confession {status_text}!*\n\n"
            f"Confession #{confession_id} is back in the queue.",
            parse_mode='Markdown'
        )

    # Notify user (if approved/rejected)
    try:
        if user_message:
            await context.bot.send_message(chat_id=user_id, text=user_message, parse_mode='Markdown')
    except Exception as e:
        logger.warning(f"Could not notify user {user_id}: {e}")
    
    # Update admin message
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
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")]])
    )
    context.user_data.clear()
    return ConversationHandler.END

# --- Browsing Logic ---

async def browse_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Shows the browsing category menu."""
    # This is the MessageHandler entry point
    await update.message.reply_text(
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
    
    # Determine the message sending method
    if via_callback:
        # Edit the message if it came from an inline button press
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
             logger.warning(f"Error editing message during navigation (often OK if message is identical): {e}")
    else:
        # Send a new message if it came from a deep link or text command
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
    
    action = query.data.split('_')[0]
    confessions = context.user_data.get('confessions_list', [])
    current_index = context.user_data.get('current_index', 0)
    
    new_index = current_index
    if action == 'next':
        if current_index < len(confessions) - 1:
            new_index += 1
    elif action == 'prev':
        if current_index > 0:
            new_index -= 1
            
    context.user_data['current_index'] = new_index
    
    await display_confession(update, context, via_callback=True)
    return BROWSING_CONFESSIONS

async def back_to_browse_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Goes back to the category selection menu."""
    query = update.callback_query
    await query.answer()
    
    # Clear confession list data
    context.user_data.pop('confessions_list', None)
    context.user_data.pop('current_index', None)
    
    await query.edit_message_text(
        "📚 *Browse Confessions by Category:* \n\nSelect a category or *Latest*:",
        reply_markup=get_browse_keyboard(show_back=False),
        parse_mode='Markdown'
    )
    return BROWSING_CONFESSIONS

async def go_to_confession(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Re-displays a specific confession after viewing comments or starting the comment flow."""
    query = update.callback_query
    await query.answer()
    
    try:
        confession_id = int(query.data.split('_')[2])
    except IndexError:
        await query.answer("Error finding confession ID.", show_alert=True)
        return BROWSING_CONFESSIONS

    # We need to re-fetch the list if it's missing (e.g., bot restart)
    if 'confessions_list' not in context.user_data:
        # Fetch just this one confession to ensure it can be displayed
        confession_full = db.get_confession(confession_id)
        if not confession_full:
            await query.edit_message_text("Confession not found.")
            return BROWSING_CONFESSIONS
        
        # Data structure (id, text, category, timestamp)
        confession_data = (confession_full[0], confession_full[4], confession_full[3], confession_full[5])
        context.user_data['confessions_list'] = [confession_data]
        context.user_data['current_index'] = 0
    
    # Find the index of the confession_id in the current list
    try:
        index = next(i for i, data in enumerate(context.user_data['confessions_list']) if data[0] == confession_id)
        context.user_data['current_index'] = index
    except StopIteration:
        # If it's not in the current browsing list, we can't maintain the browsing session.
        pass

    await display_confession(update, context, via_callback=True)
    return BROWSING_CONFESSIONS


# --- Comment Logic ---

async def view_comments(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Fetches and displays comments for the current confession."""
    query = update.callback_query
    await query.answer()
    
    confession_id = int(query.data.split('_')[2])
    
    comments = db.get_comments(confession_id)
    formatted_comments = format_comments_list(confession_id, comments)
    
    await query.edit_message_text(
        formatted_comments,
        reply_markup=get_comments_management(confession_id),
        parse_mode='Markdown'
    )
    
    return BROWSING_CONFESSIONS # Stay in browsing state


async def start_add_comment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Prompts the user to write a comment."""
    query = update.callback_query
    await query.answer()
    
    confession_id = int(query.data.split('_')[2])
    context.user_data['comment_confession_id'] = confession_id
    
    await query.edit_message_text(
        f"📝 *Write your anonymous comment for Confession #{confession_id}:*",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel Comment", callback_data="cancel_comment")]])
    )
    
    return WRITING_COMMENT

async def receive_comment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Saves the comment to the DB and updates the channel post count."""
    user_id = update.effective_user.id
    username = update.effective_user.first_name or "Anonymous"
    comment_text = update.message.text.strip()
    confession_id = context.user_data.get('comment_confession_id')
    
    if not confession_id:
        await update.message.reply_text("❌ Error: Could not link comment. Please try again from the Browse menu.")
        return ConversationHandler.END
        
    if not (1 <= len(comment_text) <= 500):
        await update.message.reply_text(
            "❌ *Comment must be between 1 and 500 characters.*\n\n"
            "Try again:",
            parse_mode='Markdown'
        )
        return WRITING_COMMENT
        
    # 1. SAVE TO DB
    comment_id = db.save_comment(confession_id, user_id, username, comment_text)
    
    if not comment_id:
        await update.message.reply_text("❌ *Error saving comment.* Please try again later.", parse_mode='Markdown')
        context.user_data.pop('comment_confession_id', None)
        return ConversationHandler.END

    # 2. UPDATE CHANNEL POST COUNT
    confession = db.get_confession(confession_id)
    if confession and confession[7]: # Index 7 is channel_message_id
        channel_message_id = confession[7]
        category = confession[3]
        confession_text = confession[4]
        
        try:
            # Reformat the post to get the updated comment count
            updated_text = format_channel_post(confession_id, category, confession_text)
            
            await context.bot.edit_message_text(
                chat_id=CHANNEL_ID,
                message_id=channel_message_id,
                text=updated_text,
                reply_markup=get_channel_post_keyboard(confession_id, BOT_USERNAME),
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Failed to update channel post {channel_message_id} count: {e}")
            
    await update.message.reply_text("✅ *Comment submitted anonymously!*")
    
    context.user_data.pop('comment_confession_id', None)
    
    # After commenting, we transition back to the main menu state for safe operation
    return ConversationHandler.END

async def cancel_comment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the comment writing process."""
    query = update.callback_query
    await query.answer()
    
    confession_id = context.user_data.get('comment_confession_id')
    
    context.user_data.pop('comment_confession_id', None)
    
    if confession_id:
        # If possible, return to the confession view
        # We need the update object to be a Message or CallbackQuery for go_to_confession.
        # Since this came from a CallbackQuery, we simulate a 'go_to_conf' event
        
        # Temporarily fake the query data to reuse go_to_confession logic
        query.data = f"go_to_conf_{confession_id}"
        await go_to_confession(update, context) 
        return BROWSING_CONFESSIONS
    else:
        # Fallback to main menu
        await query.edit_message_text(
            "❌ Comment cancelled.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")]])
        )
        return ConversationHandler.END

# --- Main Application Setup ---

def main():
    """Starts the bot."""
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN is not set.")
        return
        
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Fallback function for /cancel command during confession/commenting
    async def cancel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("Operation cancelled.", reply_markup=get_main_keyboard())
        return ConversationHandler.END
        
    # 1. Submission Conversation Handler (Category -> Write -> Submit)
    confession_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_confession, pattern="^start_confess$")],
        
        states={
            SELECTING_CATEGORY: [
                CallbackQueryHandler(select_category, pattern="^cat_"),
                CallbackQueryHandler(cancel_confession, pattern="^cancel_confess$")
            ],
            WRITING_CONFESSION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_confession)
            ],
        },
        
        fallbacks=[CommandHandler("cancel", cancel_handler), CallbackQueryHandler(cancel_confession, pattern="^cancel_confess$")]
    )

    # 2. Comment Conversation Handler (Started from a button, waiting for text)
    comment_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_add_comment, pattern="^add_comment_")],
        states={
            WRITING_COMMENT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_comment),
                CallbackQueryHandler(cancel_comment, pattern="^cancel_comment$")
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel_handler)]
    )
    
    # 3. Browsing Conversation Handler (Category Selection -> Navigation)
    browsing_conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^📖 Browse$"), browse_menu)], 
        states={
            BROWSING_CONFESSIONS: [
                CallbackQueryHandler(start_browse_category, pattern="^browse_"),
                CallbackQueryHandler(navigate_confession, pattern="^next_conf$|^prev_conf$"),
                CallbackQueryHandler(view_comments, pattern="^view_comments_"),
                CallbackQueryHandler(go_to_confession, pattern="^go_to_conf_"),
                CallbackQueryHandler(back_to_browse_menu, pattern="^back_browse$"),
            ]
        },
        fallbacks=[CommandHandler("cancel", back_to_browse_menu)]
    )

    # --- Handlers ---
    app.add_handler(CommandHandler("start", start))
    
    # Message Handlers for Reply Keyboard buttons
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_button))
    
    # Conversations
    app.add_handler(confession_conv_handler)
    app.add_handler(comment_conv_handler)
    app.add_handler(browsing_conv_handler)

    # General Callbacks
    app.add_handler(CallbackQueryHandler(handle_admin_approval, pattern="^approve_|^reject_|^pending_"))
    app.add_handler(CallbackQueryHandler(main_menu, pattern="^main_menu$|^back_main$"))
    app.add_handler(CallbackQueryHandler(handle_settings_callback, pattern="^settings_"))

    logger.info("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
