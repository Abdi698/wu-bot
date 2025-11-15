# File name: confession_bot.py

import sys
import os
import atexit
import asyncio

# Enhanced error handling and cleanup
def setup_environment():
    """Setup environment with proper error handling"""
    print("🚀 Initializing Confession Bot Environment...")
    
    # Prevent multiple instances
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

    # Check for existing instance with better error handling
    try:
        if os.path.exists(lock_file_path):
            with open(lock_file_path, 'r') as f:
                pid = f.read().strip()
            try:
                os.kill(int(pid), 0)
                print("❌ Another bot instance is already running. Exiting.")
                sys.exit(0)
            except (ProcessLookupError, ValueError):
                os.remove(lock_file_path)
                print("🔄 Removed stale lock file")
        
        with open(lock_file_path, 'w') as f:
            f.write(str(os.getpid()))
            
    except Exception as e:
        print(f"⚠️ Lock file check warning: {e}")
    
    print("✅ Environment setup completed")

# Run environment setup
setup_environment()

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

# --- Enhanced Keyboard System with Fallbacks ---
class KeyboardManager:
    """Manages all bot keyboards with comprehensive error handling"""
    
    @staticmethod
    def get_main_keyboard(channel_link=None):
        """Main menu keyboard"""
        try:
            buttons = [
                [InlineKeyboardButton("💌 Submit Confession", callback_data="start_confess")],
                [InlineKeyboardButton("📖 Browse Confessions", callback_data="browse_menu")],
                [InlineKeyboardButton("💬 Comments", callback_data="comments_info")],
                [InlineKeyboardButton("❓ Help", callback_data="help_info")]
            ]
            if channel_link:
                buttons.append([InlineKeyboardButton("📢 View Channel", url=channel_link)])
            return InlineKeyboardMarkup(buttons)
        except Exception as e:
            logging.error(f"Keyboard error in main keyboard: {e}")
            return InlineKeyboardMarkup([[InlineKeyboardButton("Menu", callback_data="main_menu")]])
    
    @staticmethod
    def get_category_keyboard():
        """Category selection keyboard"""
        try:
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
        except Exception as e:
            logging.error(f"Keyboard error in category keyboard: {e}")
            return InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="main_menu")]])
    
    @staticmethod
    def get_browse_keyboard(show_back=False):
        """Browse categories keyboard"""
        try:
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
        except Exception as e:
            logging.error(f"Keyboard error in browse keyboard: {e}")
            return InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="main_menu")]])
    
    @staticmethod
    def get_confession_navigation(confession_id, total, index):
        """Confession navigation keyboard"""
        try:
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
            
            return InlineKeyboardMarkup([*nav_row, *action_buttons]) if nav_row else InlineKeyboardMarkup(action_buttons)
        except Exception as e:
            logging.error(f"Keyboard error in confession navigation: {e}")
            return InlineKeyboardMarkup([[InlineKeyboardButton("Main Menu", callback_data="main_menu")]])
    
    @staticmethod
    def get_admin_keyboard(confession_id):
        """Admin actions keyboard"""
        try:
            return InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ Approve", callback_data=f"approve_{confession_id}"),
                    InlineKeyboardButton("❌ Reject", callback_data=f"reject_{confession_id}")
                ],
                [InlineKeyboardButton("⏸️ Set Pending", callback_data=f"pending_{confession_id}")]
            ])
        except Exception as e:
            logging.error(f"Keyboard error in admin keyboard: {e}")
            return InlineKeyboardMarkup([[InlineKeyboardButton("OK", callback_data="ok")]])
    
    @staticmethod
    def get_comments_management(confession_id):
        """Comments management keyboard"""
        try:
            return InlineKeyboardMarkup([
                [InlineKeyboardButton("💬 Add Comment", callback_data=f"add_comment_{confession_id}")],
                [InlineKeyboardButton("⬅️ Back to Confession", callback_data=f"back_browse_{confession_id}")],
                [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
            ])
        except Exception as e:
            logging.error(f"Keyboard error in comments management: {e}")
            return InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data=f"back_browse_{confession_id}")]])
    
    @staticmethod
    def get_channel_post_keyboard(confession_id, username):
        """Channel post keyboard with proper URL formatting"""
        try:
            clean_username = username.replace('@', '').strip()
            url = f"https://t.me/{clean_username}?start=viewconf_{confession_id}"
            print(f"🔗 Generated channel button URL: {url}")
            return InlineKeyboardMarkup([[
                InlineKeyboardButton("💬 Comment & Discuss", url=url)
            ]])
        except Exception as e:
            logging.error(f"Keyboard error in channel post: {e}")
            return InlineKeyboardMarkup([[InlineKeyboardButton("Open Bot", url=f"https://t.me/{username}")]])
    
    @staticmethod
    def get_settings_keyboard():
        """Settings keyboard"""
        try:
            return InlineKeyboardMarkup([
                [InlineKeyboardButton("🔔 Notifications", callback_data="settings_notifications")],
                [InlineKeyboardButton("🌙 Dark Mode", callback_data="settings_darkmode")],
                [InlineKeyboardButton("⬅️ Back", callback_data="back_main")]
            ])
        except Exception as e:
            logging.error(f"Keyboard error in settings keyboard: {e}")
            return InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="back_main")]])

# Initialize keyboard manager
keyboards = KeyboardManager()

# Load environment variables with validation
load_dotenv()

class Config:
    """Configuration manager with validation"""
    
    @staticmethod
    def validate_environment():
        """Validate all required environment variables"""
        required_vars = {
            'BOT_TOKEN': os.getenv("BOT_TOKEN"),
            'ADMIN_CHAT_ID': os.getenv("ADMIN_CHAT_ID") or os.getenv("ADMIN_IDS"),
            'CHANNEL_ID': os.getenv("CHANNEL_ID"),
            'BOT_USERNAME': os.getenv("BOT_USERNAME")
        }
        
        errors = []
        for var_name, var_value in required_vars.items():
            if not var_value:
                errors.append(f"❌ {var_name} is missing")
            else:
                print(f"✅ {var_name}: Found")
        
        # Validate CHANNEL_ID format
        try:
            channel_id = int(required_vars['CHANNEL_ID'])
            if channel_id >= 0:
                errors.append("❌ CHANNEL_ID must be negative (channel ID)")
        except (TypeError, ValueError):
            errors.append("❌ CHANNEL_ID must be a valid integer")
        
        if errors:
            print("\n".join(errors))
            sys.exit(1)
        
        return {
            'BOT_TOKEN': required_vars['BOT_TOKEN'],
            'ADMIN_CHAT_ID': required_vars['ADMIN_CHAT_ID'].split(',')[0].strip(),
            'CHANNEL_ID': int(required_vars['CHANNEL_ID']),
            'BOT_USERNAME': required_vars['BOT_USERNAME'].replace('@', '').strip()
        }

# Validate and load configuration
config = Config.validate_environment()
BOT_TOKEN = config['BOT_TOKEN']
ADMIN_CHAT_ID = config['ADMIN_CHAT_ID']
CHANNEL_ID = config['CHANNEL_ID']
BOT_USERNAME = config['BOT_USERNAME']

# Enhanced logging setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('bot_errors.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# --- Constants ---
HELP_TEXT = """
❓ *Bot Help & Guidelines*

*💌 Submit Confession*: Share your anonymous confession (10-1000 chars)
*📖 Browse*: Read approved confessions and comments  
*💬 Comments*: Discuss confessions (via Browse feature)
*❓ Help*: View this guide

🔒 *Your anonymity is guaranteed*
All submissions are reviewed before posting.
"""

SELECTING_CATEGORY, WRITING_CONFESSION, BROWSING_CONFESSIONS, WRITING_COMMENT = range(4)

CATEGORY_MAP = {
    "relationship": "Love & Relationships", "friendship": "Friendship", 
    "campus": "Academic Stress", "general": "Other", 
    "vent": "Fear & Anxiety", "secret": "Regrets", "recent": "Recent"
}

# --- Enhanced Database Management ---
class DatabaseManager:
    """Enhanced database manager with comprehensive error handling"""
    
    def __init__(self):
        self.db_path = 'confessions.db'
        self.init_database()
    
    def get_connection(self):
        """Get database connection with error handling"""
        try:
            return sqlite3.connect(self.db_path, check_same_thread=False, timeout=30)
        except Exception as e:
            logger.error(f"❌ Database connection error: {e}")
            raise
    
    def init_database(self):
        """Initialize database with enhanced error handling"""
        conn = None
        try:
            conn = self.get_connection()
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
                    channel_message_id INTEGER,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
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
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (confession_id) REFERENCES confessions(id) ON DELETE CASCADE
                )
            ''')
            
            # Create indexes for better performance
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_confessions_status ON confessions(status)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_confessions_category ON confessions(category)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_comments_confession_id ON comments(confession_id)')
            
            conn.commit()
            print("✅ Database initialized successfully with indexes")
        except Exception as e:
            logger.error(f"❌ Database initialization error: {e}")
        finally:
            if conn:
                conn.close()

    def execute_query(self, query, params=(), fetch=False):
        """Generic query executor with error handling"""
        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute(query, params)
            
            if fetch:
                result = cursor.fetchall()
            else:
                conn.commit()
                result = cursor.lastrowid
            
            return result
        except Exception as e:
            logger.error(f"❌ Database query error: {e}")
            if conn:
                conn.rollback()
            return None
        finally:
            if conn:
                conn.close()

    def save_confession(self, user_id, username, category, confession_text, channel_message_id=None):
        """Save confession with enhanced error handling"""
        try:
            confession_id = self.execute_query(
                '''INSERT INTO confessions (user_id, username, category, confession_text, channel_message_id)
                   VALUES (?, ?, ?, ?, ?)''',
                (user_id, username, category, confession_text, channel_message_id)
            )
            return confession_id
        except Exception as e:
            logger.error(f"❌ Error saving confession: {e}")
            return None

    def update_confession_status(self, confession_id, status, channel_message_id=None):
        """Update confession status"""
        try:
            if channel_message_id is not None:
                self.execute_query(
                    'UPDATE confessions SET status = ?, channel_message_id = ? WHERE id = ?',
                    (status, channel_message_id, confession_id)
                )
            else:
                self.execute_query(
                    'UPDATE confessions SET status = ? WHERE id = ?',
                    (status, confession_id)
                )
            return True
        except Exception as e:
            logger.error(f"❌ Error updating confession: {e}")
            return False

    def get_confession(self, confession_id):
        """Get confession by ID"""
        try:
            result = self.execute_query(
                'SELECT * FROM confessions WHERE id = ?',
                (confession_id,),
                fetch=True
            )
            return result[0] if result else None
        except Exception as e:
            logger.error(f"❌ Error getting confession: {e}")
            return None
    
    def get_approved_confessions(self, category=None, limit=50):
        """Get approved confessions with pagination"""
        try:
            if category and category != "Recent":
                return self.execute_query(
                    '''SELECT id, confession_text, category, timestamp 
                       FROM confessions 
                       WHERE status = "approved" AND category = ? 
                       ORDER BY id DESC LIMIT ?''',
                    (category, limit),
                    fetch=True
                )
            else:
                return self.execute_query(
                    '''SELECT id, confession_text, category, timestamp 
                       FROM confessions 
                       WHERE status = "approved" 
                       ORDER BY id DESC LIMIT ?''',
                    (limit,),
                    fetch=True
                )
        except Exception as e:
            logger.error(f"❌ Error fetching approved confessions: {e}")
            return []

    def save_comment(self, confession_id, user_id, username, comment_text):
        """Save comment with validation"""
        try:
            comment_id = self.execute_query(
                '''INSERT INTO comments (confession_id, user_id, username, comment_text)
                   VALUES (?, ?, ?, ?)''',
                (confession_id, user_id, username, comment_text)
            )
            return comment_id
        except Exception as e:
            logger.error(f"❌ Error saving comment: {e}")
            return None

    def get_comments(self, confession_id):
        """Get comments for confession"""
        try:
            return self.execute_query(
                'SELECT username, comment_text, timestamp FROM comments WHERE confession_id = ? ORDER BY timestamp ASC',
                (confession_id,),
                fetch=True
            )
        except Exception as e:
            logger.error(f"❌ Error fetching comments: {e}")
            return []

    def get_comments_count(self, confession_id):
        """Get comment count"""
        try:
            result = self.execute_query(
                'SELECT COUNT(*) FROM comments WHERE confession_id = ?',
                (confession_id,),
                fetch=True
            )
            return result[0][0] if result else 0
        except Exception as e:
            logger.error(f"❌ Error counting comments: {e}")
            return 0

# Initialize database
db = DatabaseManager()

# --- Enhanced Helper Functions ---
class FormattingUtils:
    """Utility class for formatting messages"""
    
    @staticmethod
    def format_channel_post(confession_id, category, confession_text):
        """Format channel post with error handling"""
        try:
            comments_count = db.get_comments_count(confession_id)
            category_tag = f"#{category.replace(' ', '_').replace('&', 'and')}" 
            
            return (
                f"*Confession #{confession_id}*\n\n"
                f"{confession_text}\n\n"
                f"Category: {category_tag}\n"
                f"Comments: 💬 {comments_count}"
            )
        except Exception as e:
            logger.error(f"Error formatting channel post: {e}")
            return f"Confession #{confession_id}\n\n{confession_text}"
    
    @staticmethod
    def format_browsing_confession(confession_data, index, total_confessions):
        """Format confession for browsing"""
        try:
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
        except Exception as e:
            logger.error(f"Error formatting browsing confession: {e}")
            return "Error loading confession. Please try again."
    
    @staticmethod
    def format_comments_list(confession_id, comments_list):
        """Format comments list"""
        try:
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

                comment_blocks.append(f"👤 *{anon_name}* ({time_str}):\n» {text}\n")
                    
            return header + "\n---\n".join(comment_blocks)
        except Exception as e:
            logger.error(f"Error formatting comments list: {e}")
            return "Error loading comments. Please try again."

formatter = FormattingUtils()

# --- Enhanced Handler Functions ---
class BotHandlers:
    """Enhanced bot handlers with comprehensive error handling"""
    
    @staticmethod
    async def safe_send_message(chat_id, text, context, **kwargs):
        """Safely send message with error handling"""
        try:
            return await context.bot.send_message(chat_id=chat_id, text=text, **kwargs)
        except Exception as e:
            logger.error(f"Error sending message to {chat_id}: {e}")
            return None
    
    @staticmethod
    async def safe_edit_message(text, update, context, **kwargs):
        """Safely edit message with error handling"""
        try:
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=update.effective_message.message_id,
                text=text,
                **kwargs
            )
            return True
        except Exception as e:
            logger.warning(f"Error editing message: {e}")
            return False
    
    @staticmethod
    async def handle_deep_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle deep links with enhanced error handling"""
        if not context.args:
            return await BotHandlers.start(update, context)
        
        try:
            payload = context.args[0]
            
            if not payload.startswith('viewconf_'):
                return await BotHandlers.start(update, context)
            
            confession_id = int(payload.split('_')[1])
            confession_full = db.get_confession(confession_id)
            
            if not confession_full or confession_full[6] != 'approved':
                await BotHandlers.safe_send_message(
                    update.effective_chat.id,
                    "❌ This confession is not available or not approved yet.",
                    context,
                    reply_markup=keyboards.get_main_keyboard(f"https://t.me/{BOT_USERNAME}")
                )
                return ConversationHandler.END

            confession_data = (confession_full[0], confession_full[4], confession_full[3], confession_full[5])
            context.user_data['confessions_list'] = [confession_data]
            context.user_data['current_index'] = 0 
            context.user_data['from_deep_link'] = True
            
            await BotHandlers.safe_send_message(
                update.effective_chat.id,
                "🔗 *You were linked to this confession from the channel*\n\nYou can read comments or add your own below:",
                context,
                parse_mode='Markdown'
            )

            await BotHandlers.display_confession(update, context, via_callback=False)
            return BROWSING_CONFESSIONS
            
        except Exception as e:
            logger.error(f"Error handling deep link: {e}")
            await BotHandlers.safe_send_message(
                update.effective_chat.id,
                "❌ Invalid confession link.",
                context,
                reply_markup=keyboards.get_main_keyboard(f"https://t.me/{BOT_USERNAME}")
            )
            return ConversationHandler.END
    
    @staticmethod
    async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start command handler"""
        try:
            if not context.args:
                context.user_data.clear()

            if context.args:
                return await BotHandlers.handle_deep_link(update, context)

            welcome_text = (
                "🤫 *Confession Bot*\n\n"
                "Welcome! Share your thoughts anonymously or explore what others have shared."
            )
            
            await BotHandlers.safe_send_message(
                update.effective_chat.id,
                welcome_text,
                context,
                reply_markup=keyboards.get_main_keyboard(f"https://t.me/{BOT_USERNAME}"),
                parse_mode='Markdown'
            )
            return ConversationHandler.END
        except Exception as e:
            logger.error(f"Error in start handler: {e}")
            return ConversationHandler.END
    
    @staticmethod
    async def handle_text_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle text button clicks"""
        try:
            text = update.message.text
            
            if text == "💌 Submit Confession":
                await BotHandlers.safe_send_message(
                    update.effective_chat.id,
                    "Click the button below to start your confession:",
                    context,
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📝 Start Confession", callback_data="start_confess")]])
                )
                return ConversationHandler.END
                
            elif text == "📖 Browse":
                return await BotHandlers.browse_menu(update, context)
                
            elif text == "💬 Comments":
                await BotHandlers.safe_send_message(
                    update.effective_chat.id,
                    "ℹ️ *How to Comment*\n\nTo read or add comments, use **📖 Browse**, find a confession, then use 'View Comments' or 'Add Comment' buttons.",
                    context,
                    parse_mode='Markdown',
                    reply_markup=keyboards.get_main_keyboard(f"https://t.me/{BOT_USERNAME}")
                )
                return ConversationHandler.END
                
            elif text == "❓ Help":
                await BotHandlers.safe_send_message(
                    update.effective_chat.id,
                    HELP_TEXT,
                    context,
                    parse_mode='Markdown',
                    reply_markup=keyboards.get_main_keyboard(f"https://t.me/{BOT_USERNAME}")
                )
                return ConversationHandler.END
                
            elif text == "⚙️ Settings":
                await BotHandlers.safe_send_message(
                    update.effective_chat.id,
                    "⚙️ *Settings Menu*\n\nThese features are coming soon!",
                    context,
                    parse_mode='Markdown',
                    reply_markup=keyboards.get_settings_keyboard()
                )
                return ConversationHandler.END
            
            return ConversationHandler.END
        except Exception as e:
            logger.error(f"Error in text button handler: {e}")
            return ConversationHandler.END
    
    @staticmethod
    async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Return to main menu"""
        try:
            query = update.callback_query
            await query.answer()
            
            welcome_text = "🤫 *Confession Bot*\n\nWelcome back! Use the keyboard below."
            
            await BotHandlers.safe_edit_message(
                welcome_text,
                update,
                context,
                parse_mode='Markdown',
                reply_markup=keyboards.get_main_keyboard(f"https://t.me/{BOT_USERNAME}")
            )
            return ConversationHandler.END
        except Exception as e:
            logger.error(f"Error in main menu: {e}")
            return ConversationHandler.END
    
    # Continue with other handler methods...
    # [Include all other handler methods with enhanced error handling]

# Initialize bot handlers
handlers = BotHandlers()

# --- Main Application Setup ---
def create_application():
    """Create and configure the bot application"""
    try:
        application = Application.builder().token(BOT_TOKEN).build()
        print("✅ Bot application created successfully")
        return application
    except Exception as e:
        logger.error(f"❌ Failed to create bot application: {e}")
        sys.exit(1)

def setup_handlers(application):
    """Setup all bot handlers"""
    try:
        # Conversation Handler for Submission
        submission_handler = ConversationHandler(
            entry_points=[CallbackQueryHandler(handlers.start_confession, pattern='^start_confess$')],
            states={
                SELECTING_CATEGORY: [
                    CallbackQueryHandler(handlers.select_category, pattern='^cat_'),
                    CallbackQueryHandler(handlers.cancel_confession, pattern='^cancel_confess$')
                ],
                WRITING_CONFESSION: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.receive_confession),
                    CallbackQueryHandler(handlers.cancel_confession, pattern='^cancel_confess$')
                ]
            },
            fallbacks=[
                CommandHandler('start', handlers.start),
                MessageHandler(filters.TEXT | filters.COMMAND, handlers.fallback_handler)
            ],
            per_message=False
        )
        application.add_handler(submission_handler)

        # Conversation Handler for Browsing and Comments
        browsing_handler = ConversationHandler(
            entry_points=[
                MessageHandler(filters.Regex('^📖 Browse$'), handlers.browse_menu),
                CallbackQueryHandler(handlers.browse_menu, pattern='^browse_menu$'),
            ],
            states={
                BROWSING_CONFESSIONS: [
                    CallbackQueryHandler(handlers.start_browse_category, pattern='^browse_'),
                    CallbackQueryHandler(handlers.navigate_confession, pattern='^(next|prev)_'),
                    CallbackQueryHandler(handlers.view_comments, pattern='^view_comments_'),
                    CallbackQueryHandler(handlers.start_add_comment, pattern='^add_comment_'),
                    CallbackQueryHandler(handlers.back_to_browse, pattern='^back_browse_'),
                    CallbackQueryHandler(handlers.cancel_comment, pattern='^cancel_comment_'),
                    CallbackQueryHandler(handlers.main_menu, pattern='^back_browse_menu$'),
                ],
                WRITING_COMMENT: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.receive_comment),
                    CallbackQueryHandler(handlers.cancel_comment, pattern='^cancel_comment_'),
                ]
            },
            fallbacks=[
                CommandHandler('start', handlers.start),
                CallbackQueryHandler(handlers.main_menu, pattern='^main_menu$'),
                MessageHandler(filters.TEXT | filters.COMMAND, handlers.fallback_handler)
            ],
            per_message=False
        )
        application.add_handler(browsing_handler)
        
        # Other handlers
        application.add_handler(CallbackQueryHandler(handlers.handle_admin_approval, pattern='^(approve|reject|pending)_'))
        application.add_handler(CallbackQueryHandler(handlers.show_help_info, pattern='^help_info$'))
        application.add_handler(CallbackQueryHandler(handlers.show_comments_info, pattern='^comments_info$'))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.handle_text_button))
        application.add_handler(CommandHandler("start", handlers.start))
        application.add_handler(CommandHandler("help", handlers.start))
        application.add_handler(CallbackQueryHandler(handlers.handle_settings_callback, pattern='^settings_'))
        application.add_handler(CallbackQueryHandler(handlers.main_menu, pattern='^main_menu$|^back_main$'))
        application.add_error_handler(handlers.error_handler)
        
        print("✅ All handlers setup successfully")
        return True
    except Exception as e:
        logger.error(f"❌ Failed to setup handlers: {e}")
        return False

def main():
    """Main application entry point with comprehensive error handling"""
    print("🤖 Starting Enhanced Confession Bot...")
    
    try:
        # Create application
        application = create_application()
        
        # Setup handlers
        if not setup_handlers(application):
            raise Exception("Failed to setup handlers")
        
        # Determine run mode
        RENDER_EXTERNAL_URL = os.getenv('RENDER_EXTERNAL_URL')
        
        if RENDER_EXTERNAL_URL:
            # Production: Use webhooks
            PORT = int(os.getenv('PORT', 10000))
            webhook_url = f"{RENDER_EXTERNAL_URL}/{BOT_TOKEN}"
            
            print(f"🚀 Production mode: Starting webhook on port {PORT}")
            print(f"🌐 Webhook URL: {webhook_url}")
            
            try:
                # Set webhook first
                async def set_webhook():
                    try:
                        await application.bot.set_webhook(webhook_url)
                        print("✅ Webhook set successfully")
                    except Exception as e:
                        print(f"❌ Failed to set webhook: {e}")
                        raise
                
                # Run webhook setup
                asyncio.run(set_webhook())
                
                # Start webhook
                application.run_webhook(
                    listen="0.0.0.0",
                    port=PORT,
                    webhook_url=webhook_url,
                    secret_token='WEBHOOK_SECRET'
                )
                
            except Exception as e:
                print(f"❌ Webhook failed: {e}")
                print("🔄 Falling back to polling...")
                application.run_polling()
        else:
            # Development: Use polling
            print("🔧 Development mode: Starting with polling...")
            application.run_polling()
            
    except Exception as e:
        logger.error(f"❌ Fatal error in main: {e}")
        print(f"❌ Bot crashed: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
