import sqlite3
import os
from telegram import (
    Update, ReplyKeyboardMarkup,
    InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler,
    MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)

TOKEN = os.getenv("TOKEN")
ADMIN_ID = 2097179248  # change if needed

# ================= DATABASE =================
conn = sqlite3.connect("bot.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    name TEXT,
    balance INTEGER DEFAULT 0,
    upi TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS gmail_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    gmail TEXT,
    status TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS withdrawals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    amount INTEGER,
    upi TEXT,
    status TEXT
)
""")

conn.commit()

# ================= MENU =================
def menu():
    return ReplyKeyboardMarkup([
        ["📧 Create Gmail", "💰 Balance"],
        ["🏧 Withdrawal", "🔗 Link UPI"],
    ], resize_keyboard=True)

# ================= START =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    cursor.execute("INSERT OR IGNORE INTO users VALUES (?, ?, 0, NULL)",
                   (user.id, user.first_name))
    conn.commit()

    await update.message.reply_text("Welcome!", reply_markup=menu())

# ================= CREATE GMAIL =================
async def create_gmail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cursor.execute("SELECT id, gmail FROM gmail_tasks WHERE status='available' LIMIT 1")
    task = cursor.fetchone()

    if not task:
        await update.message.reply_text("No Gmail available.")
        return

    task_id, gmail = task

    context.user_data["gmail_task"] = task_id

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Done", callback_data="gmail_done")],
        [InlineKeyboardButton("❌ Cancel", callback_data="gmail_cancel")]
    ])

    await update.message.reply_text(
        f"📧 Gmail: {gmail}\n💰 Reward: ₹17\n\nClick Done after creating",
        reply_markup=keyboard
    )

# ================= DONE =================
async def gmail_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = query.from_user
    task_id = context.user_data.get("gmail_task")

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Approve", callback_data=f"gapprove_{task_id}_{user.id}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"greject_{task_id}_{user.id}")
        ]
    ])

    await context.bot.send_message(
        ADMIN_ID,
        f"📧 Gmail Done\n👤 {user.first_name}\nTask ID: {task_id}",
        reply_markup=keyboard
    )

    await query.edit_message_text("⏳ Sent for approval")

# ================= ADMIN APPROVE =================
async def admin_actions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data.split("_")
    action = data[0]
    task_id = int(data[1])
    user_id = int(data[2])

    if action == "gapprove":
        cursor.execute("UPDATE gmail_tasks SET status='used' WHERE id=?", (task_id,))
        cursor.execute("UPDATE users SET balance = balance + 17 WHERE user_id=?", (user_id,))
        conn.commit()

        await context.bot.send_message(user_id, "✅ Approved! ₹17 added")
        await query.edit_message_text("Approved")

    elif action == "greject":
        cursor.execute("UPDATE gmail_tasks SET status='available' WHERE id=?", (task_id,))
        conn.commit()

        await context.bot.send_message(user_id, "❌ Rejected")
        await query.edit_message_text("Rejected")

# ================= BALANCE =================
async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cursor.execute("SELECT balance, upi FROM users WHERE user_id=?", (update.effective_user.id,))
    bal, upi = cursor.fetchone()

    await update.message.reply_text(f"💰 ₹{bal}\nUPI: {upi}")

# ================= LINK UPI =================
async def link_upi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Send UPI ID")
    context.user_data["upi"] = True

async def save_upi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("upi"):
        cursor.execute("UPDATE users SET upi=? WHERE user_id=?",
                       (update.message.text, update.effective_user.id))
        conn.commit()
        context.user_data["upi"] = False
        await update.message.reply_text("UPI Saved")

# ================= WITHDRAW =================
async def withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    cursor.execute("SELECT balance, upi FROM users WHERE user_id=?", (user_id,))
    bal, upi = cursor.fetchone()

    if bal < 50:
        await update.message.reply_text("Min ₹50 required")
        return

    cursor.execute("INSERT INTO withdrawals VALUES (NULL, ?, ?, ?, 'pending')",
                   (user_id, bal, upi))
    wid = cursor.lastrowid

    cursor.execute("UPDATE users SET balance=0 WHERE user_id=?", (user_id,))
    conn.commit()

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Approve", callback_data=f"wapprove_{wid}_{user_id}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"wreject_{wid}_{user_id}")
        ]
    ])

    await context.bot.send_message(
        ADMIN_ID,
        f"💸 Withdraw ₹{bal}\nUPI: {upi}",
        reply_markup=keyboard
    )

    await update.message.reply_text("Request sent")

# ================= WITHDRAW ADMIN =================
async def withdraw_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data.split("_")
    action = data[0]
    wid = int(data[1])
    user_id = int(data[2])

    cursor.execute("SELECT amount FROM withdrawals WHERE id=?", (wid,))
    amount = cursor.fetchone()[0]

    if action == "wapprove":
        cursor.execute("UPDATE withdrawals SET status='approved' WHERE id=?", (wid,))
        conn.commit()
        await context.bot.send_message(user_id, "✅ Withdrawal Approved")

    elif action == "wreject":
        cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (amount, user_id))
        cursor.execute("UPDATE withdrawals SET status='rejected' WHERE id=?", (wid,))
        conn.commit()
        await context.bot.send_message(user_id, "❌ Rejected, refunded")

    await query.edit_message_text("Done")

# ================= ADMIN ADD GMAIL =================
async def add_gmail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    await update.message.reply_text("Send Gmail list (one per line)")
    context.user_data["add_gmail"] = True

async def save_gmail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("add_gmail"):
        lines = update.message.text.split("\n")

        for g in lines:
            cursor.execute("INSERT INTO gmail_tasks (gmail, status) VALUES (?, 'available')", (g.strip(),))

        conn.commit()
        context.user_data["add_gmail"] = False
        await update.message.reply_text("✅ Gmail Added")

# ================= HANDLER =================
async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if text == "📧 Create Gmail":
        await create_gmail(update, context)

    elif text == "💰 Balance":
        await balance(update, context)

    elif text == "🏧 Withdrawal":
        await withdraw(update, context)

    elif text == "🔗 Link UPI":
        await link_upi(update, context)

    else:
        await save_upi(update, context)
        await save_gmail(update, context)

# ================= RUN =================
app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("addgmail", add_gmail))

app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))

app.add_handler(CallbackQueryHandler(gmail_done, pattern="gmail_done"))
app.add_handler(CallbackQueryHandler(admin_actions, pattern="gapprove_|greject_"))
app.add_handler(CallbackQueryHandler(withdraw_admin, pattern="wapprove_|wreject_"))

app.run_polling()
