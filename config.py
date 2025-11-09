import os
from dotenv import load_dotenv

load_dotenv()

# Bot Configuration
BOT_TOKEN = os.getenv('8319779341:AAGFmurF3DECS8HBZ53Kj8qVJSxyHPZS-2c')
CHANNEL_ID = os.getenv('CHANNEL_ID', '-1002516867446')
ADMIN_IDS = [int(id.strip()) for id in os.getenv('ADMIN_IDS', '7411390360').split(',')]

# Bot Settings
MAX_CONFESSION_LENGTH = 1000
SUBMISSIONS_PER_HOUR = 3

# Categories
CATEGORIES = {
    "love": "💕 Love & Relationships",
    "friendship": "👥 Friendship", 
    "campus": "🎓 Campus Life",
    "general": "😊 General",
    "vent": "😢 Vent",
    "secret": "🤫 Secret"
}

# Messages
WELCOME_MESSAGE = """
🤫 <b>WU Confession Bot</b>

Welcome! Share your thoughts anonymously.

🔒 <b>100% Anonymous</b>
⚡ <b>Auto-Approval</b>
💬 <b>Real Comments</b>

Use buttons below to get started!
"""

HELP_MESSAGE = """
📖 <b>How to Use:</b>

• Click "Submit Confession" to share
• Choose a category
• Write your confession
• It posts automatically!

<b>Rules:</b>
• Be respectful
• No hate speech
• Keep it anonymous
• Max 1000 characters
"""