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

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))
ADMIN_IDS = [int(x.strip()) for x in os.getenv("ADMIN_IDS").split(",")]

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# --- Database setup ---
conn = sqlite3.connect("confessions.db", check_same_thread=False)
c = conn.cursor()
c.execute("""CREATE TABLE IF NOT EXISTS confessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                text TEXT,
                approved INTEGER DEFAULT 0,
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

# --- States ---
SUBMITTING, COMMENTING = range(2)

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
    text = update.message.text
    timestamp = datetime.now().isoformat()
    
    c.execute("INSERT INTO confessions (user_id, text, timestamp) VALUES (?, ?, ?)",
              (user_id, text, timestamp))
    conn.commit()
    
    confession_id = c.lastrowid
    
    # Notify Admin
    for admin in ADMIN_IDS:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("Approve ✅", callback_data=f"approve_{confession_id}")]
        ])
        await context.bot.send_message(
            chat_id=admin,
            text=f"New confession from user {user_id}:\n\n{text}",
            reply_markup=keyboard
        )
    
    await update.message.reply_text("Your confession has been submitted for approval.")
    return ConversationHandler.END

# --- Admin Approval ---
async def approve_confession(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    if not data.startswith("approve_"):
        return
    confession_id = int(data.split("_")[1])
    
    # Get confession
    c.execute("SELECT text FROM confessions WHERE id=?", (confession_id,))
    row = c.fetchone()
    if not row:
        await query.edit_message_text("Confession not found!")
        return
    
    text = row[0]
    
    # Post to channel
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("View Comments (0)", callback_data=f"viewcomments_{confession_id}_0"),
            InlineKeyboardButton("Add Comment", callback_data=f"addcomment_{confession_id}")
        ]
    ])
    
    channel_msg = await context.bot.send_message(
        chat_id=CHANNEL_ID,
        text=f"Confession:\n{text}",
        reply_markup=keyboard
    )
    
    # Update DB
    c.execute("UPDATE confessions SET approved=1, channel_message_id=? WHERE id=?",
              (channel_msg.message_id, confession_id))
    conn.commit()
    
    await query.edit_message_text("Confession approved and posted to channel ✅")

# --- View Comments ---
async def view_comments(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    if not data.startswith("viewcomments_"):
        return
    
    parts = data.split("_")
    confession_id = int(parts[1])
    
    c.execute("SELECT user_id, text, timestamp FROM comments WHERE confession_id=?", (confession_id,))
    rows = c.fetchall()
    
    if not rows:
        await query.edit_message_text("No comments yet.")
        return
    
    messages = [f"User {r[0]} at {r[2]}:\n{r[1]}" for r in rows]
    await query.edit_message_text("\n\n".join(messages))

# --- Add Comment ---
async def add_comment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    if not data.startswith("addcomment_"):
        return
    
    confession_id = int(data.split("_")[1])
    context.user_data["comment_confession_id"] = confession_id
    
    await query.message.reply_text("Please type your comment:")
    return COMMENTING

async def save_comment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text
    confession_id = context.user_data.get("comment_confession_id")
    timestamp = datetime.now().isoformat()
    
    c.execute("INSERT INTO comments (confession_id, user_id, text, timestamp) VALUES (?, ?, ?, ?)",
              (confession_id, user_id, text, timestamp))
    conn.commit()
    
    # Update button count on channel
    c.execute("SELECT COUNT(*) FROM comments WHERE confession_id=?", (confession_id,))
    count = c.fetchone()[0]
    
    c.execute("SELECT channel_message_id FROM confessions WHERE id=?", (confession_id,))
    channel_message_id = c.fetchone()[0]
    
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(f"View Comments ({count})", callback_data=f"viewcomments_{confession_id}_{count}"),
            InlineKeyboardButton("Add Comment", callback_data=f"addcomment_{confession_id}")
        ]
    ])
    
    await context.bot.edit_message_reply_markup(
        chat_id=CHANNEL_ID,
        message_id=channel_message_id,
        reply_markup=keyboard
    )
    
    await update.message.reply_text("Your comment has been added ✅")
    return ConversationHandler.END

# --- Cancel ---
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Operation canceled.")
    return ConversationHandler.END

# --- Main ---
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    
    confess_conv = ConversationHandler(
        entry_points=[CommandHandler("confess", confess)],
        states={
            SUBMITTING: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_confession)],
            COMMENTING: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_comment)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(confess_conv)
    app.add_handler(CallbackQueryHandler(approve_confession, pattern="^approve_"))
    app.add_handler(CallbackQueryHandler(view_comments, pattern="^viewcomments_"))
    app.add_handler(CallbackQueryHandler(add_comment, pattern="^addcomment_"))
    
    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
