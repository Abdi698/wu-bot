# File name: keyboards.py

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton

def get_main_keyboard():
    """Bottom navigation keyboard - Used for the /start command."""
    return ReplyKeyboardMarkup([
        [KeyboardButton("💌 Submit Confession")],
        [KeyboardButton("📖 Browse"), KeyboardButton("💬 Comments")],
        [KeyboardButton("❓ Help"), KeyboardButton("⚙️ Settings")]
    ], resize_keyboard=True, input_field_placeholder="Choose an option...")

def get_category_keyboard():
    """Category selection for confessions."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💕 Love", callback_data="cat_relationship"),
            InlineKeyboardButton("👥 Friends", callback_data="cat_friendship")
        ],
        [
            InlineKeyboardButton("🎓 Campus", callback_data="cat_campus"),
            InlineKeyboardButton("😊 General", callback_data="cat_general")
        ],
        [
            InlineKeyboardButton("😢 Vent", callback_data="cat_vent"),
            InlineKeyboardButton("🤫 Secret", callback_data="cat_secret")
        ],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
    ])

def get_browse_keyboard(show_back=True):
    """Browse confessions category selection."""
    buttons = [
        [InlineKeyboardButton("🆕 Latest", callback_data="browse_recent")],
        [
            InlineKeyboardButton("💕 Love", callback_data="browse_relationship"),
            InlineKeyboardButton("👥 Friends", callback_data="browse_friendship")
        ],
        [
            InlineKeyboardButton("🎓 Campus", callback_data="browse_campus"),
            InlineKeyboardButton("😊 General", callback_data="browse_general")
        ],
        [
            InlineKeyboardButton("😢 Vent", callback_data="browse_vent"),
            InlineKeyboardButton("🤫 Secret", callback_data="browse_secret")
        ]
    ]
    if show_back:
        buttons.append([InlineKeyboardButton("🔙 Back to Main", callback_data="back_main")])
    
    return InlineKeyboardMarkup(buttons)

def get_admin_keyboard(confession_id):
    """Admin approval buttons."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Approve", callback_data=f"approve_{confession_id}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"reject_{confession_id}")
        ],
        [InlineKeyboardButton("⏸️ Pending", callback_data=f"pending_{confession_id}")]
    ])

def get_channel_post_keyboard(confession_id: int, bot_username: str):
    """
    Creates an inline keyboard for the channel post using a deep link 
    to prompt users to comment in the bot's private chat.
    """
    # The deep link format is t.me/BOT_USERNAME?start=payload
    deep_link_url = f"https://t.me/{bot_username}?start=viewconf_{confession_id}"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 View & Comment", url=deep_link_url)]
    ])


def get_confession_navigation(confession_number, total_confessions, current_index):
    """Enhanced navigation for confession browsing."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💬 Add Comment", callback_data=f"add_comment_{confession_number}"),
            InlineKeyboardButton("📋 View Comments", callback_data=f"view_comments_{confession_number}")
        ],
        [
            InlineKeyboardButton("⬅️ Previous", callback_data=f"prev_{confession_number}"),
            InlineKeyboardButton(f"{current_index}/{total_confessions}", callback_data="page_info"),
            InlineKeyboardButton("Next ➡️", callback_data=f"next_{confession_number}")
        ],
        [InlineKeyboardButton("🔙 Back to Browse", callback_data="back_browse")]
    ])

def get_comments_management(confession_number, can_comment=True):
    """Comments management keyboard (used when viewing comments)."""
    buttons = []
    
    if can_comment:
        buttons.append([InlineKeyboardButton("✍️ Add Comment", callback_data=f"add_comment_{confession_number}")])
    
    buttons.extend([
        # This button takes you back to the confession text
        [InlineKeyboardButton("🔙 Back to Confession", callback_data="back_browse")]
    ])
    
    return InlineKeyboardMarkup(buttons)

def get_settings_keyboard():
    """Settings keyboard."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔔 Notifications", callback_data="settings_notifications")],
        [InlineKeyboardButton("🌙 Dark Mode", callback_data="settings_darkmode")],
        [InlineKeyboardButton("🔙 Back", callback_data="back_main")]
    ])