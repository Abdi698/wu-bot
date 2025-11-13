# File name: confession_bot.py

import logging
import sqlite3
from datetime import datetime
import os
from dotenv import load_dotenv
from typing import List, Tuple, Optional, Dict

# Telegram Imports
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    constants
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
    ConversationHandler
)

# Import all keyboard functions from the provided keyboards.py
# NOTE: This line requires the keyboards.py file to exist in the same directory.
from keyboards import (
    get_main_keyboard,
    get_category_keyboard,
    get_browse_keyboard,
    get_admin_keyboard,
    get_channel_post_keyboard,
    get_confession_navigation,
    get_comments_management,
    get_settings_keyboard
)

# --- Configuration & Setup ---
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
# Get Channel ID (as int) and Channel Link for keyboard
try:
    CHANNEL_ID = int(os.getenv("CHANNEL_ID"))
except (TypeError, ValueError):
    CHANNEL_ID = os.getenv("CHANNEL_ID")
CHANNEL_LINK = os.getenv("CHANNEL_LINK", "https://t.me/telegram") # Default link
BOT_USERNAME = os.getenv("BOT_USERNAME") # Required for deep linking

ADMIN_IDS_RAW = os.getenv("ADMIN_IDS")
ADMIN_IDS: List[int] = [int(x.strip()) for x in ADMIN_IDS_RAW.split(",")] if ADMIN_IDS_RAW else []

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Conversation States and Categories ---
SELECTING_CATEGORY, WRITING_CONFESSION, BROWSING_CONFESSIONS, WRITING_COMMENT = range(4)

# Map from callback keys (used in keyboards.py) to display names
CATEGORY_MAP: Dict[str, str] = {
    "relationship": "💕 Love", "friendship": "👥 Friends", 
    "campus": "🎓 Campus", "general": "😊 General", 
    "vent": "😢 Vent", "secret": "🤫 Secret", 
    "recent": "🆕 Latest" # 'recent' is a virtual category for browsing
}

# --- Database Manager Class ---
class DatabaseManager:
    def __init__(self, db_path="confessions.db"):
        self.db_path = db_path
        self._initialize_db()

    def _get_conn(self):
        return sqlite3.connect(self.db_path, check_same_thread=False)

    def _initialize_db(self):
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS confessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                category TEXT,             -- NEW: Added category column
                text TEXT,
                approved INTEGER DEFAULT 0,  -- 0: Pending, 1: Approved, 2: Rejected
                channel_message_id INTEGER,
                timestamp TEXT
            )""")
        c.execute("""CREATE TABLE IF NOT EXISTS comments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                confession_id INTEGER,
                user_id INTEGER,
                text TEXT,
                timestamp TEXT
            )""")
        conn.commit()
        conn.close()

    def save_confession(self, user_id: int, category: str, text: str) -> Optional[int]:
        conn = self._get_conn()
        c = conn.cursor()
        timestamp = datetime.now().isoformat()
        try:
            c.execute("INSERT INTO confessions (user_id, category, text, timestamp) VALUES (?, ?, ?, ?)",
                      (user_id, category, text, timestamp))
            conn.commit()
            return c.lastrowid
        except Exception as e:
            logger.error(f"Error saving confession: {e}")
            return None
        finally:
            conn.close()

    def get_confession(self, confession_id: int) -> Optional[Tuple]:
        """Returns (id, user_id, category, text, approved, channel_message_id, timestamp)"""
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("SELECT * FROM confessions WHERE id=?", (confession_id,))
        row = c.fetchone()
        conn.close()
        return row

    def get_approved_confessions(self, category_key: str = 'recent') -> List[Tuple]:
        """Returns list of (id, text, category, timestamp) for browsing."""
        conn = self._get_conn()
        c = conn.cursor()
        
        if category_key == 'recent':
            c.execute("SELECT id, text, category, timestamp FROM confessions WHERE approved=1 ORDER BY timestamp DESC")
        else:
            category_name = CATEGORY_MAP.get(category_key)
            if category_name:
                 c.execute("SELECT id, text, category, timestamp FROM confessions WHERE approved=1 AND category=? ORDER BY timestamp DESC", (category_name,))
            else:
                return [] # Invalid category key

        rows = c.fetchall()
        conn.close()
        return rows


    def update_confession_status(self, confession_id: int, status: int, channel_message_id: Optional[int] = None):
        conn = self._get_conn()
        c = conn.cursor()
        if channel_message_id is not None:
             c.execute("UPDATE confessions SET approved=?, channel_message_id=? WHERE id=?",
                       (status, channel_message_id, confession_id))
        else:
            c.execute("UPDATE confessions SET approved=? WHERE id=?",
                       (status, confession_id))
        conn.commit()
        conn.close()

    def save_comment(self, confession_id: int, user_id: int, text: str):
        conn = self._get_conn()
        c = conn.cursor()
        timestamp = datetime.now().isoformat()
        c.execute("INSERT INTO comments (confession_id, user_id, text, timestamp) VALUES (?, ?, ?, ?)",
                  (confession_id, user_id, text, timestamp))
        conn.commit()
        conn.close()

    def get_comments(self, confession_id: int) -> List[Tuple]:
        """Returns list of (timestamp, text, user_id) for a confession."""
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("SELECT timestamp, text, user_id FROM comments WHERE confession_id=? ORDER BY timestamp ASC", (confession_id,))
        rows = c.fetchall()
        conn.close()
        return rows

    def get_comment_count(self, confession_id: int) -> int:
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM comments WHERE confession_id=?", (confession_id,))
        count = c.fetchone()[0]
        conn.close()
        return count

# Initialize Database Manager
db = DatabaseManager()

# --- Helper Formatting Functions ---

def format_confession_for_post(confession_id: int, category: str, text: str, comment_count: int) -> str:
    """Formats the text for the channel post."""
    return (
        f"🤫 **Confession #{confession_id}**\n"
        f"Category: #{category.replace(' ', '_').replace(':', '')}\n\n"
        f"_{text}_\n\n"
        f"💬 Comments: {comment_count}"
    )

def format_browsing_confession(confession_id: int, text: str, category: str, timestamp: str, index: int, total: int) -> str:
    """Formats the text for private browsing (includes navigation info)."""
    
    try:
        dt = datetime.fromisoformat(timestamp.split('.')[0])
        date_str = dt.strftime("%Y-%m-%d %H:%M")
    except ValueError:
        date_str = "Unknown time"
        
    comment_count = db.get_comment_count(confession_id)
    
    return (
        f"📝 **Confession #{confession_id}** ({index + 1}/{total})\n"
        f"Category: *{category}* - Shared {date_str}\n\n"
        f"{text}\n\n"
        f"💬 Comments: {comment_count}"
    )

def format_comments_display(confession_id: int, comments: List[Tuple]) -> str:
    """Formats the list of comments for display in private chat."""
    header = f"💬 **Comments for Confession #{confession_id}** ({len(comments)} total)\n\n"
    
    if not comments:
        return header + "No comments yet! Be the first to add one."

    comment_blocks = []
    for i, (timestamp, text, _) in enumerate(comments):
        try:
            dt = datetime.fromisoformat(timestamp.split('.')[0])
            time_str = dt.strftime('%H:%M %b %d')
        except ValueError:
            time_str = "just now"
            
        comment_block = (
            f"👤 *Anon User {i + 1}* ({time_str}):\n"
            f"» {text}"
        )
        comment_blocks.append(comment_block)
        
    return header + "\n---\n".join(comment_blocks)

# --- Handler Functions: Core Bot Logic ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /start command, including deep links for browsing."""
    
    if context.args and context.args[0].startswith('viewconf_'):
        # Handle deep link from channel post
        return await handle_deep_link(update, context)
        
    welcome_text = (
        "🤫 **Confession Bot**\n\n"
        "Welcome! Use the menu to submit a confession, browse posts, or view the channel."
    )
    
    # Using ReplyKeyboardMarkup for the main menu (defined in keyboards.py)
    await update.message.reply_text(
        welcome_text,
        reply_markup=get_main_keyboard(CHANNEL_LINK),
        parse_mode=constants.ParseMode.MARKDOWN
    )
    return ConversationHandler.END


async def handle_deep_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles deep links like /start viewconf_123."""
    payload = context.args[0]
    try:
        confession_id = int(payload.split('_')[1])
    except (IndexError, ValueError):
        await update.message.reply_text("❌ Invalid confession link.", reply_markup=get_main_keyboard(CHANNEL_LINK))
        return ConversationHandler.END

    confession_full = db.get_confession(confession_id)
    
    if not confession_full or confession_full[4] != 1: # Index 4 is 'approved' status (1=approved)
        await update.message.reply_text("❌ Sorry, that confession is not approved or does not exist.", reply_markup=get_main_keyboard(CHANNEL_LINK))
        return ConversationHandler.END

    # Data is (id, text, category, timestamp)
    confession_data = (confession_full[0], confession_full[3], confession_full[2], confession_full[6])
    
    # Temporarily store this single confession as the list for browsing
    context.user_data['confessions_list'] = [confession_data]
    context.user_data['current_index'] = 0
    
    # Send a new message with the formatted confession and navigation
    await update.message.reply_text(
        "You were redirected from the channel post:",
        parse_mode=constants.ParseMode.MARKDOWN
    )
    
    await display_confession(update, context, via_callback=False)
    
    return BROWSING_CONFESSIONS # Enter browsing state

async def handle_text_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles text button clicks from the ReplyKeyboardMarkup."""
    text = update.message.text
    
    if text == "💌 Submit Confession":
        return await start_confession(update, context)
    elif text == "📖 Browse":
        return await browse_menu(update, context)
    elif text == "💬 Comments":
        await update.message.reply_text("ℹ️ To read or add comments, please use the **📖 Browse** button, find a confession, and then use the *View/Add Comment* inline buttons.", parse_mode=constants.ParseMode.MARKDOWN)
        return ConversationHandler.END
    elif text == "❓ Help":
        await update.message.reply_text("❓ **Bot Help**\n\nUse **Submit Confession** to write a post. Use **Browse** to view and interact with approved posts.", parse_mode=constants.ParseMode.MARKDOWN)
        return ConversationHandler.END
    elif text == "⚙️ Settings":
        await update.message.reply_text("⚙️ **Settings Menu**", reply_markup=get_settings_keyboard(), parse_mode=constants.ParseMode.MARKDOWN)
        return ConversationHandler.END
    
    return ConversationHandler.END

# --- Submission Logic ---

async def start_confession(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the confession process by prompting for category selection."""
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        await query.edit_message_text(
            "📂 **Select a category for your confession:**",
            reply_markup=get_category_keyboard(),
            parse_mode=constants.ParseMode.MARKDOWN
        )
    else: # Started via ReplyKeyboardMarkup text button
        await update.message.reply_text(
            "📂 **Select a category for your confession:**",
            reply_markup=get_category_keyboard(),
            parse_mode=constants.ParseMode.MARKDOWN
        )
    
    context.user_data.clear()
    return SELECTING_CATEGORY

async def select_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle category selection and move to writing state."""
    query = update.callback_query
    await query.answer()
    
    key = query.data.replace("cat_", "")
    category = CATEGORY_MAP.get(key, 'Other')
    context.user_data['category'] = category
    
    await query.edit_message_text(
        f"✅ **Category:** {category}\n\n"
        "📝 **Now write your confession:**\n\n"
        "Type your confession (10-1000 characters):",
        parse_mode=constants.ParseMode.MARKDOWN
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
            "❌ **Please ensure your confession is between 10 and 1000 characters.**\n\n"
            "Try again:",
            parse_mode=constants.ParseMode.MARKDOWN
        )
        return WRITING_CONFESSION
    
    confession_id = db.save_confession(user_id, category, confession_text)
    if not confession_id:
        await update.message.reply_text("❌ **Error submitting confession.** Please try again later.", parse_mode=constants.ParseMode.MARKDOWN)
        return ConversationHandler.END

    # Notify Admin
    for admin_id in ADMIN_IDS:
        admin_message = (
            f"🆕 **Confession #{confession_id} PENDING**\n\n"
            f"👤 User: {username} (ID: `{user_id}`)\n"
            f"📂 Category: {category}\n"
            f"📝 Text:\n_{confession_text}_"
        )
        
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=admin_message,
                reply_markup=get_admin_keyboard(confession_id),
                parse_mode=constants.ParseMode.MARKDOWN,
                disable_web_page_preview=True
            )
        except Exception as e:
            logger.error(f"Failed to send admin message to {admin_id}: {e}")
    
    await update.message.reply_text("✅ **Confession Submitted!** You'll be notified of the outcome.", parse_mode=constants.ParseMode.MARKDOWN)
    
    context.user_data.clear()
    return ConversationHandler.END

async def handle_admin_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle admin approval/rejection/pending via callback."""
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id not in ADMIN_IDS: 
        await query.answer("❌ Only admins can perform this action.", show_alert=True)
        return
    
    action, confession_id_str = query.data.split('_', 1) 
    confession_id = int(confession_id_str)
    
    confession = db.get_confession(confession_id)
    if not confession:
        await query.edit_message_text(f"❌ Confession #{confession_id} not found.")
        return
    
    # 0:id, 1:user_id, 2:category, 3:text, 4:approved, 5:channel_message_id, 6:timestamp
    user_id, category, confession_text = confession[1], confession[2], confession[3]
    
    status_code, status_text, status_emoji, user_message = 0, "", "", ""
    
    if action == 'approve':
        try:
            comment_count = db.get_comment_count(confession_id)
            channel_text = format_confession_for_post(confession_id, category, confession_text, comment_count)
            
            channel_message = await context.bot.send_message(
                chat_id=CHANNEL_ID,
                text=channel_text,
                reply_markup=get_channel_post_keyboard(confession_id, BOT_USERNAME), 
                parse_mode=constants.ParseMode.MARKDOWN
            )
            
            db.update_confession_status(confession_id, 1, channel_message.message_id)
            status_code, status_text, status_emoji = 1, "APPROVED", "✅"
            user_message = "🎉 **Your confession has been APPROVED and is live!**"
            
        except Exception as e:
            logger.error(f"Failed to post to channel: {e}")
            await query.answer("❌ Failed to post to channel. Check bot permissions and CHANNEL_ID.", show_alert=True)
            return
            
    elif action == 'reject':
        db.update_confession_status(confession_id, 2)
        status_code, status_text, status_emoji = 2, "REJECTED", "❌"
        user_message = "❌ **Your confession was NOT APPROVED.**"

    elif action == 'pending':
        db.update_confession_status(confession_id, 0)
        status_code, status_text, status_emoji = 0, "SET BACK TO PENDING", "⏸️"
        
        return await query.edit_message_text(
            f"{status_emoji} **Confession #{confession_id} {status_text}**.",
            parse_mode=constants.ParseMode.MARKDOWN
        )

    # Notify user (if approved/rejected)
    try:
        if user_message:
            await context.bot.send_message(chat_id=user_id, text=user_message, parse_mode=constants.ParseMode.MARKDOWN)
    except Exception as e:
        logger.warning(f"Could not notify user {user_id}: {e}")
    
    # Update admin message
    await query.edit_message_text(
        f"{status_emoji} **Confession #{confession_id} {status_text}**.\n\n"
        f"Action performed by {query.from_user.first_name}.",
        parse_mode=constants.ParseMode.MARKDOWN
    )

# --- Browsing Logic ---

async def browse_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Shows the browsing category menu."""
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        # The 'back_browse' handler will hit this
        try:
            await query.edit_message_text(
                "📚 **Browse Confessions by Category:** \n\nSelect a category:",
                reply_markup=get_browse_keyboard(show_back=True),
                parse_mode=constants.ParseMode.MARKDOWN
            )
        except Exception as e:
            logger.warning(f"Browse menu edit failed (often ok): {e}")
    else: # Started via ReplyKeyboardMarkup text button
        await update.message.reply_text(
            "📚 **Browse Confessions by Category:** \n\nSelect a category:",
            reply_markup=get_browse_keyboard(show_back=True),
            parse_mode=constants.ParseMode.MARKDOWN
        )
        
    # Clear index/list from previous session
    context.user_data.pop('confessions_list', None)
    context.user_data.pop('current_index', None)
    
    return BROWSING_CONFESSIONS

async def start_browse_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Fetches confessions for the selected category."""
    query = update.callback_query
    await query.answer()
    
    browse_key = query.data.replace("browse_", "") 
    category_name = CATEGORY_MAP.get(browse_key, 'Latest')
    
    confessions = db.get_approved_confessions(category_key=browse_key)
    context.user_data['confessions_list'] = confessions
    context.user_data['current_index'] = 0 
    
    if not confessions:
        await query.edit_message_text(
            f"❌ No approved confessions found for **{category_name}**.",
            parse_mode=constants.ParseMode.MARKDOWN,
            reply_markup=get_browse_keyboard(show_back=True) 
        )
        return BROWSING_CONFESSIONS
        
    await display_confession(update, context, via_callback=True)
    return BROWSING_CONFESSIONS

async def display_confession(update: Update, context: ContextTypes.DEFAULT_TYPE, via_callback: bool):
    """Generic function to display the current confession based on index."""
    confessions = context.user_data.get('confessions_list', [])
    current_index = context.user_data.get('current_index', 0)
    
    if not confessions: return 
    
    # Data is (id, text, category, timestamp)
    c_id, text, category, timestamp = confessions[current_index]
    
    formatted_text = format_browsing_confession(c_id, text, category, timestamp, current_index, len(confessions))
    
    keyboard = get_confession_navigation(
        confession_number=c_id,
        total_confessions=len(confessions),
        current_index=current_index + 1
    )
    
    if via_callback:
        try:
            await update.callback_query.edit_message_text(
                text=formatted_text,
                reply_markup=keyboard,
                parse_mode=constants.ParseMode.MARKDOWN
            )
        except Exception as e:
             logger.warning(f"Error editing message during navigation: {e}")
    else:
        # Send a new message (used for deep links)
        await update.message.reply_text(
            text=formatted_text,
            reply_markup=keyboard,
            parse_mode=constants.ParseMode.MARKDOWN
        )


async def navigate_confession(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles 'next' and 'previous' buttons in the navigation."""
    query = update.callback_query
    await query.answer()
    
    action = query.data.split('_')[0] # 'prev' or 'next'
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

async def back_to_confession(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Returns the user to the confession view after viewing comments."""
    query = update.callback_query
    await query.answer()
    
    # The callback is 'back_conf_CONFESSION_ID'
    confession_id = int(query.data.split('_')[2])
    
    # Ensure the correct confession is loaded/selected in user_data before displaying
    if 'confessions_list' not in context.user_data:
        # Fallback to fetching the single confession if list is missing
        confession_full = db.get_confession(confession_id)
        if not confession_full:
            await query.edit_message_text("Confession not found.")
            return BROWSING_CONFESSIONS
        
        # Data structure (id, text, category, timestamp)
        confession_data = (confession_full[0], confession_full[3], confession_full[2], confession_full[6])
        context.user_data['confessions_list'] = [confession_data]
        context.user_data['current_index'] = 0
    else:
        # Find the index of the confession_id in the current list
        try:
            index = next(i for i, data in enumerate(context.user_data['confessions_list']) if data[0] == confession_id)
            context.user_data['current_index'] = index
        except StopIteration:
            # If not found, display the first one
            context.user_data['current_index'] = 0

    await display_confession(update, context, via_callback=True)
    return BROWSING_CONFESSIONS # Stay in browsing state


# --- Comment Logic ---

async def view_comments(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Fetches and displays comments for the current confession."""
    query = update.callback_query
    await query.answer()
    
    # Callback is 'view_comments_CONFESSION_ID'
    confession_id = int(query.data.split('_')[2])
    
    comments = db.get_comments(confession_id)
    formatted_comments = format_comments_display(confession_id, comments)
    
    await query.edit_message_text(
        formatted_comments,
        reply_markup=get_comments_management(confession_id, can_comment=True),
        parse_mode=constants.ParseMode.MARKDOWN
    )
    
    return BROWSING_CONFESSIONS 


async def start_add_comment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Prompts the user to write a comment."""
    query = update.callback_query
    await query.answer()
    
    # Callback is 'add_comment_CONFESSION_ID'
    confession_id = int(query.data.split('_')[2])
    context.user_data['comment_confession_id'] = confession_id
    
    # The message is sent as a new message, not an edit, as we are starting a conversation
    await query.message.reply_text(
        f"📝 **Write your anonymous comment for Confession #{confession_id}:**\n\n"
        "Type /cancel to stop.",
        parse_mode=constants.ParseMode.MARKDOWN
    )
    
    return WRITING_COMMENT

async def receive_comment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Saves the comment to the DB and updates the channel post count."""
    user_id = update.effective_user.id
    comment_text = update.message.text.strip()
    confession_id = context.user_data.pop('comment_confession_id', None)
    
    if not confession_id:
        await update.message.reply_text("❌ Error: Comment session expired. Please try again.")
        return ConversationHandler.END
        
    if not (1 <= len(comment_text) <= 500):
        await update.message.reply_text(
            "❌ **Comment must be between 1 and 500 characters.**\n\n"
            "Try again (or /cancel):",
            parse_mode=constants.ParseMode.MARKDOWN
        )
        # Re-save the ID if the user needs to retry
        context.user_data['comment_confession_id'] = confession_id 
        return WRITING_COMMENT
        
    db.save_comment(confession_id, user_id, comment_text)
    
    # 2. UPDATE CHANNEL POST COUNT
    confession = db.get_confession(confession_id)
    if confession and confession[5]: # Index 5 is channel_message_id
        channel_message_id = confession[5]
        category = confession[2]
        confession_text = confession[3]
        
        try:
            comment_count = db.get_comment_count(confession_id)
            updated_text = format_confession_for_post(confession_id, category, confession_text, comment_count)
            
            # Update the channel post text (which includes the comment count)
            await context.bot.edit_message_text(
                chat_id=CHANNEL_ID,
                message_id=channel_message_id,
                text=updated_text,
                reply_markup=get_channel_post_keyboard(confession_id, BOT_USERNAME),
                parse_mode=constants.ParseMode.MARKDOWN
            )
        except Exception as e:
            logger.error(f"Failed to update channel post {channel_message_id} count: {e}")
            
    await update.message.reply_text("✅ **Comment submitted anonymously!**", reply_markup=get_main_keyboard(CHANNEL_LINK), parse_mode=constants.ParseMode.MARKDOWN)
    
    return ConversationHandler.END

# --- Fallbacks and Main Menu ---

async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Return to main menu from an inline callback."""
    query = update.callback_query
    await query.answer()
    
    welcome_text = "🤫 **Confession Bot**\n\nWelcome back! Use the keyboard below."
    
    try:
        await query.edit_message_text(
            welcome_text, 
            parse_mode=constants.ParseMode.MARKDOWN,
        )
    except Exception as e:
        logger.warning(f"main_menu edit failed (often OK if message is identical): {e}")
        
    return ConversationHandler.END # End any pending conversation

async def cancel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /cancel command."""
    context.user_data.clear()
    await update.message.reply_text("Operation cancelled.", reply_markup=get_main_keyboard(CHANNEL_LINK))
    return ConversationHandler.END

# --- Main Application Setup ---

def main():
    """Starts the bot."""
    if not all([BOT_TOKEN, CHANNEL_ID, BOT_USERNAME, ADMIN_IDS]):
        logger.error("FATAL ERROR: Configuration environment variables (BOT_TOKEN, CHANNEL_ID, BOT_USERNAME, ADMIN_IDS) are required.")
        return
        
    app = Application.builder().token(BOT_TOKEN).build()
    
    # 1. Submission Conversation Handler (Category -> Write)
    confession_conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^💌 Submit Confession$"), start_confession)],
        
        states={
            SELECTING_CATEGORY: [
                CallbackQueryHandler(select_category, pattern="^cat_"),
                CallbackQueryHandler(cancel_handler, pattern="^cancel$")
            ],
            WRITING_CONFESSION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_confession)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_handler)]
    )

    # 2. Comment Conversation Handler (Starts when user hits 'Add Comment' from a browsing/view message)
    comment_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_add_comment, pattern="^add_comment_")],
        states={
            WRITING_COMMENT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_comment),
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel_handler)]
    )
    
    # 3. Browsing Conversation Handler (Handles all browsing actions)
    browsing_conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^📖 Browse$"), browse_menu)], 
        states={
            BROWSING_CONFESSIONS: [
                CallbackQueryHandler(start_browse_category, pattern="^browse_"),
                CallbackQueryHandler(navigate_confession, pattern="^next_|^prev_"),
                CallbackQueryHandler(view_comments, pattern="^view_comments_"),
                CallbackQueryHandler(back_to_confession, pattern="^back_conf_"), # New callback
                CallbackQueryHandler(browse_menu, pattern="^back_browse$"), # Returns to category selection
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel_handler)]
    )

    # --- Handlers ---
    app.add_handler(CommandHandler("start", start))
    app.add_handler(confession_conv_handler)
    app.add_handler(comment_conv_handler)
    app.add_handler(browsing_conv_handler)

    # General/Admin Callbacks
    app.add_handler(CallbackQueryHandler(handle_admin_action, pattern="^approve_|^reject_|^pending_"))
    app.add_handler(CallbackQueryHandler(main_menu, pattern="^back_main$"))
    app.add_handler(CallbackQueryHandler(main_menu, pattern="^cancel$")) # Catch the cancel from keyboards.py
    
    # Message Handler for the remaining main menu text buttons (Help, Settings, Comments)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_button))
    
    logger.info("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
