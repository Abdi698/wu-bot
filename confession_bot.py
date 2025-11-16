import os
import sys
import sqlite3
import logging
import threading
import time
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
ADMIN_CHAT_ID_RAW = os.getenv("ADMIN_CHAT_ID", "")
ADMIN_CHAT_IDS = [id.strip() for id in ADMIN_CHAT_ID_RAW.split(',') if id.strip()] if ADMIN_CHAT_ID_RAW else []
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

SELECTING_CATEGORY, WRITING_CONFESSION, BROWSING_CONFESSIONS, WRITING_COMMENT = range(4)

CATEGORY_MAP = {
    "relationship": "💔 Love & Relationships", 
    "friendship": "👥 Friendship", 
    "campus": "📚 Academic Stress", 
    "general": "🌟 Other", 
    "vent": "😨 Fear & Anxiety", 
    "secret": "😔 Regrets"
}

# --- Enhanced Flask App for Render Health Checks ---
app = Flask(__name__)

# Global variable to track bot status
bot_status = "starting"
start_time = time.time()

@app.route('/')
def home():
    """Main health check endpoint"""
    uptime = time.time() - start_time
    hours = int(uptime // 3600)
    minutes = int((uptime % 3600) // 60)
    seconds = int(uptime % 60)
    
    return f"""
    <html>
        <head>
            <title>🤫 Confession Bot</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 40px; }}
                .status {{ padding: 10px; border-radius: 5px; margin: 10px 0; }}
                .running {{ background: #d4edda; color: #155724; }}
                .stopped {{ background: #f8d7da; color: #721c24; }}
            </style>
        </head>
        <body>
            <h1>🤫 Confession Bot</h1>
            <div class="status running">
                Status: <strong>RUNNING</strong><br>
                Uptime: {hours}h {minutes}m {seconds}s<br>
                Started: {datetime.fromtimestamp(start_time).strftime('%Y-%m-%d %H:%M:%S')}
            </div>
            <p>Endpoints:</p>
            <ul>
                <li><a href="/health">/health</a> - JSON health check</li>
                <li><a href="/status">/status</a> - Bot status</li>
                <li><a href="/ping">/ping</a> - Simple ping</li>
            </ul>
        </body>
    </html>
    """

@app.route('/health')
def health():
    """JSON health check endpoint for Render"""
    uptime = time.time() - start_time
    return {
        "status": "healthy",
        "service": "confession-bot",
        "bot_status": "running",
        "uptime_seconds": int(uptime),
        "timestamp": datetime.now().isoformat()
    }

@app.route('/status')
def status():
    """Bot status endpoint"""
    uptime = time.time() - start_time
    return {
        "bot": BOT_USERNAME,
        "status": "running",
        "uptime": f"{int(uptime)} seconds",
        "database": "connected",
        "last_checked": datetime.now().isoformat()
    }

@app.route('/ping')
def ping():
    """Simple ping endpoint"""
    return "pong"

@app.route('/keepalive')
def keepalive():
    """Keepalive endpoint to prevent shutdown"""
    return {"status": "alive", "timestamp": datetime.now().isoformat()}

def run_flask():
    """Run Flask app with enhanced configuration"""
    port = int(os.environ.get('PORT', 5000))
    print(f"🚀 Starting Flask health server on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

# --- Keep Alive Background Thread ---
def keep_alive_ping():
    """Background thread to ping the health endpoint regularly"""
    import requests
    base_url = f"http://localhost:{os.environ.get('PORT', 5000)}"
    
    while True:
        try:
            response = requests.get(f"{base_url}/keepalive", timeout=10)
            if response.status_code == 200:
                print(f"✅ Keep-alive ping successful at {datetime.now().strftime('%H:%M:%S')}")
            else:
                print(f"⚠️ Keep-alive ping failed: {response.status_code}")
        except Exception as e:
            print(f"❌ Keep-alive ping error: {e}")
        
        # Ping every 5 minutes to stay alive
        time.sleep(300)

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
    
    def get_approved_confessions(self, category=None, limit=50):
        """Fetches approved confessions with limit for faster loading."""
        conn = None
        try:
            conn = sqlite3.connect('confessions.db', check_same_thread=False)
            cursor = conn.cursor()
            if category and category != "recent":
                cursor.execute(
                    'SELECT id, confession_text, category, timestamp FROM confessions WHERE status = "approved" AND category = ? ORDER BY id DESC LIMIT ?', 
                    (category, limit)
                )
            else:
                cursor.execute(
                    'SELECT id, confession_text, category, timestamp FROM confessions WHERE status = "approved" ORDER BY id DESC LIMIT ?',
                    (limit,)
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

# --- Keyboard Functions ---
def get_main_keyboard():
    """Main menu keyboard"""
    buttons = [
        [InlineKeyboardButton("💌 Submit Confession", callback_data="start_confess")],
        [InlineKeyboardButton("📖 Browse Confessions", callback_data="browse_menu")],
        [InlineKeyboardButton("❓ Help & Guidelines", callback_data="help_info")]
    ]
    return InlineKeyboardMarkup(buttons)

def get_category_keyboard():
    """Category selection keyboard"""
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
    """Browse categories keyboard"""
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
    """IMMEDIATE ACCESS: Direct comment buttons when user clicks from channel"""
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
    """Browse view keyboard with comment count"""
    comments_count = db.get_comments_count(confession_id)
    buttons = []
    
    # Navigation buttons
    if index > 1:
        buttons.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"prev_{confession_id}"))
    if index < total:
        buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"next_{confession_id}"))
    
    nav_row = [buttons] if buttons else []
    
    # Action buttons with comment count
    action_buttons = [
        [
            InlineKeyboardButton(f"💬 Add Comment ({comments_count})", callback_data=f"add_comment_{confession_id}"),
            InlineKeyboardButton("📜 View Comments", callback_data=f"view_comments_{confession_id}")
        ],
        [InlineKeyboardButton("📚 Browse Categories", callback_data="browse_menu")],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
    ]
    
    if nav_row:
        return InlineKeyboardMarkup([*nav_row, *action_buttons])
    else:
        return InlineKeyboardMarkup(action_buttons)

def get_admin_keyboard(confession_id):
    """Admin actions keyboard"""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Approve", callback_data=f"approve_{confession_id}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"reject_{confession_id}")
        ]
    ])

def get_comments_management_keyboard(confession_id):
    """Comments management keyboard"""
    comments_count = db.get_comments_count(confession_id)
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"💬 Add Comment ({comments_count})", callback_data=f"add_comment_{confession_id}")],
        [InlineKeyboardButton("⬅️ Back to Confession", callback_data=f"back_to_confession_{confession_id}")],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
    ])

def get_channel_post_keyboard(confession_id):
    """Channel post keyboard - goes directly to discussion page"""
    url = f"https://t.me/{BOT_USERNAME}?start=discuss_{confession_id}"
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("💬 Comment & Discuss", url=url)
    ]])

# --- Helper Functions ---
def escape_markdown_text(text):
    """Escape special characters for Telegram MarkdownV2."""
    escape_chars = r'_*[]()`>#+-.!|{}=~-'
    for char in escape_chars:
        text = text.replace(char, f'\\{char}')
    return text

def format_channel_post(confession_id, category, confession_text):
    """Format channel post with comment count"""
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
    """Full confession format with comment count"""
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
    """Welcome message when user clicks from channel"""
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
    """Format comments list"""
    header = f"💬 *Comments for Confession #{confession_id}* ({len(comments_list)} total)\n\n"
    
    if not comments_list:
        return header + "No comments yet. Be the first to share your thoughts! 💭"
        
    comment_blocks = []
    
    for i, (username, text, timestamp) in enumerate(comments_list):
        safe_comment_text = escape_markdown_text(text)
        anon_name = f"Anonymous #{i+1}"
        
        time_str = ""
        try:
            dt = datetime.fromisoformat(timestamp.split('.')[0])
            time_str = dt.strftime('%H:%M • %b %d')
        except Exception:
            time_str = "recently"

        comment_blocks.append(f"👤 *{anon_name}* ({time_str}):\n» {safe_comment_text}\n")
            
    return header + "\n".join(comment_blocks)

# --- Handler Functions ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send welcome message and main keyboard."""
    context.user_data.clear()
    
    # Check if it's a deep link from channel
    if context.args:
        payload = context.args[0]
        if payload.startswith('discuss_'):
            try:
                confession_id = int(payload.split('_')[1])
                confession = db.get_confession(confession_id)
                
                if confession and confession[6] == 'approved':
                    # Show discussion page immediately
                    confession_data = (confession[0], confession[4], confession[3], confession[5])
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
    """Return to main menu from an inline callback."""
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
    """Displays the help text from an inline button."""
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
    """Start the confession process."""
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
    """Handle category selection."""
    query = update.callback_query
    await query.answer()
    
    key = query.data.replace("cat_", "")
    category = CATEGORY_MAP.get(key, '🌟 Other')
    context.user_data['category'] = category
    
    await query.edit_message_text(
        f"✅ *Category Selected:* {category}\n\n"
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
    """Receive confession text, save to DB, and send admin link."""
    user_id = update.effective_user.id
    username = update.effective_user.first_name or "Anonymous"
    confession_text = update.message.text.strip()
    category = context.user_data.get('category', '🌟 Other')
    
    # Validation
    if len(confession_text) < 10:
        await update.message.reply_text(
            "❌ *Too short!* Please write at least 10 characters.\n\nTry again:",
            parse_mode='Markdown'
        )
        return WRITING_CONFESSION
        
    if len(confession_text) > 1000:
        await update.message.reply_text(
            "❌ *Too long!* Please keep it under 1000 characters.\n\nTry again:",
            parse_mode='Markdown'
        )
        return WRITING_CONFESSION
    
    # Save confession
    confession_id = db.save_confession(user_id, username, category, confession_text)
    if not confession_id:
        await update.message.reply_text(
            "❌ *Error submitting confession.* Please try again later.", 
            parse_mode='Markdown',
            reply_markup=get_main_keyboard()
        )
        context.user_data.clear()
        return ConversationHandler.END

    # Prepare admin notification
    admin_message = (
        f"🆕 *New Confession Pending Review* #{confession_id}\n\n"
        f"👤 *User:* {username} (ID: {user_id})\n"
        f"📂 *Category:* {category}\n"
        f"📝 *Confession:* {escape_markdown_text(confession_text)}\n\n"
        f"*Please review this confession:*"
    )
    
    # Send to all admins
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
        
        # Notify user
        await update.message.reply_text(
            "✅ *Confession Submitted Successfully!*\n\n"
            "Your confession has been sent for admin review. You'll be notified when it's approved.\n\n"
            "🔒 *Anonymous* • ⏰ *24h review* • 📢 *Channel post if approved*",
            parse_mode='Markdown',
            reply_markup=get_main_keyboard()
        )
        
    except Exception as e:
        logger.error(f"Failed to send admin messages: {e}")
        await update.message.reply_text(
            "⚠️ *Confession saved but admin notification failed.*\n\n"
            "Your confession is pending review. Admins will check it soon.",
            parse_mode='Markdown',
            reply_markup=get_main_keyboard()
        )
    
    context.user_data.clear()
    return ConversationHandler.END

async def cancel_confession(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the confession process."""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "❌ Confession cancelled.\n\nReturning to main menu.", 
        reply_markup=get_main_keyboard()
    )
    context.user_data.clear()
    return ConversationHandler.END

# --- Admin Functions ---
async def handle_admin_approval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle admin approval/rejection."""
    query = update.callback_query
    await query.answer()
    
    # Check admin permissions
    user_id_str = str(query.from_user.id)
    if user_id_str not in ADMIN_CHAT_IDS:
        await query.answer("❌ Only admins can perform this action.", show_alert=True)
        return
    
    action, confession_id_str = query.data.split('_', 1) 
    confession_id = int(confession_id_str)
    
    # Get confession data
    confession = db.get_confession(confession_id)
    if not confession:
        await query.edit_message_text(f"❌ Confession #{confession_id} not found.")
        return
    
    user_id = confession[1]
    category = confession[3]
    confession_text = confession[4]
    
    if action == 'approve':
        try:
            # Post to channel
            channel_text = format_channel_post(confession_id, category, confession_text)
            channel_message = await context.bot.send_message(
                chat_id=CHANNEL_ID,
                text=channel_text,
                reply_markup=get_channel_post_keyboard(confession_id), 
                parse_mode='Markdown'
            )
            
            # Update database
            db.update_confession_status(confession_id, 'approved', channel_message.message_id)
            
            # Notify user
            user_message = (
                "🎉 *Your Confession Has Been Approved!*\n\n"
                "Your confession is now live on the channel! "
                "People can view and comment on it.\n\n"
                "Thank you for sharing your thoughts! 💫"
            )
            status_text = "APPROVED"
            status_emoji = "✅"
            
            try:
                await context.bot.send_message(chat_id=user_id, text=user_message, parse_mode='Markdown')
            except Exception as e:
                logger.warning(f"Could not notify user {user_id}: {e}")
                
        except Exception as e:
            logger.error(f"Failed to post to channel: {e}")
            await query.answer("❌ Failed to post to channel. Check bot permissions.", show_alert=True)
            return
            
    elif action == 'reject':
        db.update_confession_status(confession_id, 'rejected')
        user_message = (
            "❌ *Confession Not Approved*\n\n"
            "Your confession did not meet our guidelines. "
            "You can submit another confession following our rules.\n\n"
            "Thank you for understanding."
        )
        status_text = "REJECTED"
        status_emoji = "❌"
        
        try:
            await context.bot.send_message(chat_id=user_id, text=user_message, parse_mode='Markdown')
        except Exception as e:
            logger.warning(f"Could not notify user {user_id}: {e}")

    # Update admin message
    await query.edit_message_text(
        f"{status_emoji} *Confession {status_text}!*\n\n"
        f"Confession #{confession_id} has been {status_text.lower()}.\n"
        f"The user has been notified.",
        parse_mode='Markdown'
    )

# --- Browsing Logic ---
async def browse_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Shows the browsing category menu."""
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
        await query.edit_message_text(
            browse_text,
            reply_markup=get_browse_keyboard(),
            parse_mode='Markdown'
        )
    return BROWSING_CONFESSIONS

async def start_browse_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Fetches and displays confessions."""
    query = update.callback_query
    await query.answer()
    
    browse_key = query.data.replace("browse_", "") 
    category_name = CATEGORY_MAP.get(browse_key, "Latest") 
    
    context.user_data['browse_category'] = category_name
    context.user_data['current_index'] = 0 
    
    # Load confessions
    confessions = db.get_approved_confessions(category=category_name if category_name != "Latest" else None, limit=20)
    context.user_data['confessions_list'] = confessions
    
    if not confessions:
        await query.edit_message_text(
            f"📭 *No confessions found for {category_name}*\n\n"
            "There are no approved confessions in this category yet.\n"
            "Check back later or browse other categories!",
            parse_mode='Markdown',
            reply_markup=get_browse_keyboard()
        )
        return BROWSING_CONFESSIONS
        
    await display_confession(update, context, via_callback=True)
    return BROWSING_CONFESSIONS

async def display_confession(update: Update, context: ContextTypes.DEFAULT_TYPE, via_callback=False):
    """Display confession with comment count."""
    confessions = context.user_data.get('confessions_list', [])
    current_index = context.user_data.get('current_index', 0)
    
    if not confessions: 
        if via_callback:
            await update.callback_query.edit_message_text(
                "❌ No confessions found in this category.",
                reply_markup=get_browse_keyboard()
            )
        else:
            await update.message.reply_text(
                "❌ No confessions found in this category.",
                reply_markup=get_browse_keyboard()
            )
        return 
    
    confession_data = confessions[current_index]
    confession_id = confession_data[0]
    
    # Use full format with comment count
    formatted_text = format_confession_full(confession_data, current_index + 1, len(confessions))
    
    if via_callback:
        try:
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=update.effective_message.message_id,
                text=formatted_text,
                reply_markup=get_confession_browse_keyboard(confession_id, len(confessions), current_index + 1),
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.warning(f"Error editing message during navigation: {e}")
    else:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=formatted_text,
            reply_markup=get_confession_browse_keyboard(confession_id, len(confessions), current_index + 1),
            parse_mode='Markdown'
        )

async def navigate_confession(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles 'next' and 'previous' buttons."""
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

# --- Commenting Logic ---
async def view_comments(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """View comments for a confession."""
    query = update.callback_query
    await query.answer()

    try:
        confession_id = int(query.data.split('_')[2])
    except (IndexError, ValueError):
        await query.edit_message_text(
            "❌ Error: Could not find that confession.", 
            reply_markup=get_main_keyboard()
        )
        return ConversationHandler.END

    comments_list = db.get_comments(confession_id)
    formatted_text = format_comments_list(confession_id, comments_list)

    await query.edit_message_text(
        text=formatted_text,
        parse_mode='Markdown',
        reply_markup=get_comments_management_keyboard(confession_id)
    )
    return BROWSING_CONFESSIONS

async def back_to_confession(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Returns to the confession view from comments."""
    query = update.callback_query
    await query.answer()
    
    try:
        confession_id = int(query.data.split('_')[3])
    except (IndexError, ValueError):
        await query.edit_message_text(
            "❌ Error: Could not find that confession.", 
            reply_markup=get_main_keyboard()
        )
        return ConversationHandler.END
    
    # Find confession in current list
    confessions = context.user_data.get('confessions_list', [])
    current_index = 0
    for i, confession_data in enumerate(confessions):
        if confession_data[0] == confession_id:
            current_index = i
            break
    
    context.user_data['current_index'] = current_index
    await display_confession(update, context, via_callback=True)
    return BROWSING_CONFESSIONS

async def start_comment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start commenting directly from confession view."""
    query = update.callback_query
    await query.answer()
    
    try:
        confession_id = int(query.data.split('_')[2])
    except (IndexError, ValueError):
        await query.edit_message_text(
            "❌ Error: Could not find that confession.", 
            reply_markup=get_main_keyboard()
        )
        return ConversationHandler.END
    
    context.user_data['commenting_on_id'] = confession_id
    
    await query.edit_message_text(
        "💭 *Add Your Comment*\n\n"
        "Please type your comment below:\n"
        "• 5-500 characters\n"
        "• Be respectful\n"
        "• Stay anonymous\n\n"
        "Your comment will be posted immediately.",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("❌ Cancel", callback_data="cancel_comment")
        ]])
    )
    return WRITING_COMMENT

async def receive_comment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Saves the user's comment text to the database."""
    comment_text = update.message.text.strip()
    user = update.effective_user
    confession_id = context.user_data.get('commenting_on_id')

    if not confession_id:
        await update.message.reply_text(
            "❌ Error: Could not find the confession.", 
            reply_markup=get_main_keyboard()
        )
        return ConversationHandler.END

    if len(comment_text) < 5:
        await update.message.reply_text(
            "❌ *Comment too short!* Please write at least 5 characters.\n\nTry again:", 
            parse_mode='Markdown'
        )
        return WRITING_COMMENT
        
    if len(comment_text) > 500:
        await update.message.reply_text(
            "❌ *Comment too long!* Please keep it under 500 characters.\n\nTry again:", 
            parse_mode='Markdown'
        )
        return WRITING_COMMENT

    try:
        db.save_comment(confession_id, user.id, user.first_name or "Anonymous", comment_text)
        
        # Get updated comment count
        comments_count = db.get_comments_count(confession_id)
        
        await update.message.reply_text(
            f"✅ *Comment Added Successfully!*\n\n"
            f"Your comment has been posted anonymously.\n"
            f"📊 Total comments: {comments_count}",
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Error saving comment: {e}")
        await update.message.reply_text(
            "❌ Error posting comment. Please try again later."
        )
    
    await update.message.reply_text(
        "Returning to main menu:", 
        reply_markup=get_main_keyboard()
    )
    context.user_data.clear()
    return ConversationHandler.END

async def cancel_comment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancels the comment writing process."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "❌ Comment cancelled.",
        reply_markup=get_main_keyboard()
    )
    context.user_data.clear()
    return ConversationHandler.END

# --- Main Application ---
def main():
    """Run the bot with enhanced keep-alive features."""
    # Startup message
    print("🤫 Confession Bot Starting...")
    print(f"✅ Bot Username: @{BOT_USERNAME}")
    print(f"✅ Channel ID: {CHANNEL_ID}")
    print(f"✅ Admin IDs: {ADMIN_CHAT_IDS}")
    print("✅ Database initialized")
    
    # Start Flask in background for Render health checks
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    print("✅ Health check server started")
    
    # Start keep-alive pinger
    keepalive_thread = threading.Thread(target=keep_alive_ping, daemon=True)
    keepalive_thread.start()
    print("✅ Keep-alive pinger started")
    
    # Create bot application
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
                CallbackQueryHandler(start_comment, pattern='^add_comment_'),  # Add comment
                CallbackQueryHandler(view_comments, pattern='^view_comments_'), # View comments
                CallbackQueryHandler(back_to_confession, pattern='^back_to_confession_') # Back to confession
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

    # Add handlers
    application.add_handler(conv_handler)
    application.add_handler(CallbackQueryHandler(handle_admin_approval, pattern='^approve_|^reject_'))

    # Update bot status
    global bot_status
    bot_status = "running"
    
    # Start bot polling with error recovery
    print("🔄 Starting bot polling...")
    try:
        application.run_polling(
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES,
            close_loop=False
        )
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
        print("🔄 Restarting bot in 10 seconds...")
        time.sleep(10)
        main()  # Auto-restart

if __name__ == '__main__':
    main()
