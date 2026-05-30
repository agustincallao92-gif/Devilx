# ─────────────────────────────────────────────────────────────────────────────
#  MANJIRO HOSTING  +  MANJI MANJI AI Code Fixer
#
#  Features:
#    • Upload a .py bot file → auto-saved & launched
#    • Start / Stop / Restart individual bots
#    • View live logs (last N lines) for any bot
#    • CPU & RAM usage per bot process
#    • List all bots with status (running / stopped / crashed)
#    • Delete a bot (stops it and removes the file)
#    • Auto-restart crashed bots (optional per bot)
#    • Persistent state — survives host_bot restarts
#    • AI Fixer — send any .py file → MANJI AI finds bugs, returns fixed file
#    • AI Fix from Logs — one button to auto-fix a crashed bot using its logs
#    • AI Chat — ask MANJI AI anything about Python / Telegram bots
#
#  Requirements:
#    pip install -r requirements.txt
#    — or individually:
#    pip install python-telegram-bot>=21.0 psutil>=5.9 google-generativeai>=0.5
#
#  Setup:
#    1. Set BOT_TOKEN, ADMIN_IDS, ANTHROPIC_API_KEY below
#    2. python host_bot.py
#    3. In Telegram: /start  (the only slash command — everything else is buttons)
# ─────────────────────────────────────────────────────────────────────────────

import asyncio
import json
import logging
import os
import re
import secrets
import signal
import subprocess
import sys
import time
import threading
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import psutil
import google.generativeai as genai

from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from telegram.constants import ParseMode

# ── Config ────────────────────────────────────────────────────────────────────
BOT_TOKEN      = "8268389194:AAFQ__wVslIfwEerDQNRRKhwd8zVhqwoqmg"   # BotFather token for THIS manager bot
ADMIN_IDS      = [6854608129]             # your Telegram user ID(s)
GEMINI_API_KEY = "AIzaSyDHEPICq2hafbpilXDo7eS3S7JkcbcH9vI"    # free at aistudio.google.com
OWNER_USERNAME = "devxyto"               # without @, shown in Contact Owner button
AI_MODEL       = "gemini-1.5-flash"      # free tier model

BOTS_DIR   = Path("hosted_bots")
STATE_FILE = "host_state.json"
KEYS_FILE  = "access_keys.json"
LOG_LINES  = 40
MAX_RUNNING = 6   # maximum simultaneously running .py bots
PORT = int(os.environ.get("PORT", 8080))  # Render injects PORT automatically

KEY_DURATIONS = {
    "1d":  timedelta(days=1),
    "3d":  timedelta(days=3),
    "8d":  timedelta(days=8),
    "13d": timedelta(days=13),
    "32d": timedelta(days=32),
    "1yr": timedelta(days=365),
}

BOTS_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    format="%(asctime)s [HOST] %(levelname)s %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ── Gemini client ─────────────────────────────────────────────────────────────
genai.configure(api_key=GEMINI_API_KEY)
ai_model = genai.GenerativeModel(
    model_name=AI_MODEL,
    generation_config={"max_output_tokens": 4096},
)

# ── Runtime state ─────────────────────────────────────────────────────────────
bots: dict  = {}   # persisted to STATE_FILE
procs: dict = {}   # subprocess.Popen per bot name

WAITING_UPLOAD: set  = set()   # uid → expecting .py file to host
WAITING_AI_FIX: set  = set()   # uid → expecting .py file to AI-fix
WAITING_AI_CHAT: dict = {}     # uid → list of conversation messages
WAITING_ANNOUNCE: set = set()  # uid → expecting announcement text
WAITING_INSTALL: dict = {}     # uid → {"name": bot_name, "upgrade": bool}


# ── Persistence ───────────────────────────────────────────────────────────────
def load_state():
    global bots
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                bots = json.load(f)
        except Exception:
            bots = {}


def save_state():
    with open(STATE_FILE, "w") as f:
        json.dump(bots, f, indent=2)


# ── Key system ────────────────────────────────────────────────────────────────
def load_keys() -> dict:
    if os.path.exists(KEYS_FILE):
        try:
            with open(KEYS_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_keys(keys: dict):
    with open(KEYS_FILE, "w") as f:
        json.dump(keys, f, indent=2)


def generate_key(duration_label: str) -> str | None:
    """Generate a new access key and persist it. Returns key string or None if bad label."""
    if duration_label not in KEY_DURATIONS:
        return None
    key = secrets.token_hex(16)          # 32-char hex key
    expiry = (datetime.utcnow() + KEY_DURATIONS[duration_label]).isoformat()
    keys = load_keys()
    keys[key] = {"expires": expiry, "duration": duration_label, "used_by": None}
    save_keys(keys)
    return key


def activate_key(uid: int, key: str) -> str:
    """
    Try to activate a key for a user.
    Returns 'ok', 'already_active', 'invalid', or 'expired'.
    """
    keys = load_keys()
    if key not in keys:
        return "invalid"
    entry = keys[key]
    if datetime.utcnow() > datetime.fromisoformat(entry["expires"]):
        return "expired"
    # Allow re-use by same user (e.g. they restarted the bot)
    if entry["used_by"] and entry["used_by"] != uid:
        return "invalid"          # key already claimed by someone else
    entry["used_by"] = uid
    save_keys(keys)
    return "ok"


def user_has_access(uid: int) -> bool:
    """Admins always have access; others need a valid unexpired key."""
    if uid in ADMIN_IDS:
        return True
    keys = load_keys()
    now = datetime.utcnow()
    for entry in keys.values():
        if entry.get("used_by") == uid:
            if now <= datetime.fromisoformat(entry["expires"]):
                return True
    return False


# ── Process helpers ───────────────────────────────────────────────────────────
def log_path(name: str) -> Path:
    return BOTS_DIR / f"{name}.log"


def start_bot(name: str) -> tuple[bool, str]:
    """Returns (success, reason). reason is '' on success."""
    if name not in bots:
        return False, "not_found"
    if name in procs and procs[name].poll() is None:
        return False, "already_running"
    # Enforce max running bots limit
    running_count = sum(1 for n in procs if procs[n].poll() is None)
    if running_count >= MAX_RUNNING:
        return False, "limit_reached"
    bot_file = bots[name]["file"]
    lp = log_path(name)
    log_handle = open(lp, "a")
    proc = subprocess.Popen(
        [sys.executable, "-u", bot_file],
        stdout=log_handle,
        stderr=log_handle,
        text=True,
        preexec_fn=os.setsid if os.name != "nt" else None,
    )
    procs[name] = proc
    logger.info(f"Started '{name}' PID={proc.pid}")
    return True, ""


def stop_bot(name: str) -> bool:
    proc = procs.get(name)
    if proc is None or proc.poll() is not None:
        return False
    try:
        if os.name != "nt":
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        else:
            proc.terminate()
        proc.wait(timeout=5)
    except Exception:
        proc.kill()
    procs.pop(name, None)
    logger.info(f"Stopped '{name}'")
    return True


MAX_PACKAGES   = 20   # hard cap per install session
BATCH_SIZE     = 5    # packages installed per pip call
BATCH_TIMEOUT  = 120  # seconds per batch

def install_requirements(packages: str, upgrade: bool = True) -> tuple[bool, str]:
    """
    Install up to MAX_PACKAGES pip packages in batches of BATCH_SIZE.
    Returns (overall_success, full_output_text).
    """
    pkg_list = packages.replace("\n", " ").split()
    if not pkg_list:
        return False, "No packages specified."

    # Enforce hard cap
    if len(pkg_list) > MAX_PACKAGES:
        pkg_list = pkg_list[:MAX_PACKAGES]

    base_cmd = [sys.executable, "-m", "pip", "install"]
    if upgrade:
        base_cmd.append("--upgrade")

    batches = [pkg_list[i:i + BATCH_SIZE] for i in range(0, len(pkg_list), BATCH_SIZE)]
    all_output: list[str] = []
    overall_success = True

    for idx, batch in enumerate(batches, 1):
        header = f"── Batch {idx}/{len(batches)}: {' '.join(batch)} ──"
        all_output.append(header)
        try:
            result = subprocess.run(
                base_cmd + batch,
                capture_output=True,
                text=True,
                timeout=BATCH_TIMEOUT,
            )
            batch_out = (result.stdout + result.stderr).strip()
            all_output.append(batch_out)
            if result.returncode != 0:
                overall_success = False
                all_output.append(f"⚠️ Batch {idx} failed (exit {result.returncode})")
        except subprocess.TimeoutExpired:
            overall_success = False
            all_output.append(f"❌ Batch {idx} timed out after {BATCH_TIMEOUT}s")
        except Exception as e:
            overall_success = False
            all_output.append(f"❌ Batch {idx} error: {e}")

    return overall_success, "\n".join(all_output)


def parse_requirements_txt(content: str) -> list[str]:
    """Parse a requirements.txt file and return a list of valid package specs."""
    packages = []
    for line in content.splitlines():
        line = line.strip()
        # Skip blank lines, comments, and options like -r, --index-url, etc.
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        packages.append(line)
    return packages


def bot_status(name: str) -> str:
    proc = procs.get(name)
    if proc is None:
        return "⏹ Stopped"
    if proc.poll() is None:
        return "✅ Running"
    return "💀 Crashed"


def bot_resources(name: str) -> str:
    proc = procs.get(name)
    if proc is None or proc.poll() is not None:
        return "—"
    try:
        p   = psutil.Process(proc.pid)
        cpu = p.cpu_percent(interval=0.2)
        ram = p.memory_info().rss / 1024 / 1024
        return f"CPU {cpu:.1f}% | RAM {ram:.1f} MB"
    except Exception:
        return "—"


def read_log(name: str, n: int = LOG_LINES) -> str:
    lp = log_path(name)
    if not lp.exists():
        return "(no logs yet)"
    lines = lp.read_text(errors="replace").splitlines()
    snippet = lines[-n:] if len(lines) > n else lines
    return "\n".join(snippet) or "(empty log)"


# ── AI helpers ────────────────────────────────────────────────────────────────
FIXER_SYSTEM = (
    "You are an expert Python and Telegram bot developer.\n"
    "When given Python source code (and optionally crash logs), you:\n"
    "1. Identify ALL bugs, errors, and bad practices with line numbers.\n"
    "2. Return the COMPLETE fixed Python file — no placeholders, no omissions.\n\n"
    "Format your reply EXACTLY like this:\n\n"
    "ISSUES FOUND:\n"
    "<bullet list of issues with line numbers>\n\n"
    "FIXED CODE:\n"
    "```python\n"
    "<complete fixed file>\n"
    "```\n\n"
    "SUMMARY:\n"
    "<brief summary of all changes made>"
)

CHAT_SYSTEM = (
    "You are a helpful Telegram bot development assistant inside MANJIRO HOSTING. "
    "Help with Python, python-telegram-bot library, debugging, and Telegram Bot API. "
    "Be concise and practical. Use code blocks when showing code."
)


def _sync_ai_fix(code: str, logs: str = "") -> str:
    user_content = f"Python bot file to fix:\n\n```python\n{code}\n```"
    if logs:
        user_content += f"\n\nRecent crash logs:\n\n```\n{logs}\n```"
    user_content += "\n\nFind all issues and return the complete fixed file."
    prompt = FIXER_SYSTEM + "\n\n" + user_content
    resp = ai_model.generate_content(prompt)
    return resp.text


def _sync_ai_chat(history: list, user_msg: str) -> str:
    # Convert history to Gemini format
    gemini_history = []
    for msg in history:
        role = "user" if msg["role"] == "user" else "model"
        gemini_history.append({"role": role, "parts": [msg["content"]]})

    chat = ai_model.start_chat(history=gemini_history)
    resp = chat.send_message(CHAT_SYSTEM + "\n\n" + user_msg if not gemini_history else user_msg)
    reply = resp.text

    # Keep plain history for our internal tracking
    history.append({"role": "user",      "content": user_msg})
    history.append({"role": "assistant", "content": reply})
    return reply


def extract_fixed_code(ai_response: str) -> str | None:
    match = re.search(r"```python\n(.*?)```", ai_response, re.DOTALL)
    if match:
        return match.group(1).strip()
    return None


def strip_code_block(ai_response: str) -> str:
    return re.sub(r"```python.*?```", "[see fixed file below]", ai_response, flags=re.DOTALL).strip()


# ── Auth decorators ───────────────────────────────────────────────────────────
def admin_only(func):
    async def wrapper(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id not in ADMIN_IDS:
            await update.effective_message.reply_text("⛔ Admins only.")
            return
        return await func(update, ctx)
    wrapper.__name__ = func.__name__
    return wrapper


def access_required(func):
    """Allows admins always; other users need a valid key (activated via /start <key>)."""
    async def wrapper(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        uid = update.effective_user.id
        if not user_has_access(uid):
            await update.effective_message.reply_text(
                "🔑 <b>Access required.</b>\n\n"
                "You need a valid access key to use this bot.\n"
                "Use <code>/start YOUR_KEY</code> to activate your key.",
                parse_mode=ParseMode.HTML,
            )
            return
        return await func(update, ctx)
    wrapper.__name__ = func.__name__
    return wrapper


# ── Keyboards ─────────────────────────────────────────────────────────────────
def main_menu_kb(is_admin: bool = False):
    rows = [
        [InlineKeyboardButton("📋 List Bots",    callback_data="list"),
         InlineKeyboardButton("➕ Upload Bot",   callback_data="upload")],
        [InlineKeyboardButton("🤖 AI Fix File",  callback_data="ai_fix"),
         InlineKeyboardButton("💬 AI Chat",      callback_data="ai_chat")],
        [InlineKeyboardButton("📊 System Stats", callback_data="stats"),
         InlineKeyboardButton("⚡ Bot Speed",    callback_data="speed")],
        [InlineKeyboardButton("📞 Contact Owner", url=f"https://t.me/{OWNER_USERNAME}"),
         InlineKeyboardButton("🔄 Refresh",      callback_data="menu")],
    ]
    if is_admin:
        rows.append([
            InlineKeyboardButton("📢 Announce",   callback_data="announce"),
            InlineKeyboardButton("🔑 Gen Key",    callback_data="genkey"),
        ])
    return InlineKeyboardMarkup(rows)


def bot_menu_kb(name: str):
    ar = "ON ✅" if bots[name].get("auto_restart") else "OFF ❌"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("▶ Start",    callback_data=f"start|{name}"),
         InlineKeyboardButton("⏹ Stop",     callback_data=f"stop|{name}"),
         InlineKeyboardButton("🔄 Restart", callback_data=f"restart|{name}")],
        [InlineKeyboardButton("📄 Logs",    callback_data=f"logs|{name}"),
         InlineKeyboardButton("📊 Stats",   callback_data=f"res|{name}"),
         InlineKeyboardButton("🗑 Delete",  callback_data=f"delete|{name}")],
        [InlineKeyboardButton(f"🤖 AI Fix (from logs)", callback_data=f"ai_fix_bot|{name}")],
        [InlineKeyboardButton(f"🔁 Auto-restart: {ar}", callback_data=f"toggle_ar|{name}")],
        [InlineKeyboardButton("📦 Install Requirements",  callback_data=f"install_reqs|{name}")],
        [InlineKeyboardButton("« Back", callback_data="list")],
    ])


def bots_list_kb():
    rows = []
    for name in bots:
        st   = bot_status(name)
        icon = "✅" if "Running" in st else ("💀" if "Crashed" in st else "⏹")
        rows.append([InlineKeyboardButton(f"{icon} {name}", callback_data=f"bot|{name}")])
    rows.append([InlineKeyboardButton("« Back", callback_data="menu")])
    return InlineKeyboardMarkup(rows)


# ── Commands ──────────────────────────────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    is_admin = uid in ADMIN_IDS

    # Handle key activation: /start <key>
    if ctx.args and not is_admin:
        key = ctx.args[0].strip()
        result = activate_key(uid, key)
        if result == "ok":
            await update.message.reply_text(
                "✅ <b>Key activated!</b> You now have access to the bot.\n\n"
                "🤖 <b>MANJIRO HOSTING</b>\n"
                "Manage hosted bots and use AI to fix broken code.",
                parse_mode=ParseMode.HTML,
                reply_markup=main_menu_kb(is_admin=False),
            )
        elif result == "expired":
            await update.message.reply_text("❌ That key has expired. Ask an admin for a new one.")
        else:
            await update.message.reply_text("❌ Invalid key. Ask an admin for a valid access key.")
        return

    if not user_has_access(uid):
        await update.message.reply_text(
            "🔑 <b>Access required.</b>\n\n"
            "You need a valid access key to use this bot.\n"
            "Use <code>/start YOUR_KEY</code> to activate it.",
            parse_mode=ParseMode.HTML,
        )
        return

    await update.message.reply_text(
        "🤖 <b>MANJIRO HOSTING</b>\n\n"
        "Manage hosted bots and use AI to fix broken code.",
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu_kb(is_admin=is_admin),
    )


# (All actions are handled via inline buttons — no slash commands beyond /start)


# ── Message handler ───────────────────────────────────────────────────────────
async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id

    if not user_has_access(uid):
        return  # silently ignore — /start will show the gate

    doc  = update.message.document
    text = (update.message.text or "").strip()

    # ── Install requirements (typed text OR requirements.txt file)
    if uid in WAITING_INSTALL:
        install_info = WAITING_INSTALL.get(uid)
        bot_name = install_info["name"]
        upgrade  = install_info["upgrade"]

        # Accept a .txt file (requirements.txt)
        if doc and doc.file_name.endswith(".txt"):
            WAITING_INSTALL.pop(uid)
            tg_file = await doc.get_file()
            tmp_path = BOTS_DIR / f"_reqs_{uid}_{doc.file_name}"
            await tg_file.download_to_drive(str(tmp_path))
            content = tmp_path.read_text(errors="replace")
            tmp_path.unlink(missing_ok=True)

            pkg_list = parse_requirements_txt(content)
            if not pkg_list:
                await update.message.reply_text("⚠️ No valid packages found in that file.")
                return
            packages = "\n".join(pkg_list)

        elif not doc:
            WAITING_INSTALL.pop(uid)
            packages = text.strip()
            if not packages:
                await update.message.reply_text("⚠️ No packages entered. Cancelled.")
                return
        else:
            # Some other file type — ignore and wait
            await update.message.reply_text("⚠️ Please send a <b>.txt</b> requirements file or type package names.", parse_mode=ParseMode.HTML)
            return

        pkg_list_all   = packages.replace("\n", " ").split()
        pkg_count      = len(pkg_list_all)
        capped         = pkg_count > MAX_PACKAGES
        if capped:
            pkg_list_all = pkg_list_all[:MAX_PACKAGES]
            packages     = " ".join(pkg_list_all)
            pkg_count    = MAX_PACKAGES

        n_batches    = (pkg_count + BATCH_SIZE - 1) // BATCH_SIZE
        mode_label   = "⬆️ Upgraded" if upgrade else "📌 Normal (no upgrade)"
        cap_note     = f"\n⚠️ Capped at {MAX_PACKAGES} packages — extras ignored." if capped else ""
        thinking = await update.message.reply_text(
            f"📦 Installing {pkg_count} package(s) in {n_batches} batch(es) ({mode_label}):{cap_note}\n"
            f"<code>{packages}</code>\n\n⏳ This may take a moment…",
            parse_mode=ParseMode.HTML,
        )
        loop = asyncio.get_event_loop()
        success, output = await loop.run_in_executor(
            None, install_requirements, packages, upgrade
        )
        await thinking.delete()

        if len(output) > 3000:
            output = "…(truncated)\n" + output[-3000:]

        status_icon = "✅" if success else "❌"
        await update.message.reply_text(
            f"{status_icon} <b>pip install {'succeeded' if success else 'failed'}</b> "
            f"for <code>{bot_name}</code> ({mode_label})\n\n"
            f"<pre>{output}</pre>",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📦 Install more",      callback_data=f"install_reqs|{bot_name}"),
                 InlineKeyboardButton("« Bot menu",            callback_data=f"bot|{bot_name}")],
            ]),
        )
        return

    # ── Announcement broadcast (admin only)
    if uid in WAITING_ANNOUNCE and not doc:
        WAITING_ANNOUNCE.discard(uid)
        announcement = text
        keys = load_keys()
        now = datetime.utcnow()
        # Collect all user IDs with active (non-expired) keys
        recipients = set()
        for entry in keys.values():
            user_id = entry.get("used_by")
            if user_id and now <= datetime.fromisoformat(entry["expires"]):
                recipients.add(user_id)
        # Always include admins
        for aid in ADMIN_IDS:
            recipients.add(aid)
        recipients.discard(uid)  # don't send to yourself

        sent = 0
        failed = 0
        for recipient in recipients:
            try:
                await update.message.bot.send_message(
                    recipient,
                    f"📢 <b>Announcement</b>\n\n{announcement}",
                    parse_mode=ParseMode.HTML,
                )
                sent += 1
            except Exception:
                failed += 1

        await update.message.reply_text(
            f"📢 Announcement sent!\n✅ Delivered: <b>{sent}</b>  ❌ Failed: <b>{failed}</b>",
            parse_mode=ParseMode.HTML,
        )
        return

    # ── AI Chat (text only)
    if uid in WAITING_AI_CHAT and not doc:
        thinking = await update.message.reply_text("🤖 Thinking...")
        loop = asyncio.get_event_loop()
        history = WAITING_AI_CHAT[uid]
        try:
            reply = await loop.run_in_executor(None, _sync_ai_chat, history, text)
            # Keep history bounded
            if len(history) > 40:
                WAITING_AI_CHAT[uid] = history[-40:]
        except Exception as e:
            reply = f"❌ AI error: {e}"
        await thinking.delete()
        for chunk in [reply[i:i+4000] for i in range(0, len(reply), 4000)]:
            await update.message.reply_text(chunk)
        return

    if not doc:
        return

    # Allow .txt requirements files when in install mode; otherwise require .py
    if not doc.file_name.endswith(".py") and not (uid in WAITING_INSTALL and doc.file_name.endswith(".txt")):
        await update.message.reply_text("⚠️ Please send a .py file.")
        return

    # ── AI Fix mode
    if uid in WAITING_AI_FIX:
        WAITING_AI_FIX.discard(uid)
        thinking = await update.message.reply_text(
            "🤖 Analyzing your file with MANJI AI...\nThis takes 10–30 seconds."
        )
        loop = asyncio.get_event_loop()
        try:
            tg_file  = await doc.get_file()
            tmp_path = BOTS_DIR / f"_aifix_{uid}_{doc.file_name}"
            await tg_file.download_to_drive(str(tmp_path))
            code = tmp_path.read_text(errors="replace")
            tmp_path.unlink(missing_ok=True)

            ai_response = await loop.run_in_executor(None, _sync_ai_fix, code, "")
        except Exception as e:
            await thinking.delete()
            await update.message.reply_text(f"❌ AI error: {e}")
            return

        await thinking.delete()
        await _send_ai_fix_result(update.message, ctx, doc.file_name, ai_response)
        return

    # ── Upload / Host mode
    if uid in WAITING_UPLOAD:
        WAITING_UPLOAD.discard(uid)
        name = Path(doc.file_name).stem
        if not name.replace("_", "").replace("-", "").isalnum():
            await update.message.reply_text("⚠️ Invalid filename. Use letters, numbers, _ or -.")
            return

        dest    = BOTS_DIR / doc.file_name
        tg_file = await doc.get_file()
        await tg_file.download_to_drive(str(dest))

        bots[name] = {
            "file":         str(dest),
            "auto_restart": False,
            "uploaded":     time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        save_state()

        await update.message.reply_text(
            f"✅ <b>{name}</b> uploaded!\n\nStart it now?",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("▶ Start now", callback_data=f"start|{name}"),
                 InlineKeyboardButton("Later",        callback_data=f"bot|{name}")],
            ]),
        )


async def _send_ai_fix_result(message, ctx, filename: str, ai_response: str):
    """Shared logic: send explanation + fixed file document."""
    fixed_code = extract_fixed_code(ai_response)
    explanation = strip_code_block(ai_response)

    # Send explanation (chunked if long)
    for chunk in [explanation[i:i+4000] for i in range(0, len(explanation), 4000)]:
        await message.reply_text(chunk)

    if fixed_code:
        fixed_name = "fixed_" + filename
        fixed_path = BOTS_DIR / fixed_name
        fixed_path.write_text(fixed_code)
        # Store so callback can register it
        ctx.bot_data[f"fixed_path_{fixed_name}"] = str(fixed_path)

        with open(fixed_path, "rb") as f:
            await message.reply_document(
                document=f,
                filename=fixed_name,
                caption=(
                    "✅ <b>Fixed file ready!</b>\n"
                    "Download it or host it directly:"
                ),
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📤 Host this fixed bot",
                                         callback_data=f"host_fixed|{fixed_name}")],
                    [InlineKeyboardButton("🏠 Main Menu", callback_data="menu")],
                ]),
            )
    else:
        await message.reply_text(
            "⚠️ MANJI AI didn't return a clean code block.\n"
            "Check the explanation above for manual guidance."
        )


# ── Callback handler ──────────────────────────────────────────────────────────
async def handle_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data  = query.data
    uid   = update.effective_user.id

    if not user_has_access(uid):
        await query.answer("🔑 Access required. Use /start YOUR_KEY", show_alert=True)
        return

    # ── Main menu
    if data == "menu":
        await query.message.edit_text(
            "🤖 <b>MANJIRO HOSTING</b>\n\nChoose an option:",
            parse_mode=ParseMode.HTML,
            reply_markup=main_menu_kb(is_admin=(uid in ADMIN_IDS)),
        )
        return

    # ── List bots
    if data == "list":
        if not bots:
            await query.message.edit_text(
                "No bots hosted yet.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("➕ Upload Bot", callback_data="upload")],
                    [InlineKeyboardButton("« Back",        callback_data="menu")],
                ]),
            )
            return
        lines = [f"{bot_status(n)}  <code>{n}</code>" for n in bots]
        await query.message.edit_text(
            "📋 <b>Hosted Bots:</b>\n\n" + "\n".join(lines),
            parse_mode=ParseMode.HTML,
            reply_markup=bots_list_kb(),
        )
        return

    # ── Upload prompt
    if data == "upload":
        WAITING_UPLOAD.add(uid)
        WAITING_AI_FIX.discard(uid)
        WAITING_AI_CHAT.pop(uid, None)
        WAITING_ANNOUNCE.discard(uid)
        WAITING_INSTALL.pop(uid, None)
        await query.message.reply_text(
            "📤 Send me the <b>.py</b> file to host.\n"
            "The filename (without .py) becomes the bot name.",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ Cancel", callback_data="cancel")],
            ]),
        )
        return

    # ── AI Fix (file)
    if data == "ai_fix":
        WAITING_AI_FIX.add(uid)
        WAITING_UPLOAD.discard(uid)
        WAITING_AI_CHAT.pop(uid, None)
        WAITING_ANNOUNCE.discard(uid)
        WAITING_INSTALL.pop(uid, None)
        await query.message.reply_text(
            "🤖 <b>MANJI AI Code Fixer</b>\n\n"
            "Send me any <b>.py</b> file.\n"
            "MANJI AI will find all bugs and return a fixed version.",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ Cancel", callback_data="cancel")],
            ]),
        )
        return

    # ── AI Chat
    if data == "ai_chat":
        WAITING_AI_CHAT[uid] = []
        WAITING_UPLOAD.discard(uid)
        WAITING_AI_FIX.discard(uid)
        WAITING_ANNOUNCE.discard(uid)
        WAITING_INSTALL.pop(uid, None)
        await query.message.reply_text(
            "💬 <b>AI Chat Mode active</b>\n\n"
            "Ask me anything about Python or Telegram bots.\n"
            "Press the button below when done.",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔚 End Chat", callback_data="endchat")],
            ]),
        )
        return

    # ── Announce (admin only)
    if data == "announce":
        if uid not in ADMIN_IDS:
            await query.answer("⛔ Admins only.", show_alert=True)
            return
        WAITING_ANNOUNCE.add(uid)
        WAITING_UPLOAD.discard(uid)
        WAITING_AI_FIX.discard(uid)
        WAITING_AI_CHAT.pop(uid, None)
        WAITING_INSTALL.pop(uid, None)
        await query.message.reply_text(
            "📢 <b>Broadcast Announcement</b>\n\n"
            "Type your announcement message. It will be sent to all users with active keys.",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ Cancel", callback_data="cancel")],
            ]),
        )
        return

    # ── Generate key (admin only)
    if data == "genkey":
        if uid not in ADMIN_IDS:
            await query.answer("⛔ Admins only.", show_alert=True)
            return
        await query.message.edit_text(
            "🔑 <b>Generate Access Key</b>\n\nChoose duration:",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("1 Day",   callback_data="genkey|1d"),
                 InlineKeyboardButton("3 Days",  callback_data="genkey|3d")],
                [InlineKeyboardButton("8 Days",  callback_data="genkey|8d"),
                 InlineKeyboardButton("13 Days", callback_data="genkey|13d")],
                [InlineKeyboardButton("32 Days", callback_data="genkey|32d"),
                 InlineKeyboardButton("1 Year",  callback_data="genkey|1yr")],
                [InlineKeyboardButton("« Back",  callback_data="menu")],
            ]),
        )
        return

    if data.startswith("genkey|"):
        if uid not in ADMIN_IDS:
            await query.answer("⛔ Admins only.", show_alert=True)
            return
        duration = data.split("|", 1)[1]
        key = generate_key(duration)
        if key:
            expiry_dt  = datetime.utcnow() + KEY_DURATIONS[duration]
            expiry_str = expiry_dt.strftime("%Y-%m-%d %H:%M UTC")
            bot_me     = await ctx.bot.get_me()
            deep_link  = f"https://t.me/{bot_me.username}?start={key}"
            await query.message.reply_text(
                f"✅ <b>New Key Generated</b>\n\n"
                f"⏱ Duration: <b>{duration}</b>\n"
                f"📅 Expires: <b>{expiry_str}</b>\n\n"
                f"🔑 Key: <code>{key}</code>\n\n"
                f"🔗 Activation link:\n<code>{deep_link}</code>\n\n"
                f"Share the key or link with the user.",
                parse_mode=ParseMode.HTML,
            )
        else:
            await query.message.reply_text("❌ Invalid duration.")
        return

    # ── Cancel (clears all waiting states)
    if data == "cancel":
        WAITING_UPLOAD.discard(uid)
        WAITING_AI_FIX.discard(uid)
        WAITING_AI_CHAT.pop(uid, None)
        WAITING_ANNOUNCE.discard(uid)
        WAITING_INSTALL.pop(uid, None)
        await query.message.reply_text(
            "❌ Cancelled.",
            reply_markup=main_menu_kb(is_admin=(uid in ADMIN_IDS)),
        )
        return

    # ── End AI chat
    if data == "endchat":
        WAITING_AI_CHAT.pop(uid, None)
        await query.message.reply_text(
            "💬 Chat ended.",
            reply_markup=main_menu_kb(is_admin=(uid in ADMIN_IDS)),
        )
        return

    # ── Bot speed ping
    if data == "speed":
        t_start = time.monotonic()
        msg = await query.message.reply_text("⚡ Pinging...")
        elapsed_ms = (time.monotonic() - t_start) * 1000
        await msg.edit_text(
            f"⚡ <b>Bot Speed</b>\n\n"
            f"🏓 Response time: <b>{elapsed_ms:.0f} ms</b>\n"
            f"{'🟢 Excellent' if elapsed_ms < 300 else '🟡 Good' if elapsed_ms < 800 else '🔴 Slow'}",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Test Again", callback_data="speed"),
                 InlineKeyboardButton("« Back",        callback_data="menu")],
            ]),
        )
        return

    # ── System stats
    if data == "stats":
        cpu  = psutil.cpu_percent(interval=0.5)
        ram  = psutil.virtual_memory()
        disk = psutil.disk_usage(".")
        running = sum(1 for n in bots if "Running" in bot_status(n))
        await query.message.edit_text(
            f"📊 <b>System Stats</b>\n\n"
            f"🖥 CPU: <b>{cpu:.1f}%</b>\n"
            f"🧠 RAM: <b>{ram.used/1024**3:.1f}/{ram.total/1024**3:.1f} GB</b> ({ram.percent}%)\n"
            f"💾 Disk: <b>{disk.used/1024**3:.1f}/{disk.total/1024**3:.1f} GB</b> ({disk.percent}%)\n\n"
            f"🤖 Bots: <b>{len(bots)}</b>  ✅ Running: <b>{running}</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=main_menu_kb(is_admin=(uid in ADMIN_IDS)),
        )
        return

    # ── Host a previously AI-fixed file
    if data.startswith("host_fixed|"):
        fixed_name     = data.split("|", 1)[1]
        fixed_path_str = ctx.bot_data.get(f"fixed_path_{fixed_name}")
        if not fixed_path_str or not os.path.exists(fixed_path_str):
            await query.message.reply_text("⚠️ Fixed file not found. Please re-upload.")
            return
        name = Path(fixed_name).stem.removeprefix("fixed_")
        bots[name] = {
            "file":         fixed_path_str,
            "auto_restart": False,
            "uploaded":     time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        save_state()
        await query.message.reply_text(
            f"✅ <b>{name}</b> registered!\n\nStart it now?",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("▶ Start now", callback_data=f"start|{name}"),
                 InlineKeyboardButton("Later",        callback_data=f"bot|{name}")],
            ]),
        )
        return

    # ── Install requirements for a bot
    if data.startswith("install_reqs|"):
        _, name = data.split("|", 1)
        if name not in bots:
            await query.message.reply_text("⚠️ Bot not found.")
            return
        WAITING_UPLOAD.discard(uid)
        WAITING_AI_FIX.discard(uid)
        WAITING_AI_CHAT.pop(uid, None)
        WAITING_ANNOUNCE.discard(uid)
        # Show mode-selection menu — don't enter waiting state yet
        await query.message.reply_text(
            f"📦 <b>Install Requirements for <code>{name}</code></b>\n\n"
            "Choose install mode:",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬆️ Upgraded  (pip install --upgrade)",
                                      callback_data=f"install_mode|{name}|upgrade")],
                [InlineKeyboardButton("📌 Normal  (pip install, no upgrade)",
                                      callback_data=f"install_mode|{name}|normal")],
                [InlineKeyboardButton("❌ Cancel", callback_data="cancel")],
            ]),
        )
        return

    # ── Install mode chosen → ask for packages / file
    if data.startswith("install_mode|"):
        parts = data.split("|", 2)
        _, name, mode = parts
        if name not in bots:
            await query.message.reply_text("⚠️ Bot not found.")
            return
        upgrade = (mode == "upgrade")
        WAITING_INSTALL[uid] = {"name": name, "upgrade": upgrade}
        WAITING_UPLOAD.discard(uid)
        WAITING_AI_FIX.discard(uid)
        WAITING_AI_CHAT.pop(uid, None)
        WAITING_ANNOUNCE.discard(uid)
        mode_label = "⬆️ Upgraded" if upgrade else "📌 Normal"
        await query.message.reply_text(
            f"📦 <b>{mode_label} install for <code>{name}</code></b>\n\n"
            "Send a <b>requirements.txt</b> file  <i>or</i>  type package names (space/newline separated).\n\n"
            f"<b>Up to {MAX_PACKAGES} packages</b> per session — installed in batches of {BATCH_SIZE}.\n\n"
            "<i>Examples:</i>\n"
            "<code>requests aiohttp python-dotenv</code>\n"
            "<code>aiohttp==3.9.1</code>  ← pinned version works too",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ Cancel", callback_data="cancel")],
            ]),
        )
        return

    # ── Bot-specific actions (format: "action|botname")
    if "|" not in data:
        return

    action, name = data.split("|", 1)

    if name not in bots:
        await query.message.edit_text("⚠️ Bot not found.", reply_markup=main_menu_kb(is_admin=(uid in ADMIN_IDS)))
        return

    if action == "bot":
        st  = bot_status(name)
        res = bot_resources(name)
        info = bots[name]
        await query.message.edit_text(
            f"🤖 <b>{name}</b>\n\n"
            f"Status: {st}\n"
            f"Resources: {res}\n"
            f"File: <code>{info['file']}</code>\n"
            f"Uploaded: {info.get('uploaded', '—')}\n"
            f"Auto-restart: {'✅ ON' if info.get('auto_restart') else '❌ OFF'}",
            parse_mode=ParseMode.HTML,
            reply_markup=bot_menu_kb(name),
        )

    elif action == "start":
        ok, reason = start_bot(name)
        if ok:
            msg = f"▶ <b>{name}</b> started!"
        elif reason == "already_running":
            msg = f"⚠️ <b>{name}</b> already running."
        elif reason == "limit_reached":
            msg = f"🚫 Cannot start <b>{name}</b> — maximum of {MAX_RUNNING} bots already running.\nStop another bot first."
        else:
            msg = f"⚠️ Could not start <b>{name}</b>."
        await query.message.reply_text(msg, parse_mode=ParseMode.HTML)
        await query.message.edit_reply_markup(reply_markup=bot_menu_kb(name))

    elif action == "stop":
        ok  = stop_bot(name)
        msg = f"⏹ <b>{name}</b> stopped." if ok else f"⚠️ <b>{name}</b> not running."
        await query.message.reply_text(msg, parse_mode=ParseMode.HTML)
        await query.message.edit_reply_markup(reply_markup=bot_menu_kb(name))

    elif action == "restart":
        stop_bot(name)
        await asyncio.sleep(1)
        ok, reason = start_bot(name)
        if ok:
            msg = f"🔄 <b>{name}</b> restarted!"
        elif reason == "limit_reached":
            msg = f"🚫 <b>{name}</b> stopped but could not restart — {MAX_RUNNING} bots already running."
        else:
            msg = f"🔄 <b>{name}</b> stopped and queued for restart."
        await query.message.reply_text(msg, parse_mode=ParseMode.HTML)
        await query.message.edit_reply_markup(reply_markup=bot_menu_kb(name))

    elif action == "logs":
        log = read_log(name)
        if len(log) > 3800:
            log = "...(truncated)\n" + log[-3800:]
        await query.message.reply_text(
            f"📄 <b>Logs — {name}</b> (last {LOG_LINES} lines):\n\n<pre>{log}</pre>",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Refresh logs",      callback_data=f"logs|{name}"),
                 InlineKeyboardButton("🤖 AI Fix from logs",  callback_data=f"ai_fix_bot|{name}")],
                [InlineKeyboardButton("« Back",               callback_data=f"bot|{name}")],
            ]),
        )

    elif action == "res":
        res = bot_resources(name)
        await query.message.reply_text(
            f"📊 <b>{name}</b> resources: {res}",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Refresh", callback_data=f"res|{name}"),
                 InlineKeyboardButton("« Back",     callback_data=f"bot|{name}")],
            ]),
        )

    elif action == "toggle_ar":
        bots[name]["auto_restart"] = not bots[name].get("auto_restart", False)
        save_state()
        state = "ON ✅" if bots[name]["auto_restart"] else "OFF ❌"
        await query.message.reply_text(
            f"🔁 Auto-restart for <b>{name}</b>: {state}", parse_mode=ParseMode.HTML
        )
        await query.message.edit_reply_markup(reply_markup=bot_menu_kb(name))

    elif action == "delete":
        await query.message.edit_text(
            f"🗑 Delete <b>{name}</b>?\nThis stops it and removes the file.",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Yes, delete", callback_data=f"confirm_del|{name}"),
                 InlineKeyboardButton("❌ Cancel",       callback_data=f"bot|{name}")],
            ]),
        )

    elif action == "confirm_del":
        stop_bot(name)
        file_path = bots[name].get("file", "")
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
            lp = log_path(name)
            if lp.exists():
                lp.unlink()
        except Exception as e:
            logger.warning(f"Delete error: {e}")
        bots.pop(name, None)
        save_state()
        await query.message.edit_text(
            f"🗑 <b>{name}</b> deleted.",
            parse_mode=ParseMode.HTML,
            reply_markup=main_menu_kb(is_admin=(uid in ADMIN_IDS)),
        )

    # ── AI Fix from crash logs (one-click from bot menu or logs view)
    elif action == "ai_fix_bot":
        thinking = await query.message.reply_text(
            f"🤖 Reading <b>{name}</b>'s code + logs and asking MANJI AI to fix it...\n"
            "This takes 10–30 seconds.",
            parse_mode=ParseMode.HTML,
        )
        loop = asyncio.get_event_loop()
        try:
            bot_file = bots[name]["file"]
            code     = Path(bot_file).read_text(errors="replace")
            logs     = read_log(name, n=60)

            ai_response = await loop.run_in_executor(None, _sync_ai_fix, code, logs)
        except Exception as e:
            await thinking.delete()
            await query.message.reply_text(f"❌ AI error: {e}")
            return

        await thinking.delete()

        fixed_code = extract_fixed_code(ai_response)
        explanation = strip_code_block(ai_response)

        for chunk in [explanation[i:i+4000] for i in range(0, len(explanation), 4000)]:
            await query.message.reply_text(chunk)

        if fixed_code:
            orig_path = Path(bots[name]["file"])
            backup    = orig_path.with_suffix(".bak.py")
            # Backup original
            backup.write_text(orig_path.read_text(errors="replace"))
            # Overwrite with fix
            orig_path.write_text(fixed_code)

            await query.message.reply_text(
                f"✅ <b>{name}</b> has been fixed and saved!\n"
                f"Original backed up as <code>{backup.name}</code>\n\n"
                f"Restart now to apply the fix?",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 Restart now", callback_data=f"restart|{name}"),
                     InlineKeyboardButton("Later",           callback_data=f"bot|{name}")],
                ]),
            )
        else:
            await query.message.reply_text(
                "⚠️ MANJI AI didn't produce a clean code block. "
                "Check the explanation above for manual fixes."
            )


# ── Auto-restart watchdog ─────────────────────────────────────────────────────
async def watchdog(app: Application):
    while True:
        await asyncio.sleep(30)
        for name, info in list(bots.items()):
            if not info.get("auto_restart"):
                continue
            proc = procs.get(name)
            if proc is not None and proc.poll() is not None:
                logger.info(f"Auto-restarting crashed bot: {name}")
                ok, reason = start_bot(name)
                notice = (
                    f"♻️ Auto-restarted <b>{name}</b> (it crashed).\n"
                    f"Use 🤖 AI Fix from logs in its menu if it keeps crashing."
                    if ok else
                    f"⚠️ <b>{name}</b> crashed but could not auto-restart "
                    f"({reason}). Max {MAX_RUNNING} bots limit reached."
                )
                for aid in ADMIN_IDS:
                    try:
                        await app.bot.send_message(aid, notice, parse_mode=ParseMode.HTML)
                    except Exception:
                        pass


# ── Health-check server (for Render + UptimeRobot) ───────────────────────────
class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"MANJIRO HOSTING is alive!")

    def log_message(self, *args):
        pass   # silence access logs


def run_health_server():
    server = HTTPServer(("0.0.0.0", PORT), _HealthHandler)
    logger.info(f"Health-check server running on port {PORT}")
    server.serve_forever()


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    load_state()

    # Start health-check HTTP server in background thread
    t = threading.Thread(target=run_health_server, daemon=True)
    t.start()

    for name in bots:
        if bots[name].get("auto_restart"):
            logger.info(f"Auto-starting {name} on boot")
            ok, reason = start_bot(name)
            if not ok:
                logger.warning(f"Could not auto-start {name}: {reason}")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))

    app.add_handler(MessageHandler(
        (filters.Document.ALL | filters.TEXT) & ~filters.COMMAND,
        handle_message,
    ))
    app.add_handler(CallbackQueryHandler(handle_cb))

    async def post_init(application: Application):
        asyncio.create_task(watchdog(application))

    app.post_init = post_init

    logger.info("Host bot started — polling...")
    app.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()
