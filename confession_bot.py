import os
import sys
import sqlite3
import logging
import threading
import time
import requests # Added for internal keep-alive ping
from datetime import datetime
from flask import Flask, jsonify # Added jsonify for health check
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

# --- Configuration & Validation ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_CHAT_ID_RAW = os.getenv("ADMIN_CHAT_ID", "")
ADMIN_CHAT_IDS = [id.strip() for id in ADMIN_CHAT_ID_RAW.split(',') if id.strip()] if ADMIN_CHAT_ID_RAW else []
CHANNEL_ID = os.getenv("CHANNEL_ID")
BOT_USERNAME = os.getenv("BOT_USERNAME")
FLASK_PORT = int(os.environ.get('PORT', 5000)) # Get port from environment or default

# Validate environment variables (simplified for brevity, but keep in a real app)
if not all([BOT_TOKEN, ADMIN_CHAT_IDS, CHANNEL_ID, BOT_USERNAME]):
    print("❌ ERROR: Missing required environment variables (BOT_TOKEN, ADMIN_CHAT_ID, CHANNEL_ID, BOT_USERNAME)")
    sys.exit(1)

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

*💌 Submit Confession*: Share your anonymous confession (10-1000 characters)
*📖 Browse Confessions*: Read approved confessions by category  
*💬 Comment System*: Discuss confessions anonymously
*👮 Admin Review*: All confessions are reviewed before posting

🔒 *Your anonymity is guaranteed*
📝 All submissions are reviewed before posting
⏰ Typically approved within 24 hours

*How to Use:*
1. Click *💌 Submit Confession* to share your thoughts
2. Choose a category and write your confession
3. Wait for admin approval
4. Browse approved confessions using *📖 Browse Confessions*
5. Add comments to discuss confessions
"""

# Conversation States
SELECTING_CATEGORY, WRITING_CONFESSION, BROWSING_CONFESSIONS, WRITING_COMMENT = range(4)

CATEGORY_MAP = {
    "relationship": "💔 Love & Relationships", 
    "friendship": "👥 Friendship", 
    "campus": "📚 Academic Stress", 
    "general": "🌟 Other", 
    "vent": "😨 Fear & Anxiety", 
    "secret": "😔 Regrets",
    "recent": "📚 Latest Confessions" # For browsing category names
}
# Reverse map for database storage
REVERSE_CATEGORY_MAP = {v: k for k, v in CATEGORY_MAP.items()}

# --- Enhanced Flask App for 24/7 Health Checks ---
app = Flask(__name__)
start_time = time.time()

@app.route('/')
def home():
    """Main health check endpoint - for human readability."""
    uptime = time.time() - start_time
    hours = int(uptime // 3600)
    minutes = int((uptime % 3600) // 60)
    seconds = int(uptime % 60)
    
    return f"""
    <html>
        <body>
            <h1>🤫 Confession Bot Status</h1>
            <p>Status: <strong>RUNNING</strong></p>
            <p>Uptime: {hours}h {minutes}m {seconds}s</p>
            <p>Check: <a href="/health">/health</a> for machine check</p>
        </body>
    </html>
    """

@app.route('/health')
def health():
    """JSON health check endpoint for UptimeRobot/Render."""
    return jsonify({
        "status": "healthy",
        "service": "confession-bot",
        "timestamp": datetime.now().isoformat()
    })

def run_flask():
    """Run Flask app with enhanced configuration."""
    print(f"🚀 Starting Flask health server on port {FLASK_PORT}")
    # Setting use_reloader=False is crucial when running with telegram.ext
    app.run(host='0.0.0.0', port=FLASK_PORT, debug=False, use_reloader=False)

# --- Keep Alive Background Thread ---
def keep_alive_ping():
    """Background thread to ping the health endpoint regularly (self-ping)."""
    # Use the public URL to ensure external network activity
    base_url = f"http://localhost:{FLASK_PORT}" 
    
    # Wait 30 seconds to allow the Flask thread to start
    time.sleep(30) 
    
    while True:
        try:
            response = requests.get(f"{base_url}/health", timeout=10)
            if response.status_code == 200:
                logger.info(f"✅ Keep-alive ping successful at {datetime.now().strftime('%H:%M:%S')}")
            else:
                logger.warning(f"⚠️ Keep-alive ping failed: {response.status_code}")
        except Exception as e:
            logger.error(f"❌ Keep-alive ping error: {e}")
            
        # Ping every 5 minutes (300 seconds) to stay alive
        time.sleep(300)

# --- Database Management ---
class DatabaseManager:
    def __init__(self):
        self.init_database()
    
    def init_database(self):
        conn = None
        try:
            # check_same_thread=False is essential for multi-threaded bots
            conn = sqlite3.connect('confessions.db', check_same_thread=False) 
            cursor = conn.cursor()
            
            # Confessions table
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
            
            # Comments table
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

    # --- CRUD Methods (Abbreviated to keep file shorter) ---
    # (Your original CRUD methods: save_confession, update_confession_status, 
    # get_confession, get_approved_confessions, save_comment, get_comments, get_comments_count)
    
    def save_confession(self, user_id, username, category, confession_text):
        conn = sqlite3.connect('confessions.db', check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute('INSERT INTO confessions (user_id, username, category, confession_text) VALUES (?, ?, ?, ?)', (user_id, username, category, confession_text))
        confession_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return confession_id

    def update_confession_status(self, confession_id, status, channel_message_id=None):
        conn = sqlite3.connect('confessions.db', check_same_thread=False)
        cursor = conn.cursor()
        if channel_message_id is not None:
            cursor.execute('UPDATE confessions SET status = ?, channel_message_id = ? WHERE id = ?', (status, channel_message_id, confession_id))
        else:
            cursor.execute('UPDATE confessions SET status = ? WHERE id = ?', (status, confession_id))
        conn.commit()
        conn.close()

    def get_confession(self, confession_id):
        conn = sqlite3.connect('confessions.db', check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM confessions WHERE id = ?', (confession_id,))
        result = cursor.fetchone()
        conn.close()
        return result
    
    def get_approved_confessions(self, category=None, limit=50):
        conn = sqlite3.connect('confessions.db', check_same_thread=False)
        cursor = conn.cursor()
        if category and category != "recent":
            cursor.execute('SELECT id, confession_text, category, timestamp FROM confessions WHERE status = "approved" AND category = ? ORDER BY id DESC LIMIT ?', (category, limit))
        else:
            cursor.execute('SELECT id, confession_text, category, timestamp FROM confessions WHERE status = "approved" ORDER BY id DESC LIMIT ?', (limit,))
        result = cursor.fetchall()
        conn.close()
        return result

    def save_comment(self, confession_id, user_id, username, comment_text):
        conn = sqlite3.connect('confessions.db', check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute('INSERT INTO comments (confession_id, user_id, username, comment_text) VALUES (?, ?, ?, ?)', (confession_id, user_id, username, comment_text))
        comment_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return comment_id

    def get_comments(self, confession_id):
        conn = sqlite3.connect('confessions.db', check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute('SELECT username, comment_text, timestamp FROM comments WHERE confession_id = ? ORDER BY timestamp ASC', (confession_id,))
        result = cursor.fetchall()
        conn.close()
        return result

    def get_comments_count(self, confession_id):
        conn = sqlite3.connect('confessions.db', check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM comments WHERE confession_id = ?', (confession_id,))
        count = cursor.fetchone()[0]
        conn.close()
        return count
    
# Initialize database
db = DatabaseManager()

# --- Keyboard Functions (Your original functions, assumed correct) ---

def get_main_keyboard():
    buttons = [
        [InlineKeyboardButton("💌 Submit Confession", callback_data="start_confess")],
        [InlineKeyboardButton("📖 Browse Confessions", callback_data="browse_menu")],
        [InlineKeyboardButton("❓ Help & Guidelines", callback_data="help_info")]
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
        [InlineKeyboardButton("📚 Latest Confessions", callback_data="browse_recent")],
        [InlineKeyboardButton("💔 Love & Relationships", callback_data="browse_relationship")],
        [InlineKeyboardButton("👥 Friendship", callback_data="browse_friendship")],
        [InlineKeyboardButton("📚 Academic Stress", callback_data="browse_campus")],
        [InlineKeyboardButton("😨 Fear & Anxiety", callback_data="browse_vent")],
        [InlineKeyboardButton("😔 Regrets", callback_data="browse_secret")],
        [InlineKeyboardButton("🌟 Other", callback_data="browse_general")],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(buttons)

def get_confession_discussion_keyboard(confession_id):
    comments_count = db.get_comments_count(confession_id)
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(f"💬 Add Comment ({comments_count})", callback_data=f"add_comment_{confession_id}"),
            InlineKeyboardButton("📜 View Comments", callback_data=f"view_comments_{confession_id}")
        ],
        [InlineKeyboardButton("📖 Browse More Confessions", callback_data="browse_menu")],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
    ])

def get_confession_browse_keyboard(confession_id, total, index):
    comments_count = db.get_comments_count(confession_id)
    buttons = []
    
    # Navigation buttons
    nav_row = []
    if index > 1:
        nav_row.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"prev_{confession_id}"))
    if index < total:
        nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"next_{confession_id}"))
    
    # Action buttons with comment count
    action_buttons = [
        [
            InlineKeyboardButton(f"💬 Add Comment ({comments_count})", callback_data=f"add_comment_{confession_id}"),
            InlineKeyboardButton("📜 View Comments", callback_data=f"view_comments_{confession_id}")
        ],
        [InlineKeyboardButton("📚 Browse Categories", callback_data="browse_menu")],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
    ]
    
    rows = []
    if nav_row:
        rows.append(nav_row)
    rows.extend(action_buttons)
    
    return InlineKeyboardMarkup(rows)

def get_admin_keyboard(confession_id):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Approve", callback_data=f"approve_{confession_id}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"reject_{confession_id}")
        ]
    ])

def get_comments_management_keyboard(confession_id):
    comments_count = db.get_comments_count(confession_id)
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"💬 Add Comment ({comments_count})", callback_data=f"add_comment_{confession_id}")],
        [InlineKeyboardButton("⬅️ Back to Confession", callback_data=f"back_to_confession_{confession_id}")],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
    ])

def get_channel_post_keyboard(confession_id):
    url = f"https://t.me/{BOT_USERNAME}?start=discuss_{confession_id}"
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("💬 Comment & Discuss", url=url)
    ]])

# --- Helper Functions (Your original functions, assumed correct) ---

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
        f"*Category:* {category}\n"
        f"*Comments:* 💬 {comments_count}\n\n"
        f"_Click below to join the discussion!_ 👇"
    )

def format_confession_full(confession_data, index, total):
    # Data: (id, text, formatted_category, timestamp)
    confession_id, text, category, timestamp = confession_data
    
    try:
        dt = datetime.fromisoformat(timestamp)
        date_str = dt.strftime("%b %d, %Y at %H:%M")
    except (ValueError, TypeError):
        date_str = "recently"
        
    comments_count = db.get_comments_count(confession_id)
    
    return (
        f"📝 *Confession #{confession_id}* ({index}/{total})\n\n"
        f"*{category}* • {date_str}\n\n"
        f"{text}\n\n"
        f"💬 *{comments_count} comments* • Join the discussion below!"
    )

def format_discussion_welcome(confession_id, confession_data):
    # Data: (id, text, formatted_category, timestamp)
    confession_id, text, category, timestamp = confession_data
    
    try:
        dt = datetime.fromisoformat(timestamp)
        date_str = dt.strftime("%b %d, %Y at %H:%M")
    except (ValueError, TypeError):
        date_str = "recently"
        
    comments_count = db.get_comments_count(confession_id)
    
    return (
        f"💬 *Discussion for Confession #{confession_id}*\n\n"
        f"*{category}* • {date_str}\n\n"
        f"{text}\n\n"
        f"🔍 *{comments_count} comments* • Share your thoughts below!"
    )

def format_comments_list(confession_id, comments_list):
    header = f"💬 *Comments for Confession #{confession_id}* ({len(comments_list)} total)\n\n"
    
    if not comments_list:
        return header + "No comments yet. Be the first to share your thoughts! 💭"
        
    comment_blocks = []
    
    for i, (username, text, timestamp) in enumerate(comments_list):
        safe_comment_text = escape_markdown_text(text)
        # Use simple Anonymous #N naming for anonymity
        anon_name = f"Anonymous #{i+1}" 
        
        time_str = ""
        try:
            dt = datetime.fromisoformat(timestamp.split('.')[0])
            time_str = dt.strftime('%H:%M • %b %d')
        except Exception:
            time_str = "recently"

        comment_blocks.append(f"👤 *{anon_name}* ({time_str}):\n» {safe_comment_text}\n")
            
    return header + "\n".join(comment_blocks)

# --- Handler Functions (Your original functions) ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    
    # Check if it's a deep link from channel
    if context.args:
        payload = context.args[0]
        if payload.startswith('discuss_'):
            try:
                confession_id = int(payload.split('_')[1])
                confession = db.get_confession(confession_id)
                
                if confession and confession[6] == 'approved':
                    # Confession data is (id, text, db_category, timestamp)
                    confession_data = (confession[0], confession[4], CATEGORY_MAP.get(confession[3], confession[3]), confession[5]) 
                    await update.message.reply_text(
                        format_discussion_welcome(confession_id, confession_data),
                        parse_mode='Markdown',
                        reply_markup=get_confession_discussion_keyboard(confession_id)
                    )
                    return BROWSING_CONFESSIONS
            except (IndexError, ValueError, Exception) as e:
                logger.error(f"Error handling deep link: {e}")
    
    welcome_text = (
        "🤫 *Welcome to Confession Bot!*\n\n"
        "• Share your thoughts *anonymously*\n"
        "• Read confessions from others\n"
        "• Discuss with comments\n\n"
        "🔒 *Your privacy is protected*\n"
        "👮 *All posts are reviewed by admins*"
    )
    
    await update.message.reply_text(
        welcome_text, 
        reply_markup=get_main_keyboard(), 
        parse_mode='Markdown'
    )
    return ConversationHandler.END

async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    welcome_text = "🤫 *Confession Bot*\n\nWelcome back! What would you like to do?"
    
    try:
        await query.edit_message_text(
            welcome_text, 
            parse_mode='Markdown',
            reply_markup=get_main_keyboard()
        )
    except Exception as e:
        logger.warning(f"main_menu edit failed: {e}")
        
    return ConversationHandler.END

async def help_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        HELP_TEXT,
        parse_mode='Markdown',
        reply_markup=get_main_keyboard()
    )
    return ConversationHandler.END

# --- Confession Submission Logic ---
async def start_confession(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    context.user_data.clear()
    
    await query.edit_message_text(
        "📂 *Select a category for your confession:*\n\n"
        "Choose the category that best fits your confession:",
        reply_markup=get_category_keyboard(),
        parse_mode='Markdown'
    )
    
    return SELECTING_CATEGORY

async def select_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    key = query.data.replace("cat_", "")
    # Save the database key (e.g., 'relationship')
    context.user_data['db_category'] = key 
    # Use the display name for the prompt
    display_category = CATEGORY_MAP.get(key, '🌟 Other')
    
    await query.edit_message_text(
        f"✅ *Category Selected:* {display_category}\n\n"
        "📝 *Now write your confession:*\n\n"
        "Please type your confession below:\n"
        "• 10-1000 characters\n"
        "• Be respectful\n"
        "• No personal information\n\n"
        "Your confession will be reviewed by admins before posting.",
        parse_mode='Markdown'
    )
    
    return WRITING_CONFESSION

async def receive_confession(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    username = update.effective_user.first_name or "Anonymous"
    confession_text = update.message.text.strip()
    # Get the database key
    db_category = context.user_data.get('db_category', 'general') 
    display_category = CATEGORY_MAP.get(db_category, '🌟 Other')

    # Validation
    if not (10 <= len(confession_text) <= 1000):
        await update.message.reply_text(
            f"❌ *Length Error!* Your confession must be between 10 and 1000 characters (Yours: {len(confession_text)}).\n\nTry again:",
            parse_mode='Markdown'
        )
        return WRITING_CONFESSION
    
    # Save confession using the database key
    confession_id = db.save_confession(user_id, username, db_category, confession_text)
    
    if not confession_id:
        await update.message.reply_text("❌ *Error submitting confession.* Please try again later.", parse_mode='Markdown', reply_markup=get_main_keyboard())
        context.user_data.clear()
        return ConversationHandler.END

    # Prepare admin notification
    admin_message = (
        f"🆕 *New Confession Pending Review* #{confession_id}\n\n"
        f"👤 *User:* {username} (ID: {user_id})\n"
        f"📂 *Category:* {display_category}\n"
        f"📝 *Confession:* {escape_markdown_text(confession_text)}\n\n"
        f"*Please review this confession:*"
    )
    
    # Send to all admins
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
            
    # Notify user
    await update.message.reply_text(
        "✅ *Confession Submitted Successfully!*\n\n"
        "Your confession has been sent for admin review. You'll be notified when it's approved.\n\n"
        "🔒 *Anonymous* • ⏰ *24h review* • 📢 *Channel post if approved*",
        parse_mode='Markdown',
        reply_markup=get_main_keyboard()
    )
        
    context.user_data.clear()
    return ConversationHandler.END

async def cancel_confession(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "❌ Confession cancelled.\n\nReturning to main menu.", 
        reply_markup=get_main_keyboard()
    )
    context.user_data.clear()
    return ConversationHandler.END

# --- Admin Functions (Your original functions) ---
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
        await query.edit_message_text(f"❌ Confession #{confession_id} not found or already processed.")
        return
    
    # Unpack confession: (id, user_id, username, category_key, text, timestamp, status, channel_msg_id)
    submitter_user_id = confession[1]
    category_key = confession[3]
    confession_text = confession[4]
    display_category = CATEGORY_MAP.get(category_key, '🌟 Other')
    
    if action == 'approve':
        try:
            # Post to channel
            channel_text = format_channel_post(confession_id, display_category, confession_text)
            channel_message = await context.bot.send_message(
                chat_id=CHANNEL_ID,
                text=channel_text,
                reply_markup=get_channel_post_keyboard(confession_id), 
                parse_mode='Markdown'
            )
            
            # Update database with new status and channel message ID
            db.update_confession_status(confession_id, 'approved', channel_message.message_id)
            
            # Notify submitter
            user_message = "🎉 *Your Confession Has Been Approved!*"
            status_text = "APPROVED"
            status_emoji = "✅"
            try:
                await context.bot.send_message(chat_id=submitter_user_id, text=user_message, parse_mode='Markdown')
            except Exception as e:
                logger.warning(f"Could not notify user {submitter_user_id}: {e}")
                
        except Exception as e:
            logger.error(f"Failed to post to channel: {e}")
            await query.answer("❌ Failed to post to channel. Check bot permissions.", show_alert=True)
            return
            
    elif action == 'reject':
        db.update_confession_status(confession_id, 'rejected')
        user_message = "❌ *Confession Not Approved*\n\nYour confession did not meet our guidelines."
        status_text = "REJECTED"
        status_emoji = "❌"
        
        try:
            await context.bot.send_message(chat_id=submitter_user_id, text=user_message, parse_mode='Markdown')
        except Exception as e:
            logger.warning(f"Could not notify user {submitter_user_id}: {e}")

    # Update admin message
    await query.edit_message_text(
        f"{status_emoji} *Confession {status_text}!*\n\n"
        f"Confession #{confession_id} has been {status_text.lower()}.\n"
        f"The user has been notified.",
        parse_mode='Markdown'
    )

# --- Browsing Logic ---
async def browse_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    browse_text = (
        "📚 *Browse Confessions*\n\n"
        "Choose a category to explore confessions:\n"
        "• *Latest* - Most recent confessions\n"
        "• *By Category* - Filter by specific topics"
    )
    
    if update.message:
        await update.message.reply_text(
            browse_text,
            reply_markup=get_browse_keyboard(),
            parse_mode='Markdown'
        )
    else:
        query = update.callback_query
        await query.answer()
        try:
            await query.edit_message_text(
                browse_text,
                reply_markup=get_browse_keyboard(),
                parse_mode='Markdown'
            )
        except:
             # Fallback if the message hasn't been modified recently
             await query.message.reply_text(
                browse_text,
                reply_markup=get_browse_keyboard(),
                parse_mode='Markdown'
            )

    return BROWSING_CONFESSIONS

async def display_confession(update: Update, context: ContextTypes.DEFAULT_TYPE, index: int):
    """Helper function to display a specific confession by index."""
    confessions = context.user_data.get('confessions_list')
    if not confessions:
        await update.effective_chat.send_message("❌ Browsing session expired. Please start browsing again.", reply_markup=get_browse_keyboard())
        return BROWSING_CONFESSIONS
        
    total = len(confessions)
    if not (0 <= index < total):
        if update.callback_query:
            await update.callback_query.answer("No more confessions in this category.", show_alert=True)
        return

    context.user_data['current_index'] = index
    
    # Data is: (id, text, db_category, timestamp)
    raw_data = confessions[index] 
    
    # Convert DB category key to display name for formatting
    display_category = CATEGORY_MAP.get(raw_data[2], '🌟 Other') 
    confession_data = (raw_data[0], raw_data[1], display_category, raw_data[3])
    confession_id = raw_data[0]
    
    formatted_text = format_confession_full(confession_data, index + 1, total)
    keyboard = get_confession_browse_keyboard(confession_id, total, index + 1)
    
    try:
        if update.callback_query:
            await update.callback_query.edit_message_text(
                formatted_text,
                reply_markup=keyboard,
                parse_mode='Markdown'
            )
        else: # Used for deep links or initial command response if needed
             await update.message.reply_text(
                formatted_text,
                reply_markup=keyboard,
                parse_mode='Markdown'
            )
    except Exception as e:
        logger.warning(f"Error displaying confession: {e}")
        # Send as new message if edit fails (e.g., message too old)
        await update.effective_chat.send_message(
            formatted_text,
            reply_markup=keyboard,
            parse_mode='Markdown'
        )

async def start_browse_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    browse_key = query.data.replace("browse_", "") 
    display_category_name = CATEGORY_MAP.get(browse_key, "Latest") 
    
    # The key is passed to the DB manager (e.g., 'relationship' or 'recent')
    confessions_raw = db.get_approved_confessions(category=browse_key if browse_key != "recent" else None, limit=50)

    # Store list as (id, text, db_category, timestamp)
    context.user_data['confessions_list'] = confessions_raw 
    
    if not confessions_raw:
        await query.edit_message_text(
            f"🚫 *No approved confessions found in the '{display_category_name}' category yet.*",
            reply_markup=get_browse_keyboard(),
            parse_mode='Markdown'
        )
        return BROWSING_CONFESSIONS
        
    # Display the first confession
    await display_confession(update, context, index=0)

    return BROWSING_CONFESSIONS

async def browse_navigation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    confessions = context.user_data.get('confessions_list')
    current_index = context.user_data.get('current_index', 0)
    
    if not confessions:
        await query.edit_message_text(
            "Session expired. Please start browsing again.",
            reply_markup=get_browse_keyboard(),
            parse_mode='Markdown'
        )
        return BROWSING_CONFESSIONS

    action = query.data.split('_')[0]
    
    new_index = current_index
    if action == 'next':
        new_index += 1
    elif action == 'prev':
        new_index -= 1
    
    await display_confession(update, context, index=new_index)
    return BROWSING_CONFESSIONS

async def handle_back_to_confession(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    try:
        confession_id = int(query.data.split('_')[-1])
    except:
        await query.edit_message_text("❌ Invalid command. Returning to main menu.", reply_markup=get_main_keyboard())
        return ConversationHandler.END

    confessions = context.user_data.get('confessions_list', [])
    index = -1
    
    for i, c in enumerate(confessions):
        if c[0] == confession_id:
            index = i
            break

    if index != -1:
        # If the confession is in the current browsing list, display it normally
        await display_confession(update, context, index=index)
    else:
        # Fallback for deep links or expired session
        confession = db.get_confession(confession_id)
        if confession and confession[6] == 'approved':
            # Data: (id, text, db_category, timestamp)
            display_category = CATEGORY_MAP.get(confession[3], confession[3])
            confession_data = (confession[0], confession[4], display_category, confession[5])
            
            formatted_text = format_discussion_welcome(confession_id, confession_data)
            await query.edit_message_text(
                formatted_text,
                reply_markup=get_confession_discussion_keyboard(confession_id),
                parse_mode='Markdown'
            )
        else:
            await query.edit_message_text(
                f"❌ Confession #{confession_id} not available.",
                reply_markup=get_browse_keyboard(),
                parse_mode='Markdown'
            )

    return BROWSING_CONFESSIONS

# --- Comment Logic ---
async def start_add_comment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    try:
        confession_id = int(query.data.split('_')[-1])
    except:
        await query.edit_message_text("❌ Invalid action. Returning to main menu.", reply_markup=get_main_keyboard())
        return ConversationHandler.END

    confession = db.get_confession(confession_id)
    if not confession or confession[6] != 'approved':
        await query.edit_message_text("❌ This confession is no longer available for comments.", reply_markup=get_browse_keyboard())
        return BROWSING_CONFESSIONS
        
    context.user_data['comment_confession_id'] = confession_id
    
    await query.edit_message_text(
        f"💬 *Confession #{confession_id}: Write Your Comment*\n\n"
        f"Your comment will be posted anonymously. Be respectful!\n\n"
        f"📝 *Enter your comment (max 500 characters):*",
        parse_mode='Markdown'
    )
    
    return WRITING_COMMENT

async def receive_comment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    confession_id = context.user_data.get('comment_confession_id')
    user_id = update.effective_user.id
    username = update.effective_user.first_name or "Anonymous"
    comment_text = update.message.text.strip()

    if not confession_id:
        await update.message.reply_text("❌ Comment session expired. Please start again from the confession.", reply_markup=get_main_keyboard())
        context.user_data.clear()
        return ConversationHandler.END

    # Validation
    if not (1 <= len(comment_text) <= 500):
        await update.message.reply_text(f"❌ Comment must be 1-500 characters. Yours: {len(comment_text)}.\n\nPlease try again:", parse_mode='Markdown')
        return WRITING_COMMENT

    # Save comment
    comment_id = db.save_comment(confession_id, user_id, username, comment_text)
    
    if comment_id:
        await update.message.reply_text(
            f"✅ *Comment posted successfully!*\n\n"
            f"View all comments for Confession #{confession_id} below.",
            reply_markup=get_comments_management_keyboard(confession_id),
            parse_mode='Markdown'
        )
        # TODO: Update the channel message comment count (Requires storing channel message ID and editing)

    else:
        await update.message.reply_text("❌ Error saving comment. Please try again later.", reply_markup=get_main_keyboard())
    
    if 'comment_confession_id' in context.user_data:
        del context.user_data['comment_confession_id']
    
    return BROWSING_CONFESSIONS

async def view_comments(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    try:
        confession_id = int(query.data.split('_')[-1])
    except:
        await query.edit_message_text("❌ Invalid action. Returning to main menu.", reply_markup=get_main_keyboard())
        return ConversationHandler.END

    comments = db.get_comments(confession_id)
    formatted_comments = format_comments_list(confession_id, comments)
    
    try:
        await query.edit_message_text(
            formatted_comments,
            reply_markup=get_comments_management_keyboard(confession_id),
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.warning(f"View comments edit failed: {e}")
        # If edit fails, send a new message
        await query.message.reply_text(
            formatted_comments,
            reply_markup=get_comments_management_keyboard(confession_id),
            parse_mode='Markdown'
        )
    
    return BROWSING_CONFESSIONS

# --- Main function setup ---
def main() -> None:
    """Start the bot."""
    
    # 1. Start Flask in a separate thread for health checks (24/7 uptime)
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # 2. Start keep-alive ping thread (internal redundancy for 24/7 uptime)
    keep_alive_thread = threading.Thread(target=keep_alive_ping, daemon=True)
    keep_alive_thread.start()

    # 3. Create the Application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Conversation Handler for Confession Submission
    confession_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_confession, pattern="^start_confess$")],
        states={
            SELECTING_CATEGORY: [
                CallbackQueryHandler(select_category, pattern="^cat_"),
                CallbackQueryHandler(cancel_confession, pattern="^cancel_confess$")
            ],
            WRITING_CONFESSION: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_confession)],
        },
        fallbacks=[
            CallbackQueryHandler(main_menu, pattern="^main_menu$"),
        ]
    )

    # Conversation Handler for Browsing & Commenting
    browsing_handler = ConversationHandler(
        entry_points=[
            CommandHandler("browse", browse_menu),
            CallbackQueryHandler(browse_menu, pattern="^browse_menu$"),
            # Ensure /start handles deep links and transitions to BROWSING_CONFESSIONS if needed
            CommandHandler("start", start) 
        ],
        states={
            BROWSING_CONFESSIONS: [
                CallbackQueryHandler(start_browse_category, pattern="^browse_"),
                CallbackQueryHandler(browse_navigation, pattern="^(next|prev)_"),
                CallbackQueryHandler(start_add_comment, pattern="^add_comment_"),
                CallbackQueryHandler(view_comments, pattern="^view_comments_"),
                CallbackQueryHandler(handle_back_to_confession, pattern="^back_to_confession_"),
                CallbackQueryHandler(main_menu, pattern="^main_menu$"),
            ],
            WRITING_COMMENT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_comment),
            ]
        },
        fallbacks=[
            CallbackQueryHandler(main_menu, pattern="^main_menu$"),
        ]
    )
    
    # Main Handlers
    application.add_handler(CommandHandler("start", start)) # Re-added in case it's not a deep link
    application.add_handler(CommandHandler("help", help_info))
    application.add_handler(CallbackQueryHandler(help_info, pattern="^help_info$"))
    application.add_handler(CallbackQueryHandler(main_menu, pattern="^main_menu$"))

    # Admin Handler (Must be outside the ConversationHandlers)
    application.add_handler(CallbackQueryHandler(handle_admin_approval, pattern="^(approve|reject)_"))

    # Add the conversation handlers
    application.add_handler(confession_handler)
    application.add_handler(browsing_handler)
    
    # Run the bot
    print("🤖 Starting Telegram Bot... Polling started.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
