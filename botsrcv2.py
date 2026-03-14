import sqlite3
import random
import string
from telegram import ReplyKeyboardMarkup, KeyboardButton, Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

TOKEN = "8686181910:AAF_6ZXZ-TtVBPXflmS22gUPodg7mabTQ1o"
ADMIN_ID = 6854608129

# DATABASE
db = sqlite3.connect("users.db", check_same_thread=False)
cursor = db.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users(
id INTEGER PRIMARY KEY,
name TEXT,
phone TEXT,
key TEXT
)
""")
db.commit()


# GENERATE KEY
def generate_key():
    chars = string.ascii_uppercase + string.digits
    return "XI-" + "".join(random.choice(chars) for _ in range(10))


# START
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    button = [[KeyboardButton("🔑 Free Key", request_contact=True)]]

    keyboard = ReplyKeyboardMarkup(button, resize_keyboard=True)

    await update.message.reply_text(
        "🎁 Press the button to get your FREE KEY",
        reply_markup=keyboard
    )


# CONTACT RECEIVED
async def contact(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user
    phone = update.message.contact.phone_number

    cursor.execute("SELECT * FROM users WHERE id=?", (user.id,))
    data = cursor.fetchone()

    if data:
        await update.message.reply_text(f"🔑 Your key: {data[3]}")
        return

    key = generate_key()

    cursor.execute(
        "INSERT INTO users VALUES (?,?,?,?)",
        (user.id, user.first_name, phone, key)
    )

    db.commit()

    await update.message.reply_text(
        f"✅ Registration complete!\n\n🔑 Your Key:\n{key}"
    )


# ADMIN STATS
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id != ADMIN_ID:
        return

    cursor.execute("SELECT COUNT(*) FROM users")
    total = cursor.fetchone()[0]

    await update.message.reply_text(f"👥 Total Users: {total}")


# BROADCAST
async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id != ADMIN_ID:
        return

    message = " ".join(context.args)

    cursor.execute("SELECT id FROM users")
    users = cursor.fetchall()

    for u in users:
        try:
            await context.bot.send_message(chat_id=u[0], text=message)
        except:
            pass

    await update.message.reply_text("📢 Broadcast sent!")


app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("stats", stats))
app.add_handler(CommandHandler("broadcast", broadcast))
app.add_handler(MessageHandler(filters.CONTACT, contact))

print("🚀 PRO Key Bot Running...")
app.run_polling()
