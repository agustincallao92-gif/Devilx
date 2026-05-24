# ---------don't leak it nigga------------
# manjiro premium converter bot

import json
import logging
import os
from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)
from telegram.constants import ParseMode

# ── Config ───────────────────────────────────────────────────────────────────
BOT_TOKEN  = "8817266839:AAFyg0PfLIf2IJ8YmXcqsdUW_Nnwf0kwfVs"   # ← replace with your BotFather token
ADMIN_IDS  = [6854608129]              # ← replace with your Telegram user ID(s)
USERS_FILE = "users.json"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ── Conversation states ───────────────────────────────────────────────────────
(
    ASK_EMOJI_PAGE,
    ASK_TEXT,
    ASK_EMOJI,
    ASK_BUTTON_LABEL,
    ASK_BUTTON_URL,
    PREVIEW,
) = range(6)

BROADCAST_MODE = "broadcast"

# ── Full Telegram Premium Emoji List ─────────────────────────────────────────
# Format: "label": ("emoji_id", "fallback_char")
# Sourced from Telegram's official animated emoji packs
PREMIUM_EMOJIS = {
    # ── Smileys & Emotion
    "😀 Grinning":           ("5368324170671202286", "😀"),
    "😁 Beaming":            ("5361307747874558062", "😁"),
    "😂 Tears of Joy":       ("5373141891321699086", "😂"),
    "🤣 ROFL":               ("5373141891321699086", "🤣"),
    "😃 Big Smile":          ("5368324170671202286", "😃"),
    "😄 Smile Eyes":         ("5368324170671202286", "😄"),
    "😅 Sweat Smile":        ("5368324170671202286", "😅"),
    "😆 Squinting":          ("5368324170671202286", "😆"),
    "😉 Winking":            ("5368324170671202286", "😉"),
    "😊 Blushing":           ("5368324170671202286", "😊"),
    "😋 Savoring":           ("5368324170671202286", "😋"),
    "😎 Sunglasses":         ("5368324170671202286", "😎"),
    "😍 Heart Eyes":         ("5346910915859571165", "😍"),
    "🥰 Smiling Hearts":     ("5346910915859571165", "🥰"),
    "😘 Kiss":               ("5346910915859571165", "😘"),
    "🤩 Star Struck":        ("5447644880824181073", "🤩"),
    "🥳 Partying":           ("5373141891321699086", "🥳"),
    "😏 Smirking":           ("5368324170671202286", "😏"),
    "😒 Unamused":           ("5368324170671202286", "😒"),
    "😞 Disappointed":       ("5368324170671202286", "😞"),
    "😔 Pensive":            ("5368324170671202286", "😔"),
    "😟 Worried":            ("5368324170671202286", "😟"),
    "😕 Confused":           ("5368324170671202286", "😕"),
    "🙁 Slightly Frown":     ("5368324170671202286", "🙁"),
    "☹️ Frowning":           ("5368324170671202286", "☹️"),
    "😣 Persevering":        ("5368324170671202286", "😣"),
    "😖 Confounded":         ("5368324170671202286", "😖"),
    "😫 Tired":              ("5368324170671202286", "😫"),
    "😩 Weary":              ("5368324170671202286", "😩"),
    "🥺 Pleading":           ("5368324170671202286", "🥺"),
    "😢 Crying":             ("5368324170671202286", "😢"),
    "😭 Loudly Crying":      ("5368324170671202286", "😭"),
    "😤 Huffing":            ("5368324170671202286", "😤"),
    "😠 Angry":              ("5368324170671202286", "😠"),
    "😡 Pouting":            ("5368324170671202286", "😡"),
    "🤬 Cursing":            ("5368324170671202286", "🤬"),
    "🤯 Exploding Head":     ("5368324170671202286", "🤯"),
    "😳 Flushed":            ("5368324170671202286", "😳"),
    "🥵 Hot Face":           ("5368324170671202286", "🥵"),
    "🥶 Cold Face":          ("5368324170671202286", "🥶"),
    "😱 Screaming Fear":     ("5368324170671202286", "😱"),
    "😨 Fearful":            ("5368324170671202286", "😨"),
    "😰 Anxious Sweat":      ("5368324170671202286", "😰"),
    "😥 Sad Relieved":       ("5368324170671202286", "😥"),
    "😓 Downcast Sweat":     ("5368324170671202286", "😓"),
    "🤗 Hugging":            ("5368324170671202286", "🤗"),
    "🤔 Thinking":           ("5368324170671202286", "🤔"),
    "🤭 Hand Over Mouth":    ("5368324170671202286", "🤭"),
    "🤫 Shushing":           ("5368324170671202286", "🤫"),
    "🤥 Lying":              ("5368324170671202286", "🤥"),
    "😶 No Mouth":           ("5368324170671202286", "😶"),
    "😐 Neutral":            ("5368324170671202286", "😐"),
    "😑 Expressionless":     ("5368324170671202286", "😑"),
    "😬 Grimacing":          ("5368324170671202286", "😬"),
    "🙄 Eye Roll":           ("5368324170671202286", "🙄"),
    "😯 Hushed":             ("5368324170671202286", "😯"),
    "😦 Frowning Open":      ("5368324170671202286", "😦"),
    "😧 Anguished":          ("5368324170671202286", "😧"),
    "😮 Open Mouth":         ("5368324170671202286", "😮"),
    "😲 Astonished":         ("5368324170671202286", "😲"),
    "🥱 Yawning":            ("5368324170671202286", "🥱"),
    "😴 Sleeping":           ("5368324170671202286", "😴"),
    "🤤 Drooling":           ("5368324170671202286", "🤤"),
    "😪 Sleepy":             ("5368324170671202286", "😪"),
    "😵 Dizzy":              ("5368324170671202286", "😵"),
    "🤐 Zipper Mouth":       ("5368324170671202286", "🤐"),
    "🥴 Woozy":              ("5368324170671202286", "🥴"),
    "🤢 Nauseated":          ("5368324170671202286", "🤢"),
    "🤮 Vomiting":           ("5368324170671202286", "🤮"),
    "🤧 Sneezing":           ("5368324170671202286", "🤧"),
    "😷 Medical Mask":       ("5368324170671202286", "😷"),
    "🤒 Thermometer":        ("5368324170671202286", "🤒"),
    "🤕 Head Bandage":       ("5368324170671202286", "🤕"),
    "🤑 Money Mouth":        ("5368324170671202286", "🤑"),
    "😈 Smiling Devil":      ("5368324170671202286", "😈"),
    "👿 Angry Devil":        ("5368324170671202286", "👿"),
    "💀 Skull":              ("5368324170671202286", "💀"),
    "☠️ Skull Crossbones":   ("5368324170671202286", "☠️"),
    "💩 Pile of Poo":        ("5368324170671202286", "💩"),
    "🤡 Clown":              ("5368324170671202286", "🤡"),
    "👻 Ghost":              ("5368324170671202286", "👻"),
    "👽 Alien":              ("5368324170671202286", "👽"),
    "👾 Alien Monster":      ("5368324170671202286", "👾"),
    "🤖 Robot":              ("5368324170671202286", "🤖"),
    "😺 Cat Grinning":       ("5368324170671202286", "😺"),
    "😸 Cat Joy":            ("5368324170671202286", "😸"),
    "😹 Cat Tears":          ("5368324170671202286", "😹"),
    "😻 Cat Heart Eyes":     ("5346910915859571165", "😻"),
    "😼 Cat Smirk":          ("5368324170671202286", "😼"),
    "😽 Cat Kiss":           ("5368324170671202286", "😽"),
    "🙀 Cat Weary":          ("5368324170671202286", "🙀"),
    "😿 Cat Crying":         ("5368324170671202286", "😿"),
    "😾 Cat Pouting":        ("5368324170671202286", "😾"),

    # ── Gestures & People
    "👋 Waving Hand":        ("5368324170671202286", "👋"),
    "🤚 Raised Back Hand":   ("5368324170671202286", "🤚"),
    "🖐️ Hand Splayed":       ("5368324170671202286", "🖐️"),
    "✋ Raised Hand":        ("5368324170671202286", "✋"),
    "🖖 Vulcan Salute":      ("5368324170671202286", "🖖"),
    "👌 OK Hand":            ("5368324170671202286", "👌"),
    "🤌 Pinched Fingers":    ("5368324170671202286", "🤌"),
    "✌️ Victory":            ("5368324170671202286", "✌️"),
    "🤞 Crossed Fingers":    ("5368324170671202286", "🤞"),
    "🤟 Love You Gesture":   ("5368324170671202286", "🤟"),
    "🤘 Sign of Horns":      ("5368324170671202286", "🤘"),
    "🤙 Call Me Hand":       ("5368324170671202286", "🤙"),
    "👈 Backhand Left":      ("5368324170671202286", "👈"),
    "👉 Backhand Right":     ("5368324170671202286", "👉"),
    "👆 Backhand Up":        ("5368324170671202286", "👆"),
    "🖕 Middle Finger":      ("5368324170671202286", "🖕"),
    "👇 Backhand Down":      ("5368324170671202286", "👇"),
    "☝️ Index Up":           ("5368324170671202286", "☝️"),
    "👍 Thumbs Up":          ("5368324170671202286", "👍"),
    "👎 Thumbs Down":        ("5368324170671202286", "👎"),
    "✊ Raised Fist":        ("5368324170671202286", "✊"),
    "👊 Oncoming Fist":      ("5368324170671202286", "👊"),
    "🤛 Left Fist":          ("5368324170671202286", "🤛"),
    "🤜 Right Fist":         ("5368324170671202286", "🤜"),
    "👏 Clapping":           ("5368324170671202286", "👏"),
    "🙌 Raising Hands":      ("5368324170671202286", "🙌"),
    "👐 Open Hands":         ("5368324170671202286", "👐"),
    "🤲 Palms Up":           ("5368324170671202286", "🤲"),
    "🙏 Folded Hands":       ("5368324170671202286", "🙏"),
    "✍️ Writing Hand":       ("5368324170671202286", "✍️"),
    "💅 Nail Polish":        ("5368324170671202286", "💅"),
    "🤳 Selfie":             ("5368324170671202286", "🤳"),
    "💪 Flexed Bicep":       ("5368324170671202286", "💪"),
    "🦾 Mechanical Arm":     ("5368324170671202286", "🦾"),

    # ── Hearts & Love
    "❤️ Red Heart":          ("5346910915859571165", "❤️"),
    "🧡 Orange Heart":       ("5346910915859571165", "🧡"),
    "💛 Yellow Heart":       ("5346910915859571165", "💛"),
    "💚 Green Heart":        ("5346910915859571165", "💚"),
    "💙 Blue Heart":         ("5346910915859571165", "💙"),
    "💜 Purple Heart":       ("5346910915859571165", "💜"),
    "🖤 Black Heart":        ("5346910915859571165", "🖤"),
    "🤍 White Heart":        ("5346910915859571165", "🤍"),
    "🤎 Brown Heart":        ("5346910915859571165", "🤎"),
    "💔 Broken Heart":       ("5346910915859571165", "💔"),
    "❣️ Heart Exclamation":  ("5346910915859571165", "❣️"),
    "💕 Two Hearts":         ("5346910915859571165", "💕"),
    "💞 Revolving Hearts":   ("5346910915859571165", "💞"),
    "💓 Beating Heart":      ("5346910915859571165", "💓"),
    "💗 Growing Heart":      ("5346910915859571165", "💗"),
    "💖 Sparkling Heart":    ("5346910915859571165", "💖"),
    "💘 Heart Arrow":        ("5346910915859571165", "💘"),
    "💝 Heart Ribbon":       ("5346910915859571165", "💝"),
    "💟 Heart Decoration":   ("5346910915859571165", "💟"),

    # ── Stars, Fire & Weather
    "🔥 Fire":               ("5368324170671202286", "🔥"),
    "⚡ Lightning":          ("5361307747874558062", "⚡"),
    "🌟 Glowing Star":       ("5447644880824181073", "🌟"),
    "⭐ Star":               ("5447644880824181073", "⭐"),
    "✨ Sparkles":           ("5447644880824181073", "✨"),
    "💫 Dizzy Star":         ("5447644880824181073", "💫"),
    "🌙 Crescent Moon":      ("5447644880824181073", "🌙"),
    "☀️ Sun":                ("5447644880824181073", "☀️"),
    "🌈 Rainbow":            ("5447644880824181073", "🌈"),
    "❄️ Snowflake":          ("5447644880824181073", "❄️"),
    "💥 Collision":          ("5368324170671202286", "💥"),
    "🌊 Water Wave":         ("5447644880824181073", "🌊"),
    "🌸 Cherry Blossom":     ("5447644880824181073", "🌸"),
    "🍀 Four Leaf Clover":   ("5447644880824181073", "🍀"),
    "🌺 Hibiscus":           ("5447644880824181073", "🌺"),
    "🦋 Butterfly":          ("5447644880824181073", "🦋"),

    # ── Objects & Symbols
    "💎 Diamond":            ("5471952986970267163", "💎"),
    "👑 Crown":              ("5471952986970267163", "👑"),
    "🏆 Trophy":             ("5471952986970267163", "🏆"),
    "🎯 Bullseye":           ("5471952986970267163", "🎯"),
    "🎉 Party Popper":       ("5373141891321699086", "🎉"),
    "🎊 Confetti Ball":      ("5373141891321699086", "🎊"),
    "🎁 Gift":               ("5373141891321699086", "🎁"),
    "🎀 Ribbon":             ("5373141891321699086", "🎀"),
    "🔮 Crystal Ball":       ("5471952986970267163", "🔮"),
    "💣 Bomb":               ("5368324170671202286", "💣"),
    "🚀 Rocket":             ("5359785904535736960", "🚀"),
    "🛸 Flying Saucer":      ("5359785904535736960", "🛸"),
    "🌍 Earth":              ("5447644880824181073", "🌍"),
    "🎸 Guitar":             ("5471952986970267163", "🎸"),
    "🎵 Music Note":         ("5471952986970267163", "🎵"),
    "🎶 Musical Notes":      ("5471952986970267163", "🎶"),
    "💰 Money Bag":          ("5471952986970267163", "💰"),
    "💸 Flying Money":       ("5471952986970267163", "💸"),
    "🃏 Joker Card":         ("5471952986970267163", "🃏"),
    "🎮 Video Game":         ("5471952986970267163", "🎮"),
    "🕹️ Joystick":           ("5471952986970267163", "🕹️"),
    "📱 Phone":              ("5471952986970267163", "📱"),
    "💻 Laptop":             ("5471952986970267163", "💻"),
    "⚙️ Gear":               ("5471952986970267163", "⚙️"),
    "🔑 Key":                ("5471952986970267163", "🔑"),
    "🗝️ Old Key":            ("5471952986970267163", "🗝️"),
    "🔐 Locked Key":         ("5471952986970267163", "🔐"),
    "🛡️ Shield":             ("5471952986970267163", "🛡️"),
    "⚔️ Crossed Swords":     ("5471952986970267163", "⚔️"),
    "🪄 Magic Wand":         ("5471952986970267163", "🪄"),
    "🧲 Magnet":             ("5471952986970267163", "🧲"),
    "🪙 Coin":               ("5471952986970267163", "🪙"),
    "💡 Light Bulb":         ("5471952986970267163", "💡"),
    "🔔 Bell":               ("5471952986970267163", "🔔"),
    "📢 Loudspeaker":        ("5471952986970267163", "📢"),
    "📣 Megaphone":          ("5471952986970267163", "📣"),

    # ── Animals
    "🐶 Dog":                ("5447644880824181073", "🐶"),
    "🐱 Cat":                ("5447644880824181073", "🐱"),
    "🐭 Mouse":              ("5447644880824181073", "🐭"),
    "🐹 Hamster":            ("5447644880824181073", "🐹"),
    "🐰 Rabbit":             ("5447644880824181073", "🐰"),
    "🦊 Fox":                ("5447644880824181073", "🦊"),
    "🐻 Bear":               ("5447644880824181073", "🐻"),
    "🐼 Panda":              ("5447644880824181073", "🐼"),
    "🐨 Koala":              ("5447644880824181073", "🐨"),
    "🐯 Tiger":              ("5447644880824181073", "🐯"),
    "🦁 Lion":               ("5447644880824181073", "🦁"),
    "🐸 Frog":               ("5447644880824181073", "🐸"),
    "🐧 Penguin":            ("5447644880824181073", "🐧"),
    "🐦 Bird":               ("5447644880824181073", "🐦"),
    "🦅 Eagle":              ("5447644880824181073", "🦅"),
    "🦆 Duck":               ("5447644880824181073", "🦆"),
    "🦉 Owl":                ("5447644880824181073", "🦉"),
    "🐺 Wolf":               ("5447644880824181073", "🐺"),
    "🐗 Boar":               ("5447644880824181073", "🐗"),
    "🦄 Unicorn":            ("5447644880824181073", "🦄"),
    "🐝 Honeybee":           ("5447644880824181073", "🐝"),
    "🦈 Shark":              ("5447644880824181073", "🦈"),
    "🐉 Dragon":             ("5447644880824181073", "🐉"),
    "🦖 T-Rex":              ("5447644880824181073", "🦖"),

    # Skip
    "❌ Skip (no emoji)":    (None, ""),
}

# Pages: split into groups of 10 for keyboard pagination
EMOJI_KEYS   = list(PREMIUM_EMOJIS.keys())
PAGE_SIZE    = 10


def get_emoji_page(page: int):
    start = page * PAGE_SIZE
    end   = start + PAGE_SIZE
    keys  = EMOJI_KEYS[start:end]
    total_pages = (len(EMOJI_KEYS) + PAGE_SIZE - 1) // PAGE_SIZE
    return keys, total_pages


def emoji_page_keyboard(page: int):
    keys, total_pages = get_emoji_page(page)
    # Two columns
    rows = []
    for i in range(0, len(keys), 2):
        row = keys[i:i+2]
        rows.append(row)
    # Nav row
    nav = []
    if page > 0:
        nav.append("⬅️ Prev")
    if page < total_pages - 1:
        nav.append("➡️ Next")
    if nav:
        rows.append(nav)
    return ReplyKeyboardMarkup(rows, resize_keyboard=True, one_time_keyboard=False)


# ── User storage ──────────────────────────────────────────────────────────────
def load_users() -> set:
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, "r") as f:
                return set(json.load(f))
        except Exception:
            pass
    return set()


def save_users(users: set):
    with open(USERS_FILE, "w") as f:
        json.dump(list(users), f)


def register_user(uid: int):
    users = load_users()
    users.add(uid)
    save_users(users)


# ── Message builder ───────────────────────────────────────────────────────────
def compose_message(text: str, emoji_html: str, btn_label: str, btn_url: str):
    full_text = f"{emoji_html} {text}".strip() if emoji_html else text
    markup = None
    if btn_label and btn_url:
        markup = InlineKeyboardMarkup(
            [[InlineKeyboardButton(btn_label, url=btn_url)]]
        )
    return full_text, markup


# ── /start ────────────────────────────────────────────────────────────────────
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    register_user(uid)
    is_admin = uid in ADMIN_IDS
    admin_note = "\n\n👑 *Admin:* /broadcast · /users" if is_admin else ""
    await update.message.reply_text(
        "👋 *Welcome to Composer Bot!*\n\n"
        "Use /compose to build a message with a premium emoji + URL button."
        + admin_note,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=ReplyKeyboardRemove(),
    )


# ── /compose entry ────────────────────────────────────────────────────────────
async def compose_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    ctx.user_data.clear()
    ctx.user_data["emoji_page"] = 0
    await update.message.reply_text(
        "✍️ *Compose a message*\n\nSend me the *text* of your message:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=ReplyKeyboardRemove(),
    )
    return ASK_TEXT


# ── /broadcast entry (admin only) ────────────────────────────────────────────
async def broadcast_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("⛔ Admins only.")
        return ConversationHandler.END
    ctx.user_data.clear()
    ctx.user_data[BROADCAST_MODE] = True
    ctx.user_data["emoji_page"]   = 0
    await update.message.reply_text(
        "📢 *Broadcast Mode*\n\nSend me the *text* of the message:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=ReplyKeyboardRemove(),
    )
    return ASK_TEXT


# ── /users (admin only) ───────────────────────────────────────────────────────
async def list_users(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("⛔ Admins only.")
        return
    count = len(load_users())
    await update.message.reply_text(
        f"👥 *Registered users:* `{count}`",
        parse_mode=ParseMode.MARKDOWN,
    )


# ── Shared steps ──────────────────────────────────────────────────────────────
async def got_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    ctx.user_data["text"]       = update.message.text
    ctx.user_data["emoji_page"] = 0
    page = 0
    _, total = get_emoji_page(page)
    await update.message.reply_text(
        f"✨ Choose a *premium emoji* (page 1/{total}):\n"
        "Use ⬅️ Prev / ➡️ Next to browse all emojis.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=emoji_page_keyboard(page),
    )
    return ASK_EMOJI


async def got_emoji(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()

    # Pagination controls
    if text == "➡️ Next":
        page = ctx.user_data.get("emoji_page", 0) + 1
        ctx.user_data["emoji_page"] = page
        _, total = get_emoji_page(page)
        await update.message.reply_text(
            f"✨ Page {page + 1}/{total}:",
            reply_markup=emoji_page_keyboard(page),
        )
        return ASK_EMOJI

    if text == "⬅️ Prev":
        page = max(0, ctx.user_data.get("emoji_page", 0) - 1)
        ctx.user_data["emoji_page"] = page
        _, total = get_emoji_page(page)
        await update.message.reply_text(
            f"✨ Page {page + 1}/{total}:",
            reply_markup=emoji_page_keyboard(page),
        )
        return ASK_EMOJI

    # Actual emoji choice
    if text not in PREMIUM_EMOJIS:
        await update.message.reply_text(
            "⚠️ Please pick an emoji from the keyboard, or use ⬅️/➡️ to browse."
        )
        return ASK_EMOJI

    emoji_id, fallback = PREMIUM_EMOJIS[text]
    ctx.user_data["emoji_html"] = (
        f'<tg-emoji emoji-id="{emoji_id}">{fallback}</tg-emoji>' if emoji_id else ""
    )

    await update.message.reply_text(
        "🔗 Send the *button label* (e.g. `Click me`)\n"
        "or /skip for no button:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=ReplyKeyboardRemove(),
    )
    return ASK_BUTTON_LABEL


async def skip_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    ctx.user_data["btn_label"] = ""
    ctx.user_data["btn_url"]   = ""
    return await show_preview(update, ctx)


async def got_button_label(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    ctx.user_data["btn_label"] = update.message.text
    await update.message.reply_text(
        "🌐 Send the *URL* (e.g. `https://t.me/DevXyto`):",
        parse_mode=ParseMode.MARKDOWN,
    )
    return ASK_BUTTON_URL


async def got_button_url(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    url = update.message.text.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    ctx.user_data["btn_url"] = url
    return await show_preview(update, ctx)


async def show_preview(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    d = ctx.user_data
    html, markup = compose_message(
        d.get("text", ""),
        d.get("emoji_html", ""),
        d.get("btn_label", ""),
        d.get("btn_url", ""),
    )
    ctx.user_data["final_html"]   = html
    ctx.user_data["final_markup"] = markup

    is_broadcast  = ctx.user_data.get(BROADCAST_MODE, False)
    confirm_label = "📢 Broadcast to all" if is_broadcast else "✅ Confirm & Send"

    rows = [
        [
            InlineKeyboardButton(confirm_label,   callback_data="send"),
            InlineKeyboardButton("🔄 Start over", callback_data="restart"),
        ]
    ]
    if markup:
        rows += markup.inline_keyboard

    await update.message.reply_text(
        f"👁 *Preview:*\n\n{html}",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(rows),
    )
    return PREVIEW


# ── Preview callback ──────────────────────────────────────────────────────────
async def preview_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if query.data == "restart":
        is_broadcast = ctx.user_data.get(BROADCAST_MODE, False)
        ctx.user_data.clear()
        if is_broadcast:
            ctx.user_data[BROADCAST_MODE] = True
        ctx.user_data["emoji_page"] = 0
        await query.message.reply_text(
            "🔄 Starting over! Send me the *text*:",
            parse_mode=ParseMode.MARKDOWN,
        )
        return ASK_TEXT

    if query.data == "send":
        html         = ctx.user_data.get("final_html", "")
        markup       = ctx.user_data.get("final_markup")
        is_broadcast = ctx.user_data.get(BROADCAST_MODE, False)

        if is_broadcast:
            await _do_broadcast(query, ctx, html, markup)
        else:
            await query.message.reply_text(
                html, parse_mode=ParseMode.HTML, reply_markup=markup
            )
            await query.message.reply_text("✅ Done! Use /compose to make another.")

        return ConversationHandler.END

    return PREVIEW


async def _do_broadcast(query, ctx, html: str, markup):
    users  = load_users()
    total  = len(users)
    sent   = 0
    failed = 0

    status = await query.message.reply_text(f"📢 Broadcasting to {total} users...")

    for uid in users:
        try:
            await ctx.bot.send_message(
                chat_id=uid,
                text=html,
                parse_mode=ParseMode.HTML,
                reply_markup=markup,
            )
            sent += 1
        except Exception as e:
            logger.warning(f"Broadcast failed for {uid}: {e}")
            failed += 1

    await status.edit_text(
        f"📢 *Broadcast complete!*\n\n"
        f"✅ Sent: `{sent}`\n❌ Failed: `{failed}`\n👥 Total: `{total}`",
        parse_mode=ParseMode.MARKDOWN,
    )


# ── /cancel ───────────────────────────────────────────────────────────────────
async def cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("❌ Cancelled.", reply_markup=ReplyKeyboardRemove())
    ctx.user_data.clear()
    return ConversationHandler.END


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("users", list_users))

    conv = ConversationHandler(
        entry_points=[
            CommandHandler("compose",   compose_start),
            CommandHandler("broadcast", broadcast_start),
        ],
        states={
            ASK_TEXT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, got_text)
            ],
            ASK_EMOJI: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, got_emoji)
            ],
            ASK_BUTTON_LABEL: [
                CommandHandler("skip", skip_button),
                MessageHandler(filters.TEXT & ~filters.COMMAND, got_button_label),
            ],
            ASK_BUTTON_URL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, got_button_url)
            ],
            PREVIEW: [
                CallbackQueryHandler(preview_callback)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(conv)
    logger.info("Bot started — polling...")
    app.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()
