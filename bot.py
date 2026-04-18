import sqlite3
import os
import random
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

TOKEN = os.getenv("TOKEN")

# ✅ MULTI ADMINS
ADMIN_IDS = [2097179248, 8164261864]

def is_admin(user_id):
    return user_id in ADMIN_IDS

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
    await update.message.reply_text("Welcome! In this BOT you can earn by creating G-Mails. For Guidence @Contact_Us_Alkot_bot ", reply_markup=menu())

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

    for admin in ADMIN_IDS:
        await context.bot.send_message(
            admin,
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

# ================= ADMIN GMAIL APPROVAL =================
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
        await update.message.reply_text("❌ Please link UPI first")
        return

    if bal < 50:
        await update.message.reply_text("❌ Minimum ₹50 required")
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

    for admin in ADMIN_IDS:
        await context.bot.send_message(
            admin,
            f"💸 Withdraw ₹{bal}\nUPI: {upi}",
            reply_markup=keyboard
        )

    await update.message.reply_text("✅ Request sent")

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

# ================= ADMIN PANEL =================
async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add Gmail", callback_data="admin_add")],
        [InlineKeyboardButton("💰 Add Balance", callback_data="admin_addbal")],
        [InlineKeyboardButton("➖ Deduct Balance", callback_data="admin_cutbal")],
        [InlineKeyboardButton("📊 Stats", callback_data="admin_stats")],
        [InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast")]
    ])

    await update.message.reply_text("⚙️ ADMIN PANEL", reply_markup=keyboard)

# ================= ADMIN BUTTONS =================
async def admin_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        return

    context.user_data.clear()

    if query.data == "admin_add":
        context.user_data["mode"] = "add"
        await query.message.reply_text("Send: name,email,password")

    elif query.data == "admin_addbal":
        context.user_data["mode"] = "add_balance"
        await query.message.reply_text("Send: user_id,amount")

    elif query.data == "admin_cutbal":
        context.user_data["mode"] = "cut_balance"
        await query.message.reply_text("Send: user_id,amount")

    elif query.data == "admin_broadcast":
        context.user_data["mode"] = "broadcast"
        await query.message.reply_text("Send message")

    elif query.data == "admin_stats":
        cursor.execute("SELECT COUNT(*) FROM users")
        users = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM gmail_tasks")
        gmails = cursor.fetchone()[0]
        await query.message.reply_text(f"Users: {users}\nGmails: {gmails}")

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
        await update.message.reply_text("Contact: http://t.me/Contact_Us_Alkot_bot")

    elif mode == "upi":
        cursor.execute("UPDATE users SET upi=? WHERE user_id=?", (text, update.effective_user.id))
        conn.commit()
        context.user_data.clear()
        await update.message.reply_text("✅ UPI Saved")

    elif is_admin(update.effective_user.id):

        if mode == "add":
            try:
                name, email, password = text.split(",")
                cursor.execute("INSERT INTO gmail_tasks (name,email,password) VALUES (?,?,?)",
                               (name.strip(), email.strip(), password.strip()))
                conn.commit()
                await update.message.reply_text("✅ Gmail Added")
            except:
                await update.message.reply_text("❌ Format: name,email,password")

        elif mode == "broadcast":
            cursor.execute("SELECT user_id FROM users")
            for u in cursor.fetchall():
                try:
                    await context.bot.send_message(u[0], text)
                except:
                    pass
            await update.message.reply_text("✅ Broadcast sent")

        elif mode == "add_balance":
            try:
                user_id, amount = text.split(",")
                cursor.execute("UPDATE users SET balance=balance+? WHERE user_id=?",
                               (int(amount), int(user_id)))
                conn.commit()
                await context.bot.send_message(int(user_id), f"💰 ₹{amount} added")
                await update.message.reply_text("✅ Done")
            except:
                await update.message.reply_text("❌ Format: user_id,amount")

        elif mode == "cut_balance":
            try:
                user_id, amount = text.split(",")
                cursor.execute("UPDATE users SET balance=balance-? WHERE user_id=?",
                               (int(amount), int(user_id)))
                conn.commit()
                await context.bot.send_message(int(user_id), f"➖ ₹{amount} deducted")
                await update.message.reply_text("✅ Done")
            except:
                await update.message.reply_text("❌ Format: user_id,amount")

        context.user_data.clear()

# ================= RUN =================
app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("admin", admin))

app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))

app.add_handler(CallbackQueryHandler(done, pattern="done"))
app.add_handler(CallbackQueryHandler(cancel, pattern="cancel"))
app.add_handler(CallbackQueryHandler(admin_actions, pattern="gok_|gno_"))
app.add_handler(CallbackQueryHandler(withdraw_admin, pattern="wok_|wno_"))
app.add_handler(CallbackQueryHandler(admin_buttons, pattern="admin_"))

app.run_polling()
