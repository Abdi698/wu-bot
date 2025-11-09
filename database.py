from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, ConversationHandler
import logging
import sqlite3
from datetime import datetime
import os

# Enhanced logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Your credentials
BOT_TOKEN = "8319779341:AAGFmurF3DECS8HBZ53Kj8qVJSxyHPZS-2c"
ADMIN_CHAT_ID = "7411390360"
CHANNEL_ID = "-1002516867446"  # Your channel ID

# Conversation states
SELECTING_CATEGORY, WRITING_CONFESSION = range(2)

# NEW STATES for Commenting Flow
COMMENT_MENU_STATE = 20 # State where the user sees comments and the menu buttons
WRITING_COMMENT = 21    # State where the user is typing their reply

CATEGORIES = [
    "Academic Stress", "Friendship", "Love & Relationships", 
    "Regrets", "Achievements", "Fear & Anxiety", "Other"
]

# Helper function to extract the numerical part of the channel ID for links
def get_clean_channel_id(channel_id: str) -> str:
    """Removes the '-100' prefix used by Telegram API for supergroups/channels 
    to create a public t.me/c/ link."""
    if channel_id.startswith('-100'):
        return channel_id[4:]
    return channel_id.lstrip('-')


class DatabaseManager:
    def __init__(self):
        self.init_database()
    
    def init_database(self):
        """Initialize database, creating confessions and comments tables."""
        try:
            conn = sqlite3.connect('confessions.db', check_same_thread=False)
            cursor = conn.cursor()
            
            # 1. Confessions Table (Existing)
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
            
            # 2. Comments Table (NEW)
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
            conn.close()
            logger.info("✅ Database initialized successfully with 'confessions' and 'comments' tables.")
        except Exception as e:
            logger.error(f"❌ Database initialization error: {e}")

    def save_confession(self, user_id, username, category, confession_text):
        """Save confession to database."""
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
            
            logger.info(f"✅ Confession #{confession_id} saved successfully")
            return confession_id
            
        except Exception as e:
            logger.error(f"❌ Error saving confession: {e}")
            return None
        finally:
            if conn:
                conn.close()

    def update_confession_status(self, confession_id, status, channel_message_id=None):
        """Update confession status and channel message ID."""
        conn = None
        try:
            conn = sqlite3.connect('confessions.db', check_same_thread=False)
            cursor = conn.cursor()
            
            if channel_message_id:
                cursor.execute('''
                    UPDATE confessions 
                    SET status = ?, channel_message_id = ? 
                    WHERE id = ?
                ''', (status, channel_message_id, confession_id))
            else:
                cursor.execute('''
                    UPDATE confessions 
                    SET status = ? 
                    WHERE id = ?
                ''', (status, confession_id))
            
            conn.commit()
            logger.info(f"✅ Confession #{confession_id} status updated to {status}")
            
        except Exception as e:
            logger.error(f"❌ Error updating confession: {e}")
        finally:
            if conn:
                conn.close()

    def get_confession(self, confession_id):
        """Get confession by ID"""
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
    
    # --- NEW COMMENT METHODS ---

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
            
            comment_id = cursor.lastrowid
            conn.commit()
            logger.info(f"✅ Comment #{comment_id} saved for Confession #{confession_id}")
            return comment_id
            
        except Exception as e:
            logger.error(f"❌ Error saving comment: {e}")
            return None
        finally:
            if conn:
                conn.close()
    
    def get_comments(self, confession_id):
        """Get all comments for a specific confession ID."""
        conn = None
        try:
            conn = sqlite3.connect('confessions.db', check_same_thread=False)
            cursor = conn.cursor()
            # Fetch all comment columns
            cursor.execute('''
                SELECT username, comment_text, timestamp 
                FROM comments 
                WHERE confession_id = ? 
                ORDER BY timestamp ASC
            ''', (confession_id,))
            results = cursor.fetchall()
            return results
        except Exception as e:
            logger.error(f"❌ Error getting comments: {e}")
            return []
        finally:
            if conn:
                conn.close()

    # --- END NEW COMMENT METHODS ---

    def get_pending_confessions(self):
        """Get all pending confessions"""
        conn = None
        try:
            conn = sqlite3.connect('confessions.db', check_same_thread=False)
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM confessions WHERE status = "pending" ORDER BY id DESC')
            results = cursor.fetchall()
            return results
        except Exception as e:
            logger.error(f"❌ Error getting pending confessions: {e}")
            return []
        finally:
            if conn:
                conn.close()

# Initialize database
db = DatabaseManager()

# --- CONFESSION FLOW HANDLERS (Mostly Unchanged) ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send welcome message when command /start is issued."""
    user = update.effective_user
    logger.info(f"Start command received from user {user.id} - {user.first_name}")
    
    welcome_text = (
        "🤫 *WU Confession Bot*\n\n"
        "Welcome to the anonymous confession platform!\n\n"
        "• Your identity will *never* be revealed\n"
        "• All confessions are reviewed by admins\n"
        "• Be respectful and honest\n\n"
        "Click the button below to start your confession:"
    )
    
    keyboard = [
        [InlineKeyboardButton("📝 Start Confession", callback_data="start_confess")],
        [InlineKeyboardButton("ℹ️ How It Works", callback_data="how_it_works")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode='Markdown')

async def how_it_works(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show how the bot works."""
    query = update.callback_query
    await query.answer()
    
    explanation = (
        "🔒 *How It Works:*\n\n"
        "1. Click *'Start Confession'* to begin\n"
        "2. Choose a category for your confession\n"
        "3. Write your confession text\n"
        "4. Submit for admin approval\n"
        "5. If approved, posted anonymously\n\n"
        "Your privacy is 100% guaranteed! 🛡️"
    )
    
    keyboard = [
        [InlineKeyboardButton("📝 Start Confession", callback_data="start_confess")],
        [InlineKeyboardButton("🔙 Back", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(explanation, reply_markup=reply_markup, parse_mode='Markdown')

async def start_confession(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the confession process."""
    query = update.callback_query
    await query.answer()
    
    logger.info(f"User {query.from_user.id} started confession process")
    
    # Create category buttons
    keyboard = []
    for i in range(0, len(CATEGORIES), 2):
        row = []
        row.append(InlineKeyboardButton(CATEGORIES[i], callback_data=f"category_{CATEGORIES[i]}"))
        if i + 1 < len(CATEGORIES):
            row.append(InlineKeyboardButton(CATEGORIES[i + 1], callback_data=f"category_{CATEGORIES[i + 1]}"))
        keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel_confession")]) # Changed to cancel_confession
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "📂 *Select a category for your confession:*",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    
    return SELECTING_CATEGORY

async def select_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle category selection."""
    query = update.callback_query
    await query.answer()
    
    category = query.data.replace("category_", "")
    context.user_data['category'] = category
    logger.info(f"User {query.from_user.id} selected category: {category}")
    
    await query.edit_message_text(
        f"✅ *Category:* {category}\n\n"
        "📝 *Now write your confession:*\n\n"
        "Type your confession below:",
        parse_mode='Markdown'
    )
    
    return WRITING_CONFESSION

async def receive_confession(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive and process the confession text."""
    user_id = update.effective_user.id
    username = update.effective_user.first_name or "Anonymous"
    confession_text = update.message.text.strip()
    category = context.user_data.get('category', 'General')
    
    if len(confession_text) > 1000:
        await update.message.reply_text(
            "❌ *Confession too long!* Please keep it under 1000 characters.\n\n"
            "Try again:",
            parse_mode='Markdown'
        )
        return WRITING_CONFESSION
    
    if len(confession_text) < 10:
        await update.message.reply_text(
            "❌ *Confession too short!* Please write at least 10 characters.\n\n"
            "Try again:",
            parse_mode='Markdown'
        )
        return WRITING_CONFESSION
    
    # Save to database
    confession_id = db.save_confession(user_id, username, category, confession_text)
    
    if confession_id:
        # Send to admin for approval
        admin_message = (
            f"🆕 *New Confession #*{confession_id}\n\n"
            f"👤 *User:* {username} (ID: {user_id})\n"
            f"📂 *Category:* {category}\n"
            f"📝 *Text:* {confession_text}\n"
            f"⏰ *Time:* {datetime.now().strftime('%H:%M')}\n\n"
            f"*Approve or reject this confession:*"
        )
        
        keyboard = [
            [
                InlineKeyboardButton("✅ APPROVE", callback_data=f"approve_{confession_id}"),
                InlineKeyboardButton("❌ REJECT", callback_data=f"reject_{confession_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        try:
            # Send message to ADMIN
            await context.bot.send_message(
                chat_id=ADMIN_CHAT_ID,
                text=admin_message,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            logger.info(f"✅ Confession #{confession_id} sent to ADMIN {ADMIN_CHAT_ID}")
            
            # Confirm to user
            await update.message.reply_text(
                "✅ *Confession Submitted!*\n\n"
                "Your confession has been sent for admin approval.\n"
                "You'll be notified when it's reviewed.\n"
                "Your identity is protected! 🔒\n\n"
                "Use /start to submit another confession.",
                parse_mode='Markdown'
            )
            
        except Exception as e:
            logger.error(f"❌ Failed to send to admin: {e}")
            await update.message.reply_text(
                "❌ *Error submitting confession.* Please try again later.",
                parse_mode='Markdown'
            )
    else:
        logger.error(f"❌ Failed to save confession for user {user_id}")
        await update.message.reply_text(
            "❌ *Error saving confession.* Please try again.",
            parse_mode='Markdown'
        )
    
    context.user_data.clear()
    return ConversationHandler.END

async def handle_admin_approval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle admin approval/rejection of confessions."""
    query = update.callback_query
    await query.answer()
    
    if str(query.from_user.id) != ADMIN_CHAT_ID:
        await query.answer("❌ Only admins can perform this action.", show_alert=True)
        return
    
    action, confession_id = query.data.split('_')
    confession_id = int(confession_id)
    
    confession = db.get_confession(confession_id)
    if not confession:
        await query.answer("❌ Confession not found", show_alert=True)
        return
    
    _, user_id, username, category, confession_text, timestamp, status, channel_message_id = confession
    
    user_message = ""
    
    if action == 'approve':
        try:
            # Format and post to channel
            channel_text = (
                f"🤫 *WU Confession #*{confession_id}\n\n"
                f"{confession_text}\n\n"
                f"*Category:* {category}\n"
                f"*Posted anonymously*"
            )
            
            # Add Comment Button to Channel Post
            channel_buttons = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "💬 View & Add Reply", 
                        url=f"https://t.me/{context.bot.username}?start=comment_{confession_id}"
                    )
                ]
            ])

            channel_message = await context.bot.send_message(
                chat_id=CHANNEL_ID,
                text=channel_text,
                reply_markup=channel_buttons, 
                parse_mode='Markdown'
            )
            
            db.update_confession_status(confession_id, 'approved', channel_message.message_id)
            
            # Notify user
            channel_numeric_id = get_clean_channel_id(CHANNEL_ID)
            message_link = f"https://t.me/c/{channel_numeric_id}/{channel_message.message_id}"
            
            user_message = (
                "🎉 *Your confession has been APPROVED and posted anonymously!*\n\n"
                f"You can now view it and leave replies:\n"
                f"[👉 View Confession Post]({message_link})"
            )
            status_text = "APPROVED"
            status_emoji = "✅"
            
        except Exception as e:
            logger.error(f"❌ Failed to post to channel: {e}")
            await query.answer("❌ Failed to post to channel", show_alert=True)
            return
            
    else:  # reject
        db.update_confession_status(confession_id, 'rejected')
        user_message = "❌ *Your confession was NOT APPROVED.* You can submit another one!"
        status_text = "REJECTED"
        status_emoji = "❌"
    
    try:
        await context.bot.send_message(chat_id=user_id, text=user_message, parse_mode='Markdown')
    except Exception as e:
        logger.warning(f"⚠️ Could not notify user {user_id}: {e}")
    
    await query.edit_message_text(
        f"{status_emoji} *Confession {status_text}!*\n\n"
        f"Confession #{confession_id} has been {status_text.lower()}.\n"
        f"User has been notified.",
        parse_mode='Markdown'
    )

async def cancel_confession(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the current operation."""
    
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        await query.edit_message_text("❌ Operation cancelled. Use /start to try again.")
    elif update.message:
        await update.message.reply_text("❌ Operation cancelled. Use /start to try again.")

    context.user_data.clear()
    return ConversationHandler.END

async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Return to main menu."""
    query = update.callback_query
    await query.answer()
    
    welcome_text = "🤫 *WU Confession Bot*\n\nClick below to start:"
    keyboard = [
        [InlineKeyboardButton("📝 Start Confession", callback_data="start_confess")],
        [InlineKeyboardButton("ℹ️ How It Works", callback_data="how_it_works")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(welcome_text, reply_markup=reply_markup, parse_mode='Markdown')

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle regular messages."""
    await update.message.reply_text(
        "🤫 *WU Confession Bot*\n\nUse /start to begin your anonymous confession!",
        parse_mode='Markdown'
    )

# --- NEW COMMENT FLOW HANDLERS ---

def format_comments(comments, confession_id):
    """Formats the list of comments into a readable string."""
    text = f"💬 *Replies for Confession #{confession_id}*\n\n"
    
    if not comments:
        text += "No replies yet. Be the first one to comment!"
    
    for username, comment_text, timestamp in comments:
        # Extract date and time
        time_str = datetime.strptime(timestamp.split('.')[0], '%Y-%m-%d %H:%M:%S').strftime('%H:%M %b %d')
        text += f"👤 *{username}* - {time_str}\n"
        text += f"_{comment_text}_\n\n"
    
    text += "---"
    return text


async def start_commenting(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point for the comment flow, triggered by the /start payload. 
    Shows existing comments and presents the menu."""
    
    # Check if this is a message from the deep link or a callback
    if update.message:
        payload = context.args[0] if context.args else None
    else: # This shouldn't happen in the entry point, but good practice
        await update.callback_query.answer()
        return ConversationHandler.END

    if not payload or not payload.startswith('comment_'):
        await update.message.reply_text("❌ Invalid link format. Please click the button on the confession post.")
        return ConversationHandler.END

    confession_id = int(payload.split('_')[1])
    context.user_data['comment_confession_id'] = confession_id
    
    comments = db.get_comments(confession_id)
    comment_list_text = format_comments(comments, confession_id)
    
    # 1. Display existing comments
    await update.message.reply_text(comment_list_text, parse_mode='Markdown')

    # 2. Present the menu options
    menu_text = "What would you like to do next?"
    keyboard = [
        [InlineKeyboardButton("➕ Add New Reply", callback_data=f"add_reply_{confession_id}")],
        [InlineKeyboardButton("❌ Cancel / Exit", callback_data="cancel_comment")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(menu_text, reply_markup=reply_markup, parse_mode='Markdown')
    
    return COMMENT_MENU_STATE

async def prompt_for_comment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Moves the state from COMMENT_MENU_STATE to WRITING_COMMENT."""
    query = update.callback_query
    await query.answer()
    
    confession_id = context.user_data.get('comment_confession_id')
    
    await query.edit_message_text(
        f"📝 *Writing Reply for Confession #{confession_id}:*\n\n"
        "Type your comment below. It will be visible to everyone. Use /cancel to stop.",
        parse_mode='Markdown'
    )
    
    return WRITING_COMMENT

async def receive_comment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receives and saves the new comment."""
    user = update.effective_user
    user_id = user.id
    username = user.first_name or "Anon User"
    
    confession_id = context.user_data.get('comment_confession_id')
    comment_text = update.message.text.strip()
    
    if not confession_id:
        await update.message.reply_text("❌ Error: Confession ID missing. Please use /start.")
        context.user_data.clear()
        return ConversationHandler.END

    if len(comment_text) < 5 or len(comment_text) > 500:
        await update.message.reply_text(
            "❌ Comment must be between 5 and 500 characters. Please try again or use /cancel.",
            parse_mode='Markdown'
        )
        return WRITING_COMMENT

    # Save to database
    comment_id = db.save_comment(confession_id, user_id, username, comment_text)

    if comment_id:
        await update.message.reply_text(
            "✅ *Reply Submitted!*\n\n"
            f"Your comment has been added to Confession #{confession_id}. Use /start to go to the main menu.",
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text("❌ Error saving your reply. Please try again.")

    context.user_data.clear()
    return ConversationHandler.END

# --- END NEW COMMENT FLOW HANDLERS ---

# --- ADMIN HANDLERS (Unchanged) ---
async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show statistics for admin."""
    if str(update.effective_user.id) != ADMIN_CHAT_ID:
        await update.message.reply_text("❌ Admin only command.")
        return
    
    conn = sqlite3.connect('confessions.db', check_same_thread=False)
    cursor = conn.cursor()
    
    # Get counts
    cursor.execute('SELECT COUNT(*) FROM confessions')
    total = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM confessions WHERE status = "pending"')
    pending = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM confessions WHERE status = "approved"')
    approved = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM confessions WHERE status = "rejected"')
    rejected = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM comments') # NEW comment count
    comment_count = cursor.fetchone()[0] 
    
    conn.close()
    
    stats_text = (
        "📊 *Bot Statistics*\n\n"
        f"📝 *Total Confessions:* {total}\n"
        f"💬 *Total Replies:* {comment_count}\n\n"
        f"⏳ *Pending Approval:* {pending}\n"
        f"✅ *Approved:* {approved}\n"
        f"❌ *Rejected:* {rejected}\n\n"
        f"📈 *Approval Rate:* {approved/(total or 1)*100:.1f}%"
    )
    
    await update.message.reply_text(stats_text, parse_mode='Markdown')


def main():
    """Start the bot."""
    print("🚀 Starting WU Confession Bot...")
    
    application = Application.builder().token(BOT_TOKEN).build()
    
    # --- CONVERSATION HANDLERS ---
    
    # 1. Confession Submission Handler
    confession_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_confession, pattern="^start_confess$")],
        states={
            SELECTING_CATEGORY: [
                CallbackQueryHandler(select_category, pattern="^category_"),
                CallbackQueryHandler(cancel_confession, pattern="^cancel_confession$")
            ],
            WRITING_CONFESSION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_confession),
                CommandHandler('cancel', cancel_confession)
            ]
        },
        fallbacks=[CommandHandler('start', start)]
    )
    
    # 2. Comment Submission Handler (Triggered by /start payload from channel link)
    comment_handler = ConversationHandler(
        # Entry point: The deep link command
        entry_points=[
            CommandHandler('start', start_commenting, filters=filters.Regex(r'^comment_\d+$'), block=False)
        ],
        states={
            # State 1: User sees comments and menu
            COMMENT_MENU_STATE: [
                CallbackQueryHandler(prompt_for_comment, pattern="^add_reply_"),
                CallbackQueryHandler(cancel_confession, pattern="^cancel_comment$")
            ],
            # State 2: User is typing their comment
            WRITING_COMMENT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_comment),
                CommandHandler('cancel', cancel_confession)
            ]
        },
        fallbacks=[CommandHandler('start', start)]
    )

    # --- ADD HANDLERS ---
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("stats", show_stats))
    application.add_handler(CommandHandler("cancel", cancel_confession))
    
    # The ORDER MATTERS: Comment handler must be added before the general handler for /start
    application.add_handler(comment_handler)
    
    application.add_handler(confession_handler)
    application.add_handler(CallbackQueryHandler(handle_admin_approval, pattern="^(approve|reject)_"))
    application.add_handler(CallbackQueryHandler(how_it_works, pattern="^how_it_works$"))
    application.add_handler(CallbackQueryHandler(main_menu, pattern="^main_menu$"))
    
    # Default message handler
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    application.run_polling()

if __name__ == '__main__':
    main()