from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
import sqlite3
import logging

# --- Configuration (Best Practice: Use Environment Variables) ---
# NOTE: In a real deployment, these values should be loaded from os.environ
# For this example, we keep the original hardcoded values.
BOT_TOKEN = "8319779341:AAGFmurF3DECS8HBZ53Kj8qVJSxyHPZS-2c"
ADMIN_CHAT_ID = "411390360"
DATABASE_PATH = 'confessions.db'
PAGE_SIZE = 5 # Reduced size for better per-message review

logging.basicConfig(level=logging.INFO)

def is_admin(user_id: int) -> bool:
    """Helper function to check if the user is the admin."""
    return str(user_id) == ADMIN_CHAT_ID

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show admin statistics."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Access denied.")
        return

    try:
        # Use 'with' statement for safer database handling
        with sqlite3.connect(DATABASE_PATH) as conn:
            cursor = conn.cursor()

            # Get stats
            cursor.execute("SELECT COUNT(*) FROM confessions")
            total = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM confessions WHERE status = 'pending'")
            pending = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM confessions WHERE status = 'approved'")
            approved = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM confessions WHERE status = 'rejected'")
            rejected = cursor.fetchone()[0]

        stats_text = (
            f"📊 *Admin Statistics*\n\n"
            f"• Total Confessions: {total}\n"
            f"• ⏳ Pending: {pending}\n"
            f"• ✅ Approved: {approved}\n"
            f"• ❌ Rejected: {rejected}\n\n"
            f"Use /pending to view pending confessions (Page 1)."
        )

        await update.message.reply_text(stats_text, parse_mode='Markdown')

    except sqlite3.Error as e:
        logging.error(f"Database error in admin_stats: {e}")
        await update.message.reply_text("🚨 Error accessing database for statistics.")


async def view_pending(update: Update, context: ContextTypes.DEFAULT_TYPE, offset: int = 0) -> None:
    """View pending confessions with basic pagination (default offset 0)."""
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("❌ Access denied.")
        return

    try:
        with sqlite3.connect(DATABASE_PATH) as conn:
            cursor = conn.cursor()
            # Fetch PAGE_SIZE items, starting from the current offset
            # We fetch one extra item to check if there is a next page.
            cursor.execute(
                "SELECT id, category, confession_text FROM confessions WHERE status = 'pending' LIMIT ? OFFSET ?",
                (PAGE_SIZE + 1, offset)
            )
            pending_items = cursor.fetchall()

        if not pending_items and offset == 0:
            await update.message.reply_text("✅ No pending confessions!")
            return
        elif not pending_items and offset > 0:
            # Reached end of pending queue
            await update.effective_message.reply_text("✅ No more pending confessions.")
            return

        # Determine if there's a next page and slice the list to the actual page size
        has_next_page = len(pending_items) > PAGE_SIZE
        confessions_to_show = pending_items[:PAGE_SIZE]

        for confession in confessions_to_show:
            confession_id, category, text = confession
            message = (
                f"🆕 *Pending Confession* #{confession_id}\n\n"
                f"📂 *Category:* {category}\n"
                f"📝 *Text:* {text}\n\n"
                f"*Approve or reject:*"
            )

            # Define the approve/reject keyboard
            action_keyboard = [
                InlineKeyboardButton("✅ Approve", callback_data=f"approve_{confession_id}"),
                InlineKeyboardButton("❌ Reject", callback_data=f"reject_{confession_id}")
            ]
            reply_markup = InlineKeyboardMarkup([action_keyboard])

            await update.effective_message.reply_text(message, reply_markup=reply_markup, parse_mode='Markdown')
            
        # Add the pagination navigation keyboard after showing all confessions on the page
        nav_keyboard = []
        if offset > 0:
            # 'Back' button calculates previous offset
            prev_offset = max(0, offset - PAGE_SIZE)
            nav_keyboard.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"page_{prev_offset}"))
        
        if has_next_page:
            # 'Next' button calculates next offset
            next_offset = offset + PAGE_SIZE
            nav_keyboard.append(InlineKeyboardButton("Next ➡️", callback_data=f"page_{next_offset}"))

        if nav_keyboard:
            page_number = (offset // PAGE_SIZE) + 1
            await update.effective_message.reply_text(
                f"Page {page_number}. Confession Index {offset+1} to {offset + len(confessions_to_show)}.", 
                reply_markup=InlineKeyboardMarkup([nav_keyboard])
            )

        # Update the offset in user_data for the next call (optional, but good for state tracking)
        context.user_data['pending_offset'] = offset + len(confessions_to_show)

    except sqlite3.Error as e:
        logging.error(f"Database error in view_pending: {e}")
        await update.effective_message.reply_text("🚨 Error accessing pending confessions from database.")


async def handle_pagination_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles 'Next' and 'Previous' page button clicks."""
    query = update.callback_query
    await query.answer()
    
    # The callback data is in the format "page_{offset}"
    try:
        offset = int(query.data.split('_')[1])
        # Edit the previous message to show it's loading or simply delete/ignore it.
        # For simplicity, we just call view_pending with the new offset.
        await view_pending(update, context, offset=offset)
        
    except ValueError:
        await query.edit_message_text("❌ Invalid pagination data.")


def setup_admin_commands(application: Application):
    """Setup admin command handlers."""
    application.add_handler(CommandHandler("stats", admin_stats))
    # We pass offset=0 to view_pending when called directly via the command
    application.add_handler(CommandHandler("pending", lambda update, context: view_pending(update, context, offset=0)))
    
    # Handler for approve/reject and the new pagination buttons
    application.add_handler(CallbackQueryHandler(handle_pagination_callback, pattern=r'^page_\d+$'))
    # You will need a separate handler for approve/reject callbacks (e.g., r'^(approve|reject)_\d+$')
    # This example only implements the pagination callback handler.
    # application.add_handler(CallbackQueryHandler(handle_action_callback, pattern=r'^(approve|reject)_\d+$'))