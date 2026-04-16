import sqlite3
from telegram import (
    Update, ReplyKeyboardMarkup,
    InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler,
    MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)

TOKEN = "8786051738:AAHRu0V5a3FbDQqdyHCLiRwJPCFk0Sxt0hQ"
ADMIN_ID = 2097179248  # your Telegram ID

# ================= DATABASE =================
conn = sqlite3.connect("bot.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    name TEXT,
    balance INTEGER DEFAULT 0,
    upi TEXT,
    referred_by INTEGER
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

cursor.execute("""
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    description TEXT,
    reward INTEGER,
    status TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS user_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    task_id INTEGER,
    status TEXT
)
""")

conn.commit()

# ================= MENU =================
def menu():
    return ReplyKeyboardMarkup([
        ["🎯 Earn Tasks", "💰 Balance"],
        ["🏧 Withdrawal", "📜 History"],
        ["🔗 Link UPI", "👥 My Referral"]
    ], resize_keyboard=True)

# ================= START =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ref = context.args[0] if context.args else None

    cursor.execute("SELECT * FROM users WHERE user_id=?", (user.id,))
    if not cursor.fetchone():
        cursor.execute(
            "INSERT INTO users (user_id, name, referred_by) VALUES (?, ?, ?)",
            (user.id, user.first_name, ref)
        )
        conn.commit()

        # referral reward
        if ref:
            cursor.execute("UPDATE users SET balance = balance + 3 WHERE user_id=?", (ref,))
            conn.commit()

    await update.message.reply_text("Welcome!", reply_markup=menu())

# ================= BALANCE =================
async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    cursor.execute("SELECT balance, upi FROM users WHERE user_id=?", (user_id,))
    bal, upi = cursor.fetchone()

    await update.message.reply_text(
        f"💰 Balance: ₹{bal}\n🔗 UPI: {upi if upi else 'Not set'}"
    )

# ================= LINK UPI =================
async def link_upi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Send UPI ID (example: name@upi)")
    context.user_data["await_upi"] = True

async def save_upi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("await_upi"):
        upi = update.message.text.strip()
        user_id = update.effective_user.id

        if "@" not in upi:
            await update.message.reply_text("❌ Invalid UPI")
            return

        cursor.execute("UPDATE users SET upi=? WHERE user_id=?", (upi, user_id))
        conn.commit()

        context.user_data["await_upi"] = False
        await update.message.reply_text("✅ UPI Linked")

# ================= ADMIN ADD TASK =================
async def add_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    await update.message.reply_text("Send tasks:\nTask | reward")
    context.user_data["add_task"] = True

async def save_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("add_task"):
        lines = update.message.text.split("\n")

        for line in lines:
            try:
                desc, reward = line.split("|")
                cursor.execute(
                    "INSERT INTO tasks (description, reward, status) VALUES (?, ?, ?)",
                    (desc.strip(), int(reward.strip()), "active")
                )
            except:
                pass

        conn.commit()
        context.user_data["add_task"] = False
        await update.message.reply_text("✅ Tasks Added")

# ================= EARN TASK =================
async def earn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    cursor.execute("""
        SELECT t.id, t.description, t.reward 
        FROM tasks t
        WHERE t.status='active'
        LIMIT 1
    """)
    task = cursor.fetchone()

    if not task:
        await update.message.reply_text("No tasks available")
        return

    task_id, desc, reward = task

    cursor.execute(
        "INSERT INTO user_tasks (user_id, task_id, status) VALUES (?, ?, ?)",
        (user_id, task_id, "pending")
    )
    conn.commit()

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Done", callback_data=f"done_{task_id}")]
    ])

    await update.message.reply_text(
        f"📋 Task:\n{desc}\n\n💰 ₹{reward}",
        reply_markup=keyboard
    )

# ================= TASK DONE =================
async def task_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    task_id = int(query.data.split("_")[1])
    user_id = query.from_user.id

    cursor.execute("SELECT reward FROM tasks WHERE id=?", (task_id,))
    reward = cursor.fetchone()[0]

    cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (reward, user_id))
    cursor.execute("UPDATE user_tasks SET status='done' WHERE user_id=? AND task_id=?", (user_id, task_id))
    conn.commit()

    await query.edit_message_text(f"✅ Task Completed! ₹{reward} added")

# ================= WITHDRAW =================
async def withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    cursor.execute("SELECT balance, upi, name FROM users WHERE user_id=?", (user_id,))
    bal, upi, name = cursor.fetchone()

    if bal < 50:
        await update.message.reply_text("Minimum ₹50 required")
        return

    if not upi:
        await update.message.reply_text("Link UPI first")
        return

    cursor.execute(
        "INSERT INTO withdrawals (user_id, amount, upi, status) VALUES (?, ?, ?, ?)",
        (user_id, bal, upi, "pending")
    )
    wid = cursor.lastrowid

    cursor.execute("UPDATE users SET balance=0 WHERE user_id=?", (user_id,))
    conn.commit()

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Approve", callback_data=f"approve_{wid}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"reject_{wid}")
        ]
    ])

    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=f"💸 Withdrawal\n👤 {name}\n💰 ₹{bal}\n🔗 {upi}\nID:{wid}",
        reply_markup=keyboard
    )

    await update.message.reply_text("Request sent")

# ================= ADMIN ACTION =================
async def admin_actions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    action, wid = query.data.split("_")
    wid = int(wid)

    cursor.execute("SELECT user_id, amount FROM withdrawals WHERE id=?", (wid,))
    user_id, amount = cursor.fetchone()

    if action == "approve":
        cursor.execute("UPDATE withdrawals SET status='approved' WHERE id=?", (wid,))
        conn.commit()

        await context.bot.send_message(user_id, f"✅ Withdrawal Approved ₹{amount}")
        await query.edit_message_text("Approved")

    elif action == "reject":
        cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (amount, user_id))
        cursor.execute("UPDATE withdrawals SET status='rejected' WHERE id=?", (wid,))
        conn.commit()

        await context.bot.send_message(user_id, f"❌ Rejected ₹{amount} refunded")
        await query.edit_message_text("Rejected")

# ================= REFERRAL =================
async def referral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    link = f"https://t.me/YOUR_BOT?start={user_id}"

    await update.message.reply_text(f"🔗 Your Link:\n{link}\nEarn ₹3 per referral")

# ================= HANDLER =================
async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if text == "💰 Balance":
        await balance(update, context)

    elif text == "🎯 Earn Tasks":
        await earn(update, context)

    elif text == "🏧 Withdrawal":
        await withdraw(update, context)

    elif text == "🔗 Link UPI":
        await link_upi(update, context)

    elif text == "👥 My Referral":
        await referral(update, context)

    else:
        await save_upi(update, context)
        await save_tasks(update, context)

# ================= RUN =================
app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("addtasks", add_tasks))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))
app.add_handler(CallbackQueryHandler(task_done, pattern="done_"))
app.add_handler(CallbackQueryHandler(admin_actions, pattern="approve_|reject_"))

app.run_polling()
