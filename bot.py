import sqlite3
import os
import random
from telegram import (
    Update, ReplyKeyboardMarkup,
    InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler,
    MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)

def is_admin(user_id):
    return user_id in ADMIN_IDS

TOKEN = os.getenv("TOKEN")
ADMIN_IDS = [2097179248, 8164261864]

# ================= DATABASE =================
conn = sqlite3.connect("bot.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, name TEXT, balance INTEGER DEFAULT 0, upi TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS gmail_tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, email TEXT, password TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS withdrawals (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount INTEGER, upi TEXT, status TEXT)")
conn.commit()

# ================= MENU =================
def menu():
    return ReplyKeyboardMarkup([
        ["📧 Create Gmail", "💰 Balance"],
        ["🏧 Withdrawal", "🔗 Link UPI"],
        ["🆘 Help / Contact"]
    ], resize_keyboard=True)

# ================= START =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    cursor.execute("INSERT OR IGNORE INTO users VALUES (?, ?, 0, NULL)", (user.id, user.first_name))
    conn.commit()
    await update.message.reply_text("Welcome!", reply_markup=menu())

# ================= CREATE GMAIL =================
async def create_gmail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cursor.execute("SELECT id, name, email, password FROM gmail_tasks")
    tasks = cursor.fetchall()

    if not tasks:
        await update.message.reply_text("❌ No Gmail available")
        return

    task = random.choice(tasks)
    context.user_data["gmail"] = task

    task_id, name, email, password = task

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Done", callback_data="done")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
    ])

    await update.message.reply_text(
        f"""📧 *Register Gmail Account*

👤 Name: `{name}`
📧 Email: `{email}`
🔑 Password: `{password}`

💰 Reward: ₹17""",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

# ================= DONE =================
async def done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = query.from_user
    task_id, name, email, password = context.user_data.get("gmail")

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Approve", callback_data=f"gok_{task_id}_{user.id}")],
        [InlineKeyboardButton("❌ Reject", callback_data=f"gno_{task_id}_{user.id}")]
    ])

    await context.bot.send_message(
        ADMIN_ID,
        f"""📧 Gmail Completed

👤 User: {user.first_name}
🆔 {user.id}

👤 `{name}`
📧 `{email}`
🔑 `{password}`""",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

    await query.edit_message_text("⏳ Sent for approval")

# ================= CANCEL =================
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    await query.edit_message_text("❌ Cancelled")

# ================= ADMIN APPROVAL =================
async def admin_actions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    action, task_id, user_id = query.data.split("_")
    task_id = int(task_id)
    user_id = int(user_id)

    if action == "gok":
        cursor.execute("DELETE FROM gmail_tasks WHERE id=?", (task_id,))
        cursor.execute("UPDATE users SET balance = balance + 17 WHERE user_id=?", (user_id,))
        conn.commit()

        await context.bot.send_message(user_id, "✅ Approved ₹17 added")
        await query.edit_message_text("Approved")

    elif action == "gno":
        await context.bot.send_message(user_id, "❌ Rejected")
        await query.edit_message_text("Rejected")

# ================= BALANCE =================
async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cursor.execute("SELECT balance FROM users WHERE user_id=?", (update.effective_user.id,))
    bal = cursor.fetchone()[0]
    await update.message.reply_text(f"💰 ₹{bal}")

# ================= LINK UPI =================
async def link_upi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["mode"] = "upi"
    await update.message.reply_text("Send UPI ID")

# ================= WITHDRAW =================
async def withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    cursor.execute("SELECT balance, upi FROM users WHERE user_id=?", (user_id,))
    bal, upi = cursor.fetchone()

    if not upi:
        await update.message.reply_text("❌ Please link your UPI first")
        return

    if bal < 50:
        await update.message.reply_text("❌ Minimum withdrawal is ₹50")
        return

    cursor.execute("INSERT INTO withdrawals VALUES (NULL,?,?,?, 'pending')", (user_id, bal, upi))
    wid = cursor.lastrowid

    cursor.execute("UPDATE users SET balance=0 WHERE user_id=?", (user_id,))
    conn.commit()

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Approve", callback_data=f"wok_{wid}_{user_id}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"wno_{wid}_{user_id}")
        ]
    ])

    await context.bot.send_message(
        ADMIN_ID,
        f"💸 Withdraw ₹{bal}\nUPI: {upi}",
        reply_markup=keyboard
    )

    await update.message.reply_text("✅ Withdrawal request sent")

# ================= WITHDRAW ADMIN =================
async def withdraw_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    action, wid, user_id = query.data.split("_")
    wid = int(wid)
    user_id = int(user_id)

    cursor.execute("SELECT amount FROM withdrawals WHERE id=?", (wid,))
    amount = cursor.fetchone()[0]

    if action == "wok":
        cursor.execute("UPDATE withdrawals SET status='approved' WHERE id=?", (wid,))
        conn.commit()
        await context.bot.send_message(user_id, f"✅ Withdrawal Approved ₹{amount}")
        await query.edit_message_text("Approved")

    elif action == "wno":
        cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (amount, user_id))
        cursor.execute("UPDATE withdrawals SET status='rejected' WHERE id=?", (wid,))
        conn.commit()
        await context.bot.send_message(user_id, f"❌ Rejected ₹{amount} refunded")
        await query.edit_message_text("Rejected")

# ================= TEXT HANDLER =================
async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    mode = context.user_data.get("mode")

    if text == "📧 Create Gmail":
        await create_gmail(update, context)

    elif text == "💰 Balance":
        await balance(update, context)

    elif text == "🏧 Withdrawal":
        await withdraw(update, context)

    elif text == "🔗 Link UPI":
        await link_upi(update, context)

    elif text == "🆘 Help / Contact":
        await update.message.reply_text("Contact us: http://t.me/Contact_Us_Alkot_bot")

    elif mode == "upi":
        cursor.execute("UPDATE users SET upi=? WHERE user_id=?", (text, update.effective_user.id))
        conn.commit()
        context.user_data.clear()
        await update.message.reply_text("✅ UPI Saved")

# ================= RUN =================
app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))

app.add_handler(CallbackQueryHandler(done, pattern="done"))
app.add_handler(CallbackQueryHandler(cancel, pattern="cancel"))
app.add_handler(CallbackQueryHandler(admin_actions, pattern="gok_|gno_"))
app.add_handler(CallbackQueryHandler(withdraw_admin, pattern="wok_|wno_"))

app.run_polling()
