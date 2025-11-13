# File: confession_bot.py

import logging
import sqlite3
from datetime import datetime
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
import os
from dotenv import load_dotenv
from typing import List, Tuple, Optional

load_dotenv()

# --- Configuration & Setup ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
# Note: CHANNEL_ID can be str or int (must be int if it's a channel ID like -100...)
try:
    CHANNEL_ID = int(os.getenv("CHANNEL_ID")) 
except (TypeError, ValueError):
    CHANNEL_ID = os.getenv("CHANNEL_ID") 

ADMIN_IDS_RAW = os.getenv("ADMIN_IDS")
ADMIN_IDS: List[int] = [int(x.strip()) for x in ADMIN_IDS_RAW.split(",")] if ADMIN_IDS_RAW else []

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- States ---
SUBMITTING, COMMENTING = range(2)

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
        # Ensure user_id column is present in the confessions table
        c.execute("""CREATE TABLE IF NOT EXISTS confessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                text TEXT,
                approved INTEGER DEFAULT 0, -- 0: Pending, 1: Approved, 2: Rejected
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

    def save_confession(self, user_id: int, text: str) -> Optional[int]:
        conn = self._get_conn()
        c = conn.cursor()
        timestamp = datetime.now().isoformat()
        try:
            c.execute("INSERT INTO confessions (user_id, text, timestamp) VALUES (?, ?, ?)",
                      (user_id, text, timestamp))
            conn.commit()
            return c.lastrowid
        except Exception as e:
            logger.error(f"Error saving confession: {e}")
            return None
        finally:
            conn.close()

    def get_confession(self, confession_id: int) -> Optional[Tuple]:
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("SELECT user_id, text, approved, channel_message_id FROM confessions WHERE id=?", (confession_id,))
        row = c.fetchone()
        conn.close()
        return row

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
        conn = self._get_conn()
        c = conn.cursor()
        # Fetch timestamp, text (ordered by time)
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

# --- Helper Functions ---
def format_comments_display(comments: List[Tuple]) -> str:
    if not comments:
        return "No comments yet! Be the first to add one."

    messages = []
    for i, (timestamp, text, _) in enumerate(comments):
        # Format the timestamp for readability
        try:
            dt = datetime.fromisoformat(timestamp)
            time_str = dt.strftime('%Y-%m-%d %H:%M')
        except ValueError:
            time_str = "Unknown time"
            
        # Display as an anonymous comment
        comment_block = f"**👤 Anonymous User {i + 1}** ({time_str}):\n" \
                        f"» {text}"
        messages.append(comment_block)
        
    return "💬 **Confession Comments** 💬\n\n" + "\n---\n".join(messages)


# --- Start Command ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Welcome! Send /confess to submit a confession."
    )

# --- Submit Confession ---
async def confess(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Please type your confession:")
    return SUBMITTING

async def save_confession(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    username = update.message.from_user.first_name or "Anonymous"
    text = update.message.text
    
    # Simple character limit check (Optional, but good practice)
    if not (10 <= len(text) <= 1000):
        await update.message.reply_text("❌ Your confession must be between 10 and 1000 characters. Please try again.")
        return SUBMITTING

    confession_id = db.save_confession(user_id, text)
    
    if not confession_id:
        await update.message.reply_text("❌ An internal error occurred during submission. Please try again.")
        return ConversationHandler.END
        
    # Notify Admin
    admin_message = (
        f"📝 **NEW PENDING CONFESSION #{confession_id}**\n\n"
        f"👤 User: {username} (ID: `{user_id}`)\n"
        f"Text:\n_{text}_"
    )
    
    for admin_id in ADMIN_IDS:
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Approve", callback_data=f"approve_{confession_id}"),
                InlineKeyboardButton("❌ Reject", callback_data=f"reject_{confession_id}")
            ]
        ])
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=admin_message,
                reply_markup=keyboard,
                parse_mode=constants.ParseMode.MARKDOWN
            )
        except Exception as e:
            logger.error(f"Failed to send admin message to {admin_id}: {e}")
    
    await update.message.reply_text("Your confession has been submitted for approval. You will be notified of the outcome.")
    return ConversationHandler.END

# --- Admin Approval/Rejection ---
async def handle_admin_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    # Admin check
    if query.from_user.id not in ADMIN_IDS:
        await query.answer("❌ You are not authorized to perform this action.", show_alert=True)
        return

    data = query.data
    action, confession_id_str = data.split("_")
    confession_id = int(confession_id_str)
    
    confession_data = db.get_confession(confession_id)
    if not confession_data:
        await query.edit_message_text("Confession not found!")
        return
        
    user_id, text, _, _ = confession_data
    
    status_msg = ""
    user_notification = ""
    
    if action == 'approve':
        # Post to channel
        try:
            comment_count = db.get_comment_count(confession_id)
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(f"View Comments ({comment_count})", callback_data=f"viewcomments_{confession_id}"),
                    InlineKeyboardButton("Add Comment", callback_data=f"addcomment_{confession_id}")
                ]
            ])
            
            # Format post text
            post_text = f"🤫 **Anonymous Confession #{confession_id}**\n\n" \
                        f"_{text}_"
            
            channel_msg = await context.bot.send_message(
                chat_id=CHANNEL_ID,
                text=post_text,
                reply_markup=keyboard,
                parse_mode=constants.ParseMode.MARKDOWN
            )
            
            # Update DB status to 1 (Approved) and store message ID
            db.update_confession_status(confession_id, 1, channel_msg.message_id)
            status_msg = f"✅ Confession #{confession_id} approved and posted to channel."
            user_notification = "🎉 **Your confession was APPROVED and posted!**"
            
        except Exception as e:
            logger.error(f"Failed to post to channel {CHANNEL_ID}: {e}")
            await query.answer("❌ Error posting to channel. Check bot permissions.", show_alert=True)
            return

    elif action == 'reject':
        # Update DB status to 2 (Rejected)
        db.update_confession_status(confession_id, 2)
        status_msg = f"❌ Confession #{confession_id} rejected."
        user_notification = "😔 **Your confession was REJECTED.** You can submit another one."

    # Update admin message
    await query.edit_message_text(status_msg, parse_mode=constants.ParseMode.MARKDOWN)

    # Notify user
    try:
        await context.bot.send_message(chat_id=user_id, text=user_notification, parse_mode=constants.ParseMode.MARKDOWN)
    except Exception as e:
        logger.warning(f"Could not notify user {user_id}: {e}")


# --- View Comments ---
async def view_comments(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Fetching comments...")

    data = query.data
    confession_id = int(data.split("_")[1])
    
    # Get original message data to restore the keyboard later
    confession_data = db.get_confession(confession_id)
    if not confession_data:
        await query.edit_message_text("Confession not found.")
        return
        
    # Fetch comments
    comments = db.get_comments(confession_id)
    formatted_comments = format_comments_display(comments)
    
    # Keyboard to return to the post or add another comment
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔙 Back to Post", callback_data=f"restorepost_{confession_id}"),
            InlineKeyboardButton("📝 Add Comment", callback_data=f"addcomment_{confession_id}")
        ]
    ])
    
    await query.edit_message_text(
        formatted_comments,
        reply_markup=keyboard,
        parse_mode=constants.ParseMode.MARKDOWN
    )

# --- Restore Post (After viewing comments) ---
async def restore_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    confession_id = int(query.data.split("_")[1])
    
    # Re-fetch the confession and current comment count
    confession_data = db.get_confession(confession_id)
    if not confession_data:
        await query.edit_message_text("Confession not found.")
        return
    
    _, text, _, _ = confession_data
    comment_count = db.get_comment_count(confession_id)
    
    # Recreate the original post look
    post_text = f"🤫 **Anonymous Confession #{confession_id}**\n\n" \
                f"_{text}_"
                
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(f"View Comments ({comment_count})", callback_data=f"viewcomments_{confession_id}"),
            InlineKeyboardButton("Add Comment", callback_data=f"addcomment_{confession_id}")
        ]
    ])
    
    try:
        await query.edit_message_text(
            post_text,
            reply_markup=keyboard,
            parse_mode=constants.ParseMode.MARKDOWN
        )
    except Exception as e:
        logger.warning(f"Error restoring post: {e}")
        await query.answer("Could not restore post view. Try navigating back or using /start.", show_alert=True)


# --- Add Comment ---
async def add_comment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    confession_id = int(query.data.split("_")[1])
    context.user_data["comment_confession_id"] = confession_id
    
    await query.message.reply_text("Please type your comment:")
    return COMMENTING

async def save_comment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text
    confession_id = context.user_data.pop("comment_confession_id", None)
    
    if confession_id is None:
        await update.message.reply_text("❌ Error: Comment session expired. Please start commenting again from the channel post.")
        return ConversationHandler.END
        
    db.save_comment(confession_id, user_id, text)
    
    # Get current comment count and message ID
    comment_count = db.get_comment_count(confession_id)
    confession_data = db.get_confession(confession_id)
    
    if confession_data and confession_data[3]: # Index 3 is channel_message_id
        channel_message_id = confession_data[3]
        
        # Update button count on channel
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(f"View Comments ({comment_count})", callback_data=f"viewcomments_{confession_id}"),
                InlineKeyboardButton("Add Comment", callback_data=f"addcomment_{confession_id}")
            ]
        ])
        
        try:
            await context.bot.edit_message_reply_markup(
                chat_id=CHANNEL_ID,
                message_id=channel_message_id,
                reply_markup=keyboard
            )
        except Exception as e:
            logger.error(f"Failed to update channel message reply markup: {e}")
    
    await update.message.reply_text("Your comment has been added ✅")
    return ConversationHandler.END

# --- Cancel ---
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("Operation canceled.")
    return ConversationHandler.END

# --- Main ---
def main():
    if not BOT_TOKEN or not CHANNEL_ID or not ADMIN_IDS:
        logger.error("Configuration error: BOT_TOKEN, CHANNEL_ID, or ADMIN_IDS missing or invalid.")
        return
        
    app = Application.builder().token(BOT_TOKEN).build()
    
    # 1. Confess/Comment Conversation Handler
    confess_conv = ConversationHandler(
        entry_points=[CommandHandler("confess", confess)],
        states={
            SUBMITTING: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_confession)],
            COMMENTING: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_comment)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    
    # 2. Add Comment Entry (from inline button in channel post)
    comment_entry_handler = CallbackQueryHandler(add_comment, pattern="^addcomment_")

    app.add_handler(CommandHandler("start", start))
    app.add_handler(confess_conv)
    
    # Admin Action Handler (Approve/Reject)
    app.add_handler(CallbackQueryHandler(handle_admin_action, pattern="^approve_|^reject_"))
    
    # User Interaction Handlers
    app.add_handler(CallbackQueryHandler(view_comments, pattern="^viewcomments_"))
    app.add_handler(CallbackQueryHandler(restore_post, pattern="^restorepost_"))
    app.add_handler(comment_entry_handler) # This handler must be added before the main conversation handler's fallbacks start

    logger.info("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
