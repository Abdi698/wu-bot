# File name: keyboards.py

from typing import List
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton

# Category map from confession_bot.py is needed here for consistency
CATEGORY_MAP = {
    "relationship": "💕 Love", "friendship": "👥 Friends", 
    "campus": "🎓 Campus", "general": "😊 General", 
    "vent": "😢 Vent", "secret": "🤫 Secret", 
    "recent": "🆕 Latest"
}

def get_main_keyboard(channel_link: str) -> ReplyKeyboardMarkup:
    """Returns the main reply keyboard with core user functions."""
    keyboard = [
        [KeyboardButton("💌 Submit Confession"), KeyboardButton("📖 Browse")],
        [KeyboardButton("💬 Comments"), KeyboardButton("❓ Help")],
        [KeyboardButton("⚙️ Settings"), KeyboardButton(f"📣 Channel")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)

def get_category_keyboard() -> InlineKeyboardMarkup:
    """Returns the inline keyboard for selecting confession category."""
    keyboard = []
    keys = list(CATEGORY_MAP.keys())[:-1] # Exclude 'recent'
    
    # Create rows of two categories each
    for i in range(0, len(keys), 2):
        row = []
        key1 = keys[i]
        row.append(InlineKeyboardButton(CATEGORY_MAP[key1], callback_data=f"cat_{key1}"))
        if i + 1 < len(keys):
            key2 = keys[i+1]
            row.append(InlineKeyboardButton(CATEGORY_MAP[key2], callback_data=f"cat_{key2}"))
        keyboard.append(row)
        
    keyboard.append([InlineKeyboardButton("❌ Cancel Submission", callback_data="cancel")])
    
    return InlineKeyboardMarkup(keyboard)

def get_browse_keyboard(show_back: bool = False) -> InlineKeyboardMarkup:
    """Returns the inline keyboard for browsing categories."""
    keyboard = []
    # Create rows of two categories each (including 'recent')
    keys = list(CATEGORY_MAP.keys())
    
    for i in range(0, len(keys), 2):
        row = []
        key1 = keys[i]
        row.append(InlineKeyboardButton(CATEGORY_MAP[key1], callback_data=f"browse_{key1}"))
        if i + 1 < len(keys):
            key2 = keys[i+1]
            row.append(InlineKeyboardButton(CATEGORY_MAP[key2], callback_data=f"browse_{key2}"))
        keyboard.append(row)

    if show_back:
        keyboard.append([InlineKeyboardButton("🔙 Main Menu", callback_data="back_main")])
        
    return InlineKeyboardMarkup(keyboard)

def get_admin_keyboard(confession_id: int) -> InlineKeyboardMarkup:
    """Returns the inline keyboard for admin review (Approve/Reject)."""
    keyboard = [
        [
            InlineKeyboardButton("✅ Approve", callback_data=f"approve_{confession_id}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"reject_{confession_id}"),
        ],
        [
            InlineKeyboardButton("⏸️ Set to Pending", callback_data=f"pending_{confession_id}")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_channel_post_keyboard(confession_id: int, bot_username: str) -> InlineKeyboardMarkup:
    """Returns the inline keyboard added to the channel post."""
    # Use a deep link to start the bot and navigate to the confession details
    deep_link = f"https://t.me/{bot_username}?start=viewconf_{confession_id}"
    keyboard = [
        [InlineKeyboardButton("💬 View/Add Comment", url=deep_link)]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_confession_navigation(confession_number: int, total_confessions: int, current_index: int) -> InlineKeyboardMarkup:
    """Returns the navigation and comment buttons for browsing mode."""
    
    nav_buttons = []
    if current_index > 1:
        nav_buttons.append(InlineKeyboardButton("⏪ Prev", callback_data="prev"))
    if current_index < total_confessions:
        nav_buttons.append(InlineKeyboardButton("Next ⏩", callback_data="next"))

    keyboard = [
        nav_buttons,
        [
            InlineKeyboardButton("💬 View/Add Comment", callback_data=f"view_comments_{confession_number}"),
        ],
        [
             InlineKeyboardButton("🔙 Back to Browse Menu", callback_data="back_browse")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_comments_management(confession_id: int, can_comment: bool) -> InlineKeyboardMarkup:
    """Returns buttons for managing comments (add/back)."""
    keyboard = []
    if can_comment:
        keyboard.append([InlineKeyboardButton("➕ Add Anonymous Comment", callback_data=f"add_comment_{confession_id}")])
        
    keyboard.append([InlineKeyboardButton("🔙 Back to Confession", callback_data=f"back_conf_{confession_id}")])

    return InlineKeyboardMarkup(keyboard)

def get_settings_keyboard() -> InlineKeyboardMarkup:
    """Returns a placeholder settings keyboard (expandable later)."""
    keyboard = [
        # [InlineKeyboardButton("🔔 Toggle Notifications (WIP)", callback_data="settings_toggle_notify")],
        [InlineKeyboardButton("🔙 Main Menu", callback_data="back_main")]
    ]
    return InlineKeyboardMarkup(keyboard)
