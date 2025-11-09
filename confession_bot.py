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
from dotenv import load_dotenv # <-- ADDED: For security

# --- Import Keyboards ---
from keyboards import (
    get_main_keyboard, 
    get_category_keyboard, 
    get_browse_keyboard, 
    get_confession_navigation, 
    get_admin_keyboard, 
    get_comments_management,
    get_channel_post_keyboard,
    get_settings_keyboard  # <-- ADDED: For settings button
)

# Load environment variables (from .env file)
load_dotenv()

# --- Configuration (READING FROM .ENV) ---
# NOTE: Ensure your .env file contains BOT_TOKEN, ADMIN_CHAT_ID (as a string), 
# CHANNEL_ID (as a string, e.g., "-100...") and BOT_USERNAME.

BOT_TOKEN = os.getenv("BOT_TOKEN") 
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")
# CRITICAL: Channel ID must be converted to an integer
try:
    CHANNEL_ID = int(os.getenv("CHANNEL_ID")) 
except (TypeError, ValueError):
    # Fallback/Error check if CHANNEL_ID is missing or not a valid number
    CHANNEL_ID = -100 # Safety fallback, but deployment should fail if missing
BOT_USERNAME = os.getenv("BOT_USERNAME")

if not all([BOT_TOKEN, ADMIN_CHAT_ID, CHANNEL_ID, BOT_USERNAME]):
    print("FATAL ERROR: One or more required environment variables (BOT_TOKEN, ADMIN_CHAT_ID, CHANNEL_ID, BOT_USERNAME) are missing or invalid.")
    # In a production environment, you would exit the script here.
    # For now, we continue but rely on the error handling in Application.builder().
    
# --- Logging Setup ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- NEW: Help Text Constant ---
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

🔒 *Your anonymity is our priority. stored to send you approval/rejection notices and is never shared.*
"""

# --- Conversation States and Categories ---
SELECTING_CATEGORY, WRITING_CONFESSION, BROWSING_CONFESSIONS, WRITING_COMMENT = range(4)

CATEGORIES_LIST = [
    "Academic Stress", "Friendship", "Love & Relationships", 
    "Regrets", "Achievements", "Fear & Anxiety", "Other"
]

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
            logger.info(f"DB fetched {len(comments)} comments for confession {confession_id}")
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
    
    # Fetch the current number of comments
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
            # If the tuple unpacking fails, log the error and insert a placeholder to keep the message from breaking.
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
    
    # Clear user data when starting, unless we're about to handle a deep link
    if not context.args:
        context.user_data.clear()

    # Check for deep link payload (e.g., /start viewconf_123)
    if context.args:
        return await handle_deep_link(update, context)

    # Normal start logic
    welcome_text = (
        "🤫 *WU Confession Bot*\n\n"
        "Welcome! Use the menu below to submit a confession, browse posts, or check settings."
    )
    
    # Ensure the user gets the main menu keyboard 
    await update.message.reply_text(
        welcome_text, 
        reply_markup=get_main_keyboard(), 
        parse_mode='Markdown'
    )
    return ConversationHandler.END # End any pending conversation


# --- UPDATED: handle_text_button for Help and Settings ---
async def handle_text_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles text button clicks from the ReplyKeyboardMarkup, including Help and Settings."""
    text = update.message.text
    
    if text == "💌 Submit Confession":
        # Start the submission conversation via callback query from an inline button
        await update.message.reply_text(
            "Click the button below to start your confession:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📝 Start Confession", callback_data="start_confess")]])
        )
        return ConversationHandler.END # Submission starts via the inline button's callback
        
    elif text == "📖 Browse":
        # Direct entry to the browsing menu
        return await browse_menu(update, context)
        
    elif text == "💬 Comments":
        # This provides information only
        await update.message.reply_text(
            "ℹ️ *How to Comment*\n\n"
            "To read or add comments, please use the **📖 Browse** button, find a confession, and then use the 'View Comments' or 'Add Comment' buttons.",
            parse_mode='Markdown',
            reply_markup=get_main_keyboard()
        )
        return ConversationHandler.END
        
    elif text == "❓ Help":
        # Sends the HELP_TEXT
        await update.message.reply_text(
            HELP_TEXT,
            parse_mode='Markdown',
            reply_markup=get_main_keyboard()
        )
        return ConversationHandler.END
        
    elif text == "⚙️ Settings":
        # Sends the settings keyboard
        await update.message.reply_text(
            "⚙️ *Settings Menu*\n\n"
            "These features are not yet implemented, but will be available in the future.",
            reply_markup=get_settings_keyboard(), # From keyboards.py
            parse_mode='Markdown'
        )
        return ConversationHandler.END
    
    # Fallback if the text doesn't match a known button
    return ConversationHandler.END


async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Return to main menu from an inline callback (e.g., from Settings or Cancel)."""
    query = update.callback_query
    await query.answer()
    
    welcome_text = "🤫 *WU Confession Bot*\n\nWelcome back! Use the keyboard below."
    
    try:
        # Try to edit the message (e.g., coming from Settings)
        await query.edit_message_text(
            welcome_text, 
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.warning(f"main_menu edit failed (often OK if message is identical): {e}")
        
    return ConversationHandler.END

# --- NEW: handle_settings_callback function ---
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
            reply_markup=get_main_keyboard() 
        )
        
    except Exception as e:
        logger.error(f"Failed to send admin message: {e}")
        await update.message.reply_text(
            "❌ *Error sending admin notification.* The confession is saved but pending.",
            parse_mode='Markdown',
            reply_markup=get_main_keyboard()
        )
    
    context.user_data.clear()
    return ConversationHandler.END

async def handle_admin_approval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle admin approval/rejection."""
    query = update.callback_query
    await query.answer()
    
    if str(query.from_user.id) != ADMIN_CHAT_ID:
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
            await query.answer("❌ Failed to post to channel. Check bot permissions and BOT_USERNAME.", show_alert=True)
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
    
    action, _ = query.data.split('_')
    current_index = context.user_data.get('current_index', 0)
    confessions = context.user_data.get('confessions_list', [])
    total_confessions = len(confessions)
    
    # If the list only has 1 item (from a deep link), don't navigate
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
    
    # Debug logging: Check if comments are fetched
    logger.info(f"Handler received {len(comments)} comments for confession {confession_id}.")

    formatted_comments = format_comments_list(confession_id, comments)
    
    # Store current browsing message data to return to it later
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
        f"✍️ *Adding Comment to Confession #{confession_id}*\n\n"
        "Please type your comment below (max 500 characters):",
        parse_mode='Markdown'
    )
    
    return WRITING_COMMENT

async def receive_comment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receives and saves the comment text."""
    comment_text = update.message.text.strip()
    confession_id = context.user_data.get('comment_confession_id')
    
    if not confession_id:
        await update.message.reply_text("❌ Error: Confession ID missing. Start again via /start.", reply_markup=get_main_keyboard())
        context.user_data.clear()
        return ConversationHandler.END

    if not (1 <= len(comment_text) <= 500):
        await update.message.reply_text("❌ Comment must be between 1 and 500 characters. Try again:")
        return WRITING_COMMENT
        
    user_id = update.effective_user.id
    username = update.effective_user.first_name or "Anonymous"
    
    if db.save_comment(confession_id, user_id, username, comment_text):
        
        # --- Channel Post Update ---
        # When a comment is added, we must update the channel post to show the new count.
        confession_full = db.get_confession(confession_id)
        if confession_full and confession_full[6] == 'approved' and confession_full[7]:
            channel_message_id = confession_full[7]
            category = confession_full[3]
            confession_text = confession_full[4]
            
            # Regenerate text with new comment count
            new_channel_text = format_channel_post(confession_id, category, confession_text)
            
            try:
                await context.bot.edit_message_text(
                    chat_id=CHANNEL_ID,
                    message_id=channel_message_id,
                    text=new_channel_text,
                    reply_markup=get_channel_post_keyboard(confession_id, BOT_USERNAME), 
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.warning(f"Could not update channel post for Confession #{confession_id}: {e}")
        # --- End Channel Post Update ---

        # The user has successfully commented. Return them to the main menu.
        await update.message.reply_text(
            f"✅ Your comment has been added to *Confession #{confession_id}*!",
            parse_mode='Markdown',
            reply_markup=get_main_keyboard()
        )
    else:
        await update.message.reply_text("❌ Failed to save comment due to a database error.", reply_markup=get_main_keyboard())
    
    context.user_data.clear()
    return ConversationHandler.END

async def back_to_browsing(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Returns to the specific confession view after managing comments."""
    query = update.callback_query
    await query.answer()

    # Re-fetch the data used to display the confession
    confessions = context.user_data.get('confessions_list')
    current_index = context.user_data.get('current_index')
    
    if not confessions or current_index is None:
        # Fallback if browsing context is lost
        return await start(update, context) # Go back to start, which will display the main menu

    confession_data = confessions[current_index]
    formatted_text = format_browsing_confession(confession_data, current_index, len(confessions))
    confession_id = confession_data[0]

    try:
        await query.edit_message_text(
            formatted_text,
            reply_markup=get_confession_navigation(
                confession_id, 
                len(confessions), 
                current_index + 1
            ),
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Failed to edit message back to browsing view: {e}")
        # Send as a new message if editing fails (e.g., message too old)
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
        
    return BROWSING_CONFESSIONS


# --- Main Function ---
def main():
    """Start the bot with appropriate handlers."""
    print("🚀 Starting WU Confession Bot...")
    
    custom_timeout = 30.0 
    application = Application.builder().token(BOT_TOKEN).read_timeout(custom_timeout).connect_timeout(custom_timeout).build()
    
    # --- Conversation Handlers ---
    
    # 1. Confession Submission Flow
    confession_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(start_confession, pattern="^start_confess$")
        ],
        states={
            SELECTING_CATEGORY: [
                CallbackQueryHandler(select_category, pattern="^cat_"),
                CallbackQueryHandler(cancel_confession, pattern="^cancel$")
            ],
            WRITING_CONFESSION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_confession),
            ]
        },
        fallbacks=[CommandHandler('start', start)]
    )
    
    # 2. Comment Submission Flow (Single State, initiated from browsing)
    comment_submission_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_add_comment, pattern="^add_comment_")],
        states={
            WRITING_COMMENT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_comment),
            ]
        },
        fallbacks=[CommandHandler('start', start)]
    )

    # 3. Browsing Flow
    browse_handler = ConversationHandler(
        entry_points=[
            # Primary entry via Reply Keyboard Button
            MessageHandler(filters.Regex("^📖 Browse$"), browse_menu),
            # Entry via back button from category selection:
            CallbackQueryHandler(start_browse_category, pattern="^back_browse$"), 
        ],
        states={
            BROWSING_CONFESSIONS: [
                # Navigation / Selection Callbacks
                CallbackQueryHandler(start_browse_category, pattern="^browse_"),
                CallbackQueryHandler(navigate_confession, pattern="^(prev|next)_"),
                CallbackQueryHandler(view_comments, pattern="^view_comments_"),
                CallbackQueryHandler(back_to_browsing, pattern="^back_to_confession$"), # Return from comments list
                
                # Handlers that exit this conversation 
                CallbackQueryHandler(main_menu, pattern="^back_main$"), # Exit browsing to main menu
            ],
        },
        fallbacks=[CommandHandler('start', start)]
    )

    # --- Add Handlers to the application ---
    # The /start handler must be first to catch deep links (e.g., /start viewconf_123)
    application.add_handler(CommandHandler("start", start)) 
    application.add_handler(confession_handler)
    application.add_handler(comment_submission_handler)
    application.add_handler(browse_handler)
    
    # Other handlers
    application.add_handler(CallbackQueryHandler(main_menu, pattern="^(main_menu|back_main)$"))
    application.add_handler(CallbackQueryHandler(handle_admin_approval, pattern="^(approve|reject|pending)_"))
    application.add_handler(CallbackQueryHandler(handle_settings_callback, pattern="^settings_")) # <-- ADDED: Settings placeholder callbacks

    # --- Admin Commands (Requires admin.py file) ---
    try:
        from admin import admin_stats, view_pending, handle_pagination_callback
        
        application.add_handler(CommandHandler("stats", admin_stats))
        application.add_handler(CommandHandler("pending", lambda update, context: view_pending(update, context, offset=0)))
        application.add_handler(CallbackQueryHandler(handle_pagination_callback, pattern=r'^page_\d+$'))
        
        logger.info("✅ Successfully loaded admin commands (stats, pending, pagination).")
        
    except ImportError:
        logger.warning("Could not import from admin.py. Admin commands will not work.")
    except Exception as e:
        logger.error(f"Error loading admin handlers: {e}")
    
    # Handle main menu button presses that aren't part of a conversation
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_button))
    
    # Start the Bot
    print("🤖 Bot is running. Press Ctrl+C to stop.")
    application.run_polling(poll_interval=1.0) 

if __name__ == '__main__':
    # Initialize database when the bot starts
    db.init_database()
    main()