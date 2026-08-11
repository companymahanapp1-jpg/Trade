import asyncio
import html
import logging
import os
import re
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import aiosqlite
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN", "").strip()
OWNER_ID = int(os.getenv("OWNER_ID", "0") or 0)
DB = os.getenv("DB_PATH", "data/bot.db")
START_E = os.getenv("START_EMOJI_ID", "5935946026308342844")
SUPPORT_E = os.getenv("SUPPORT_EMOJI_ID", "5938359183748370657")
ADMIN_E = os.getenv("ADMIN_EMOJI_ID", "5935933089866846598")

# Central registry: these are the exact ReplyKeyboard button texts.
BUTTON_START = "شروع یادگیری"
BUTTON_SUPPORT = "پشتیبانی"
BUTTON_ADMIN = "پنل مدیریت"
BUTTON_BACK = "بازگشت"
BUTTON_YES = "بله، حذف شود"
BUTTON_NO = "لغو"
BUTTON_SKIP = "رد کردن"
BUTTON_NEXT = "بعدی"
BUTTON_CONFIRM = "تأیید"
BUTTON_CANCEL = "انصراف"
BUTTON_NEW = "عنوان جدید"
BUTTON_CONTINUE = "بله، ادامه بده"

# All non-static menu texts also live here, preventing accidental Handler collisions.
BTN = {
    "chapters": "📚 مدیریت فصل‌ها", "lessons": "🎬 مدیریت درس‌ها", "quizzes": "📝 مدیریت آزمون‌ها",
    "users": "👥 کاربران", "admins": "👑 ادمین‌ها", "tickets": "💬 پیام‌های پشتیبانی",
    "broadcast": "📣 پیام همگانی", "join": "🔐 جوین اجباری", "stats": "📊 آمار", "settings": "⚙️ تنظیمات",
    "add": "➕ افزودن", "list": "📋 لیست", "edit": "✏️ ویرایش", "delete": "🗑 حذف",
    "reorder": "↕️ تغییر ترتیب", "publish": "📢 انتشار/لغو انتشار", "quiz_manage": "📝 مدیریت آزمون",
    "quiz_create": "➕ ساخت آزمون", "quiz_list": "📋 لیست آزمون‌ها", "question_add": "➕ افزودن سؤال",
    "question_list": "📋 سؤال‌ها", "question_edit": "✏️ ویرایش سؤال", "question_delete": "🗑 حذف سؤال",
    "quiz_settings": "⚙️ تنظیم آزمون", "quiz_delete": "🗑 حذف آزمون", "question_reorder": "↕️ ترتیب سؤال‌ها",
    "user_search": "🔎 جستجوی کاربر", "user_list": "📋 لیست کاربران", "user_progress": "📈 Progress",
    "user_completed": "📚 درس‌های تکمیل‌شده", "user_scores": "🏆 نمرات آزمون", "user_reset": "🔄 Reset Progress",
    "user_block": "🚫 Block/Unblock", "user_access": "🔐 دسترسی دوره", "user_message": "📨 ارسال پیام",
    "admin_add": "➕ افزودن ادمین", "admin_delete": "🗑 حذف ادمین", "channel_add": "➕ افزودن کانال",
    "channel_delete": "🗑 حذف کانال", "channel_toggle": "🔄 فعال/غیرفعال", "channel_test": "🧪 تست عضویت",
    "settings_bot": "🤖 وضعیت ربات", "settings_join": "🔐 Forced Join", "settings_quiz": "📝 آزمون",
    "settings_reg": "📝 ثبت‌نام", "settings_start": "✏️ متن Start", "settings_support": "✏️ متن Support",
    "settings_lesson": "✏️ متن آموزش", "settings_retry": "🔁 منطق تلاش مجدد", "ticket_reply": "📨 پاسخ",
    "ticket_close": "🔒 بستن", "learn_quiz": "📝 شروع آزمون", "retry_quiz": "🔁 تلاش مجدد",
    "ch_add": "➕ افزودن فصل", "ch_list": "📋 لیست فصل‌ها", "ch_edit": "✏️ ویرایش فصل", "ch_delete": "🗑 حذف فصل", "ch_reorder": "↕️ تغییر ترتیب فصل‌ها",
    "less_add": "➕ افزودن درس", "less_list": "📋 لیست درس‌ها", "less_edit": "✏️ ویرایش درس", "less_delete": "🗑 حذف درس",
    "detail_ch_edit": "✏️ ویرایش همین فصل", "detail_ch_delete": "🗑 حذف همین فصل", "detail_ch_lessons": "🎬 درس‌های این فصل",
    "detail_l_edit": "✏️ ویرایش همین درس", "detail_l_delete": "🗑 حذف همین درس",
    "quiz_retry_mode": "تلاش مجدد", "quiz_complete_mode": "تکمیل بدون قبولی", "confirm_duration": "تأیید مدت",
    "q_edit_text": "متن سؤال", "q_edit_options": "گزینه‌ها", "q_edit_correct": "پاسخ صحیح", "q_edit_timer": "Timer",
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
log = logging.getLogger("trading_course_bot")
dp = Dispatcher()
QUIZ_TIMER_TASKS: dict[str, asyncio.Task] = {}


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def parse_id(text: str | None):
    m = re.search(r"#(\d+)", text or "")
    return int(m.group(1)) if m else None


def kb(text, style="primary", emoji_id=None):
    args = {"text": text}
    if style:
        args["style"] = style
    if emoji_id:
        args["icon_custom_emoji_id"] = str(emoji_id)
    return KeyboardButton(**args)


def markup(rows):
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, is_persistent=True)


def reserved_button_texts():
    values = {BUTTON_START, BUTTON_SUPPORT, BUTTON_ADMIN, BUTTON_BACK, BUTTON_YES, BUTTON_NO, BUTTON_SKIP, BUTTON_NEXT, BUTTON_CONFIRM, BUTTON_CANCEL, BUTTON_NEW, BUTTON_CONTINUE}
    values.update(BTN.values())
    return values


def validate_option_texts(options):
    cleaned = [x.strip() for x in options if x and x.strip()]
    if len(cleaned) < 2:
        return False, "حداقل دو گزینه لازم است."
    normalized = [x.casefold() for x in cleaned]
    if len(set(normalized)) != len(normalized):
        return False, "❌ گزینه‌ها نباید تکراری باشند. هر گزینه را فقط یک‌بار وارد کنید."
    if any(x in reserved_button_texts() for x in cleaned):
        return False, "❌ متن گزینه با یکی از دکمه‌های سیستمی تداخل دارد. متن دیگری انتخاب کنید."
    return True, cleaned


def row(*buttons):
    return [kb(*b) if isinstance(b, tuple) else kb(b) for b in buttons]


def back_kb(*extras):
    rows = [row(*extras)] if extras else []
    rows.append([kb(BUTTON_BACK, "danger")])
    return markup(rows)


def verify_keyboard_api():
    fields = getattr(KeyboardButton, "model_fields", {})
    missing = [x for x in ("style", "icon_custom_emoji_id") if x not in fields]
    if missing:
        raise RuntimeError("Installed aiogram lacks Telegram KeyboardButton fields: " + ", ".join(missing))


def user_kb(admin=False):
    rows = [[kb(BUTTON_START, "success", START_E), kb(BUTTON_SUPPORT, "primary", SUPPORT_E)]]
    if admin:
        rows.append([kb(BUTTON_ADMIN, "primary", ADMIN_E)])
    return markup(rows)


def admin_kb():
    return markup([
        [kb(BTN["chapters"], "success"), kb(BTN["lessons"], "success")],
        [kb(BTN["quizzes"], "primary"), kb(BTN["users"], "primary")],
        [kb(BTN["admins"], "primary"), kb(BTN["tickets"], "primary")],
        [kb(BTN["join"], "success"), kb(BTN["broadcast"], "primary")],
        [kb(BTN["stats"], "success"), kb(BTN["settings"], "primary")],
        [kb(BUTTON_BACK, "danger")],
    ])


def chapter_menu():
    return markup([[kb(BTN["add"], "success"), kb(BTN["list"], "primary")],
                   [kb(BTN["edit"], "primary"), kb(BTN["delete"], "danger")],
                   [kb(BTN["reorder"], "primary")], [kb(BUTTON_BACK, "danger")]])


def lesson_menu():
    return markup([[kb(LESS_ADD, "success"), kb(LESS_LIST, "primary")],
                   [kb(LESS_EDIT, "primary"), kb(LESS_DELETE, "danger")],
                   [kb(BTN["publish"], "success")], [kb(BUTTON_BACK, "danger")]])


def quiz_menu():
    return markup([[kb(BTN["quiz_create"], "success"), kb(BTN["quiz_list"], "primary")],
                   [kb(BTN["question_add"], "success"), kb(BTN["question_list"], "primary")],
                   [kb(BTN["question_edit"], "primary"), kb(BTN["question_delete"], "danger")],
                   [kb(BTN["question_reorder"], "primary")], [kb(BUTTON_BACK, "danger")]])


class S(StatesGroup):
    # user
    learn_chapter = State(); learn_lesson = State(); learn_after_content = State(); quiz_answer = State();
    support_message = State()
    # chapter
    ch_title = State(); ch_dup = State(); ch_desc = State(); ch_select = State(); ch_info = State(); ch_edit_select = State(); ch_edit_title = State(); ch_edit_desc = State(); ch_delete_select = State(); ch_delete_confirm = State(); ch_reorder_select = State(); ch_reorder_target = State()
    # lesson
    l_title = State(); l_dup = State(); l_chapter = State(); l_desc = State(); l_content = State(); l_duration = State(); l_select = State(); l_info = State(); l_edit_select = State(); l_edit_field = State(); l_edit_value = State(); l_edit_chapter = State(); l_edit_content = State(); l_delete_select = State(); l_delete_confirm = State(); l_publish_select = State()
    # quiz
    qz_lesson = State(); qz_pass = State(); qz_retry = State(); qz_select = State(); qz_delete_confirm = State(); qz_question_select = State(); q_text = State(); q_options = State(); q_correct = State(); q_timer = State(); q_edit_select = State(); q_edit_field = State(); q_edit_text = State(); q_edit_options = State(); q_edit_correct = State(); q_edit_timer = State(); q_delete_select = State(); q_delete_confirm = State(); q_reorder_select = State(); q_reorder_target = State();
    # users
    user_select = State(); user_search = State(); user_profile = State(); user_message = State()
    # admin
    admin_add = State(); admin_delete = State(); admin_delete_confirm = State()
    # join
    channel_add_username = State(); channel_add_title = State(); channel_delete = State(); channel_toggle = State()
    # broadcast/settings
    broadcast = State(); settings_value = State()
    # tickets
    ticket_select = State(); ticket_reply = State()


# ---------------- Database ----------------

async def db():
    Path(DB).parent.mkdir(parents=True, exist_ok=True)
    c = await aiosqlite.connect(DB)
    c.row_factory = aiosqlite.Row
    await c.execute("PRAGMA foreign_keys=ON")
    return c


async def init_db():
    x = await db()
    await x.executescript("""
    CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT,telegram_id INTEGER UNIQUE NOT NULL,username TEXT,first_name TEXT,last_name TEXT,blocked INTEGER DEFAULT 0,course_access INTEGER DEFAULT 1,last_lesson_id INTEGER DEFAULT 0,created_at TEXT DEFAULT CURRENT_TIMESTAMP,last_activity TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS admins(telegram_id INTEGER PRIMARY KEY,role TEXT DEFAULT 'admin',created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS chapters(id INTEGER PRIMARY KEY AUTOINCREMENT,title TEXT NOT NULL,description TEXT DEFAULT '',position INTEGER DEFAULT 0,active INTEGER DEFAULT 1,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS lessons(id INTEGER PRIMARY KEY AUTOINCREMENT,chapter_id INTEGER REFERENCES chapters(id) ON DELETE SET NULL,title TEXT NOT NULL,description TEXT DEFAULT '',position INTEGER DEFAULT 0,content_type TEXT DEFAULT '',content_file_id TEXT DEFAULT '',content_text TEXT DEFAULT '',telegram_message_id INTEGER DEFAULT 0,duration INTEGER DEFAULT 0,active INTEGER DEFAULT 1,published INTEGER DEFAULT 0,created_at TEXT DEFAULT CURRENT_TIMESTAMP,video_file_id TEXT DEFAULT '');
    CREATE TABLE IF NOT EXISTS quizzes(id INTEGER PRIMARY KEY AUTOINCREMENT,lesson_id INTEGER UNIQUE REFERENCES lessons(id) ON DELETE CASCADE,pass_percent INTEGER DEFAULT 70,time_limit INTEGER DEFAULT 180,retry_mode TEXT DEFAULT 'retry',created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS questions(id INTEGER PRIMARY KEY AUTOINCREMENT,quiz_id INTEGER REFERENCES quizzes(id) ON DELETE CASCADE,text TEXT NOT NULL,position INTEGER DEFAULT 0,timer INTEGER DEFAULT 30);
    CREATE TABLE IF NOT EXISTS options(id INTEGER PRIMARY KEY AUTOINCREMENT,question_id INTEGER REFERENCES questions(id) ON DELETE CASCADE,text TEXT NOT NULL,is_correct INTEGER DEFAULT 0);
    CREATE TABLE IF NOT EXISTS progress(user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,lesson_id INTEGER REFERENCES lessons(id) ON DELETE CASCADE,video_started TEXT,video_done INTEGER DEFAULT 0,quiz_passed INTEGER DEFAULT 0,completed_at TEXT,PRIMARY KEY(user_id,lesson_id));
    CREATE TABLE IF NOT EXISTS attempts(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,quiz_id INTEGER,score INTEGER DEFAULT 0,passed INTEGER DEFAULT 0,started_at TEXT,finished_at TEXT);
    CREATE TABLE IF NOT EXISTS channels(id INTEGER PRIMARY KEY AUTOINCREMENT,title TEXT NOT NULL,chat_id TEXT NOT NULL,username TEXT DEFAULT '',link TEXT DEFAULT '',active INTEGER DEFAULT 1);
    CREATE TABLE IF NOT EXISTS tickets(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,status TEXT DEFAULT 'open',created_at TEXT DEFAULT CURRENT_TIMESTAMP,closed_at TEXT);
    CREATE TABLE IF NOT EXISTS ticket_messages(id INTEGER PRIMARY KEY AUTOINCREMENT,ticket_id INTEGER,sender_id INTEGER,text TEXT DEFAULT '',content_type TEXT DEFAULT 'text',telegram_message_id INTEGER DEFAULT 0,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    """)
    migrations = {
        "users": [("last_name", "TEXT"), ("course_access", "INTEGER DEFAULT 1"), ("last_lesson_id", "INTEGER DEFAULT 0"), ("last_activity", "TEXT")],
        "lessons": [("content_type", "TEXT DEFAULT ''"), ("content_file_id", "TEXT DEFAULT ''"), ("content_text", "TEXT DEFAULT ''"), ("telegram_message_id", "INTEGER DEFAULT 0"), ("published", "INTEGER DEFAULT 0"), ("created_at", "TEXT DEFAULT CURRENT_TIMESTAMP"), ("video_file_id", "TEXT DEFAULT ''")],
        "questions": [("timer", "INTEGER DEFAULT 30")], "tickets": [("closed_at", "TEXT")],
        "ticket_messages": [("content_type", "TEXT DEFAULT 'text'"), ("telegram_message_id", "INTEGER DEFAULT 0")],
    }
    for table, cols in migrations.items():
        c = await x.execute(f"PRAGMA table_info({table})")
        have = {r["name"] for r in await c.fetchall()}
        for name, typ in cols:
            if name not in have:
                await x.execute(f"ALTER TABLE {table} ADD COLUMN {name} {typ}")
    try:
        await x.execute("UPDATE lessons SET content_type='video',content_file_id=video_file_id WHERE (content_file_id IS NULL OR content_file_id='') AND video_file_id IS NOT NULL AND video_file_id<>''")
    except Exception:
        pass
    defaults = {
        "registration_enabled":"1","quiz_enabled":"1","forced_join_enabled":"1","bot_enabled":"1",
        "start_text":"آکادمی آموزش ترید؛ آموزش‌ها مرحله‌به‌مرحله هستند.",
        "support_text":"پیامت را ارسال کن تا پشتیبانی بررسی کند.",
        "lesson_text":"📚 از منوی زیر فصل موردنظر خود را انتخاب کنید.",
        "default_retry_mode":"retry",
    }
    for k,v in defaults.items(): await x.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)",(k,v))
    await x.commit(); await x.close()


async def setting(key, default=""):
    x=await db(); c=await x.execute("SELECT value FROM settings WHERE key=?",(key,)); r=await c.fetchone(); await x.close(); return r["value"] if r else default


async def set_setting(key,value):
    x=await db(); await x.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(key,str(value))); await x.commit(); await x.close()


async def is_admin(uid):
    if uid == OWNER_ID: return True
    x=await db(); c=await x.execute("SELECT 1 FROM admins WHERE telegram_id=?",(uid,)); r=await c.fetchone(); await x.close(); return bool(r)


async def ensure_user(u):
    if await setting("registration_enabled","1") != "1":
        # Existing users still update activity; new-user registration is blocked by caller.
        x=await db(); c=await x.execute("SELECT * FROM users WHERE telegram_id=?",(u.id,)); r=await c.fetchone(); await x.close(); return r
    n=now_iso(); x=await db();
    await x.execute("""INSERT INTO users(telegram_id,username,first_name,last_name,last_activity) VALUES(?,?,?,?,?)
        ON CONFLICT(telegram_id) DO UPDATE SET username=excluded.username,first_name=excluded.first_name,last_name=excluded.last_name,last_activity=excluded.last_activity""",(u.id,u.username,u.first_name,u.last_name,n))
    await x.commit(); c=await x.execute("SELECT * FROM users WHERE telegram_id=?",(u.id,)); r=await c.fetchone(); await x.close(); return r


async def get_user_by_tid(tid):
    x=await db(); c=await x.execute("SELECT * FROM users WHERE telegram_id=?",(tid,)); r=await c.fetchone(); await x.close(); return r


# ---------------- navigation ----------------

async def nav_push(state, screen):
    d = await state.get_data()
    stack = list(d.get("nav", []))
    if not stack or stack[-1] != screen:
        stack.append(screen)
    await state.update_data(nav=stack)


async def nav_replace(state, screen):
    d = await state.get_data()
    stack = list(d.get("nav", []))
    if stack:
        stack[-1] = screen
    else:
        stack = [screen]
    await state.update_data(nav=stack)


async def nav_pop(state):
    d = await state.get_data()
    stack = list(d.get("nav", []))
    if len(stack) <= 1:
        return None
    stack.pop()
    await state.update_data(nav=stack)
    return stack[-1]


async def cancel_quiz_timer(state):
    d = await state.get_data()
    session = d.get("quiz_session_id")
    if session:
        task = QUIZ_TIMER_TASKS.pop(session, None)
        if task and not task.done():
            task.cancel()


async def go_back(m, state):
    await cancel_quiz_timer(state)
    previous = await nav_pop(state)
    if previous is None:
        await state.clear()
        return await home(m)
    if previous == "learn_home" or previous == "learn_chapters":
        return await show_learning_chapters(m, state, push=False)
    if previous.startswith("learn_lessons:"):
        return await show_learning_lessons(m, state, int(previous.split(":", 1)[1]), push=False)
    if previous.startswith("learn_lesson:"):
        d = await state.get_data()
        return await show_learning_lessons(m, state, int(d.get("learn_chapter_id") or 0), push=False)
    if previous == "admin":
        await state.clear()
        return await m.answer("👑 پنل مدیریت", reply_markup=admin_kb())
    if previous == "chapter_add": return await chapter_menu_page(m, state, push=False)
    if previous == "chapter_edit_select": return await chapter_menu_page(m, state, push=False)
    if previous == "chapter_edit_title":
        return await m.answer("عنوان جدید را ارسال کنید:", reply_markup=back_kb())
    if previous == "chapter_delete_select": return await chapter_menu_page(m, state, push=False)
    if previous == "chapter_reorder_select": return await chapter_menu_page(m, state, push=False)
    if previous == "lesson_add": return await lesson_menu_page(m, state, push=False)
    if previous == "lesson_edit_select": return await lesson_menu_page(m, state, push=False)
    if previous == "lesson_edit_field": return await show_lesson(m, state, int((await state.get_data()).get("selected_lesson")), push=False)
    if previous == "quiz_question_add": return await open_quiz_for_lesson(m, state, int((await state.get_data()).get("selected_lesson")), push=False)
    if previous == "quiz_question_edit": return await open_quiz_for_lesson(m, state, int((await state.get_data()).get("selected_lesson")), push=False)
    if previous == "quiz_question_edit_field": return await m.answer("چه چیزی را ویرایش می‌کنید؟", reply_markup=markup([[kb(BTN["q_edit_text"]),kb(BTN["q_edit_options"])],[kb(BTN["q_edit_correct"]),kb(BTN["q_edit_timer"])],[kb(BUTTON_BACK,"danger")]]))
    if previous == "user_message": return await show_user(m, state, int((await state.get_data()).get("selected_user")), push=False)
    if previous == "chapter_menu": return await chapter_menu_page(m, state, push=False)
    if previous.startswith("chapter_info:"): return await show_chapter(m, state, int(previous.split(":",1)[1]), push=False)
    if previous == "lesson_menu": return await lesson_menu_page(m, state, push=False)
    if previous.startswith("lesson_info:"): return await show_lesson(m, state, int(previous.split(":",1)[1]), push=False)
    if previous == "quiz_menu": return await quiz_menu_page(m, state, push=False)
    if previous.startswith("quiz_for_lesson:"): return await open_quiz_for_lesson(m, state, int(previous.split(":",1)[1]), push=False)
    if previous.startswith("user_profile:"): return await show_user(m, state, int(previous.split(":",1)[1]), push=False)
    if previous == "users": return await users_menu(m, state, push=False)
    if previous == "tickets": return await support_admin(m, state, push=False)
    if previous == "ticket_info": return await support_admin(m, state, push=False)
    if previous == "admins": return await admins_page(m, state, push=False)
    if previous == "channels": return await channels_page(m, state, push=False)
    if previous == "settings": return await settings_page(m, state, push=False)
    await state.clear()
    return await home(m)


# ---------------- content/join ----------------

def extract_content(m):
    if m.video: return "video",m.video.file_id,"",m.video.duration or 0
    if m.document: return "document",m.document.file_id,"",0
    if m.photo: return "photo",m.photo[-1].file_id,"",0
    if m.audio: return "audio",m.audio.file_id,"",m.audio.duration or 0
    if m.voice: return "voice",m.voice.file_id,"",0
    if m.animation: return "animation",m.animation.file_id,"",m.animation.duration or 0
    if m.video_note: return "video_note",m.video_note.file_id,"",0
    if m.sticker: return "sticker",m.sticker.file_id,"",0
    if m.text: return "text","",m.text,0
    return None,"","",0


async def send_saved_content(bot,chat_id,lesson):
    t=lesson["content_type"]; fid=lesson["content_file_id"]; text=lesson["content_text"]; cap=lesson["description"] or None
    if t=="video": return await bot.send_video(chat_id,fid,caption=cap)
    if t=="document": return await bot.send_document(chat_id,fid,caption=cap)
    if t=="photo": return await bot.send_photo(chat_id,fid,caption=cap)
    if t=="audio": return await bot.send_audio(chat_id,fid,caption=cap)
    if t=="voice": return await bot.send_voice(chat_id,fid)
    if t=="animation": return await bot.send_animation(chat_id,fid,caption=cap)
    if t=="video_note": return await bot.send_video_note(chat_id,fid)
    if t=="sticker": return await bot.send_sticker(chat_id,fid)
    return await bot.send_message(chat_id,text or "")


async def check_required_join(bot,uid):
    if await setting("forced_join_enabled","1") != "1": return []
    x=await db(); c=await x.execute("SELECT * FROM channels WHERE active=1 ORDER BY id"); channels=await c.fetchall(); await x.close(); missing=[]
    for ch in channels:
        try:
            member=await bot.get_chat_member(ch["chat_id"],uid)
            if member.status in ("left","kicked"): missing.append(ch)
        except Exception: missing.append(ch)
    return missing


async def access_user(m):
    u=await ensure_user(m.from_user)
    if not u:
        await m.answer("⛔ ثبت‌نام در حال حاضر غیرفعال است."); return None
    if u["blocked"]: await m.answer("⛔ دسترسی شما مسدود شده است."); return None
    if not u["course_access"]: await m.answer("⛔ دسترسی شما به دوره محدود شده است."); return None
    missing=await check_required_join(m.bot,m.from_user.id)
    if missing:
        lines=[]
        for c in missing:
            link=c["link"] or (f"https://t.me/{c['username'].lstrip('@')}" if c["username"] else str(c["chat_id"]))
            lines.append(f"📢 {html.escape(c['title'])}: {html.escape(link)}")
        await m.answer("🔐 <b>عضویت اجباری</b>\n\nابتدا عضو کانال‌های زیر شوید و دوباره تلاش کنید:\n\n"+"\n".join(lines),parse_mode="HTML")
        return None
    return u


# ---------------- start/user learning ----------------

async def home(m):
    if await setting("bot_enabled","1")!="1" and not await is_admin(m.from_user.id): return await m.answer("⛔ ربات موقتاً غیرفعال است.")
    text=await setting("start_text")
    await m.answer(f"✨ <b>آکادمی آموزش ترید</b>\n\n{html.escape(text)}",parse_mode="HTML",reply_markup=user_kb(await is_admin(m.from_user.id)))


@dp.message(CommandStart())
async def start(m,state):
    await state.clear(); u=await ensure_user(m.from_user)
    if not u and not await is_admin(m.from_user.id): return await m.answer("⛔ ثبت‌نام در حال حاضر غیرفعال است.")
    if u and u["blocked"]: return await m.answer("⛔ دسترسی شما مسدود شده است.")
    missing=await check_required_join(m.bot,m.from_user.id) if u else []
    if missing:
        lines=[f"📢 {html.escape(c['title'])}: {html.escape(c['link'] or ('https://t.me/'+c['username'].lstrip('@') if c['username'] else c['chat_id']))}" for c in missing]
        return await m.answer("🔐 <b>عضویت اجباری</b>\n\n"+"\n".join(lines),parse_mode="HTML",reply_markup=user_kb(await is_admin(m.from_user.id)))
    await home(m)


@dp.message(F.text == BUTTON_ADMIN)
async def admin_panel_entry(m,state):
    # This entry point is intentionally restricted to Owner/Admin accounts.
    if not await is_admin(m.from_user.id):
        return
    await state.clear()
    await state.update_data(nav=["admin"])
    await m.answer("👑 پنل مدیریت", reply_markup=admin_kb())


@dp.message(F.text == BUTTON_BACK)
async def global_back(m,state):
    # Registered before all state-specific handlers so Back always wins over
    # generic FSM handlers such as @dp.message(S.some_state).
    return await go_back(m, state)


@dp.message(F.text == BUTTON_START)
async def learning_start(m,state):
    if not await access_user(m): return
    await state.clear(); await state.update_data(nav=["learn_home","learn_chapters"])
    await show_learning_chapters(m,state,push=False)


async def published_chapters():
    x=await db(); c=await x.execute("SELECT c.* FROM chapters c WHERE c.active=1 AND EXISTS(SELECT 1 FROM lessons l WHERE l.chapter_id=c.id AND l.published=1) ORDER BY c.position,c.id"); r=await c.fetchall(); await x.close(); return r


async def show_learning_chapters(m,state,push=True):
    if push: await nav_push(state,"learn_chapters")
    rows=await published_chapters()
    # Unassigned lessons are a first-class chapter-like option.
    x=await db(); c=await x.execute("SELECT COUNT(*) n FROM lessons WHERE chapter_id IS NULL AND published=1"); unassigned=(await c.fetchone())["n"]>0; await x.close()
    buttons=[[kb(f"📚 #{r['id']} | {r['title']}","success")] for r in rows]
    if unassigned: buttons.append([kb("📚 بدون فصل","primary")])
    buttons.append([kb(BUTTON_BACK,"danger")])
    await state.set_state(S.learn_chapter)
    await m.answer(await setting("lesson_text", "📚 از منوی زیر فصل موردنظر خود را انتخاب کنید."),reply_markup=markup(buttons))


@dp.message(S.learn_chapter)
async def learning_chapter_select(m,state):
    cid=parse_id(m.text)
    if m.text=="📚 بدون فصل": cid=0
    if cid is None: return await m.answer("لطفاً فصل را از کیبورد انتخاب کنید.")
    await show_learning_lessons(m,state,cid,push=True)


async def show_learning_lessons(m,state,cid,push=True):
    if push: await nav_push(state,f"learn_lessons:{cid}")
    x=await db()
    if cid==0: c=await x.execute("SELECT l.* FROM lessons l WHERE l.chapter_id IS NULL AND l.published=1 ORDER BY l.position,l.id")
    else: c=await x.execute("SELECT l.* FROM lessons l WHERE l.chapter_id=? AND l.published=1 ORDER BY l.position,l.id",(cid,))
    rows=await c.fetchall(); await x.close()
    buttons=[[kb(f"🎬 #{r['id']} | {r['title']}","primary")] for r in rows]
    await state.set_state(S.learn_lesson)
    await m.answer("🎬 درس موردنظر را انتخاب کنید:",reply_markup=markup(buttons+[[kb(BUTTON_BACK,"danger")]]))


async def lesson_is_unlocked(uid, lesson_id):
    x = await db()
    c = await x.execute("""SELECT l.id,l.chapter_id,l.position,COALESCE(c.position,2147483647) AS chapter_position,
             COALESCE(p.video_done,0) AS done,COALESCE(p.quiz_passed,0) AS passed
        FROM lessons l LEFT JOIN chapters c ON c.id=l.chapter_id
        LEFT JOIN progress p ON p.lesson_id=l.id AND p.user_id=?
        WHERE l.published=1 AND l.active=1 AND (l.chapter_id IS NULL OR c.active=1)
        ORDER BY chapter_position,l.position,l.id""", (uid,))
    rows = await c.fetchall()
    idx = next((i for i,r in enumerate(rows) if r["id"] == lesson_id), None)
    if idx is None:
        await x.close(); return False
    if idx == 0:
        await x.close(); return True
    prev = rows[idx-1]
    c = await x.execute("SELECT id FROM quizzes WHERE lesson_id=?", (prev["id"],))
    quiz = await c.fetchone()
    await x.close()
    # A lesson with a quiz is complete only after that quiz is passed.
    return bool(prev["passed"] if quiz else prev["done"])


@dp.message(S.learn_lesson)
async def learning_lesson_select(m,state):
    lid=parse_id(m.text)
    if lid is None: return await m.answer("لطفاً درس را از کیبورد انتخاب کنید.")
    u=await access_user(m)
    if not u: return
    if not await lesson_is_unlocked(u["id"],lid):
        return await m.answer("🔒 این درس هنوز برای شما باز نشده است. ابتدا درس قبلی را تکمیل کنید.")
    x=await db(); c=await x.execute("SELECT l.*,c.title ct FROM lessons l LEFT JOIN chapters c ON c.id=l.chapter_id WHERE l.id=? AND l.published=1",(lid,)); lesson=await c.fetchone();
    if not lesson: await x.close(); return await m.answer("❌ درس پیدا نشد.")
    c=await x.execute("SELECT id FROM users WHERE telegram_id=?",(m.from_user.id,)); user=await c.fetchone();
    c=await x.execute("SELECT * FROM quizzes WHERE lesson_id=?",(lid,)); quiz=await c.fetchone(); await x.commit(); await x.close()
    await nav_push(state,f"learn_lesson:{lid}"); await state.update_data(learn_lesson_id=lid,learn_chapter_id=lesson["chapter_id"] or 0)
    await send_saved_content(m.bot,m.chat.id,lesson)
    x=await db(); await x.execute("INSERT INTO progress(user_id,lesson_id,video_started) VALUES(?,?,?) ON CONFLICT(user_id,lesson_id) DO UPDATE SET video_started=COALESCE(progress.video_started,excluded.video_started)",(user["id"],lid,now_iso())); await x.execute("UPDATE users SET last_lesson_id=?,last_activity=? WHERE id=?",(lid,now_iso(),user["id"])); await x.commit(); await x.close()
    if quiz and await setting("quiz_enabled","1")=="1":
        await state.set_state(S.learn_after_content); await m.answer("📝 محتوای درس ارسال شد. برای ادامه آزمون را شروع کنید.",reply_markup=markup([[kb(BTN["learn_quiz"],"success")],[kb(BUTTON_BACK,"danger")]]))
    else:
        await complete_lesson(u["id"],lid,False); await m.answer("✅ درس تکمیل شد.",reply_markup=back_kb())


async def complete_lesson(uid, lid, quiz_passed=False, has_quiz=False):
    completed_at = now_iso() if (not has_quiz or quiz_passed) else None
    x = await db()
    await x.execute("""INSERT INTO progress(user_id,lesson_id,video_done,quiz_passed,completed_at) VALUES(?,?,?,?,?)
        ON CONFLICT(user_id,lesson_id) DO UPDATE SET video_done=1,quiz_passed=excluded.quiz_passed,completed_at=excluded.completed_at""", (uid,lid,1,int(quiz_passed),completed_at))
    await x.commit(); await x.close()


@dp.message(S.learn_after_content, F.text == BTN["learn_quiz"])
async def learner_quiz_start(m,state):
    d=await state.get_data(); lid=d.get("learn_lesson_id");
    if not lid:return await m.answer("آزمون انتخاب نشده است.")
    x=await db(); c=await x.execute("SELECT * FROM quizzes WHERE lesson_id=?",(lid,)); quiz=await c.fetchone(); c=await x.execute("SELECT * FROM questions WHERE quiz_id=? ORDER BY position,id",(quiz["id"],)) if quiz else None; qs=await c.fetchall() if c else []; await x.close()
    if not quiz or not qs:return await m.answer("این درس هنوز سؤال آزمون ندارد.")
    await cancel_quiz_timer(state); await state.update_data(quiz_id=quiz["id"],q_index=0,score=0,started=now_iso(),quiz_lesson_id=lid,quiz_session_id=uuid.uuid4().hex,question_token=None,question_id=None)
    await send_question(m.bot,m.chat.id,m.from_user.id,state)


async def send_question(bot, chat_id, uid, state):
    d = await state.get_data()
    x = await db()
    c = await x.execute("SELECT * FROM questions WHERE quiz_id=? ORDER BY position,id", (d["quiz_id"],))
    qs = await c.fetchall(); idx = d.get("q_index", 0)
    if idx >= len(qs):
        await x.close(); return await finish_quiz(bot, chat_id, uid, state)
    q = qs[idx]
    c = await x.execute("SELECT * FROM options WHERE question_id=? ORDER BY id", (q["id"],))
    opts = await c.fetchall(); await x.close()
    await cancel_quiz_timer(state)
    session = d.get("quiz_session_id") or uuid.uuid4().hex
    question_token = uuid.uuid4().hex
    deadline = asyncio.get_running_loop().time() + q["timer"]
    await state.set_state(S.quiz_answer)
    await state.update_data(quiz_session_id=session, question_token=question_token, question_id=q["id"], deadline=deadline)
    rows = [[kb(f"🔹 {o['text']}", "primary")] for o in opts]
    await bot.send_message(chat_id, f"❓ <b>{html.escape(q['text'])}</b>\n\n⏱ {q['timer']} ثانیه", parse_mode="HTML", reply_markup=markup(rows + [[kb(BUTTON_BACK, "danger")]]))
    task = asyncio.create_task(question_timeout(bot, chat_id, uid, state, q["id"], q["timer"], session, question_token))
    QUIZ_TIMER_TASKS[session] = task


async def question_timeout(bot, chat_id, uid, state, qid, seconds, session, question_token):
    try:
        await asyncio.sleep(max(1, seconds))
        d = await state.get_data()
        if d.get("quiz_session_id") != session or d.get("question_token") != question_token or d.get("question_id") != qid:
            return
        if d.get("deadline", 0) > asyncio.get_running_loop().time():
            return
        await state.update_data(q_index=d.get("q_index", 0) + 1, question_id=None, question_token=None)
        await bot.send_message(chat_id, "⏰ زمان این سؤال تمام شد.")
        await send_question(bot, chat_id, uid, state)
    except asyncio.CancelledError:
        return
    finally:
        if QUIZ_TIMER_TASKS.get(session) is asyncio.current_task():
            QUIZ_TIMER_TASKS.pop(session, None)


@dp.message(S.quiz_answer)
async def quiz_answer(m,state):
    d=await state.get_data(); qid=d.get("question_id")
    if not qid:return
    if d.get("deadline",0)<asyncio.get_running_loop().time():return
    x=await db(); c=await x.execute("SELECT * FROM options WHERE question_id=?",(qid,)); opts=await c.fetchall(); chosen=(m.text or "").replace("🔹 ","",1); opt=next((o for o in opts if o["text"]==chosen),None); await x.close()
    if not opt:return await m.answer("گزینه را از کیبورد انتخاب کنید.")
    score=d.get("score",0)+int(opt["is_correct"]); await state.update_data(score=score,question_id=None,q_index=d.get("q_index",0)+1)
    await m.answer("✅ پاسخ ثبت شد." if opt["is_correct"] else "❌ پاسخ ثبت شد.")
    await send_question(m.bot,m.chat.id,m.from_user.id,state)


async def finish_quiz(bot,chat_id,uid,state):
    d=await state.get_data();
    await cancel_quiz_timer(state)
    x=await db(); c=await x.execute("SELECT * FROM quizzes WHERE id=?",(d["quiz_id"],)); quiz=await c.fetchone(); c=await x.execute("SELECT COUNT(*) n FROM questions WHERE quiz_id=?",(d["quiz_id"],)); total=(await c.fetchone())["n"]; user=await get_user_by_tid(uid); score=d.get("score",0); passed=total>0 and score*100//total>=quiz["pass_percent"]; await x.execute("INSERT INTO attempts(user_id,quiz_id,score,passed,started_at,finished_at) VALUES(?,?,?,?,?,?)",(user["id"],quiz["id"],score,int(passed),d.get("started"),now_iso())); await x.commit(); await x.close()
    await complete_lesson(user["id"], d["quiz_lesson_id"], passed, has_quiz=True)
    nav = list(d.get("nav", []))
    if not nav: nav=[f"learn_lessons:{d['quiz_lesson_id']}"]
    await state.clear()
    await state.update_data(nav=nav, quiz_lesson_id=d["quiz_lesson_id"], learn_lesson_id=d["quiz_lesson_id"], quiz_id=quiz["id"], quiz_session_id=None, question_token=None, question_id=None)
    if not passed and quiz["retry_mode"]=="retry":
        await bot.send_message(chat_id,f"❌ قبول نشدی. نمره: {score}/{total}\nمی‌توانی دوباره تلاش کنی.",reply_markup=markup([[kb(BTN["retry_quiz"],"success")],[kb(BUTTON_BACK,"danger")]]))
    else:
        await bot.send_message(chat_id,f"{'🏆 قبول شدی!' if passed else '❌ قبول نشدی.'}\nنمره: {score}/{total}",reply_markup=markup([[kb(BUTTON_BACK,"danger")]]))


@dp.message(F.text == BTN["retry_quiz"])
async def retry_quiz(m,state):
    d = await state.get_data()
    lid = d.get("quiz_lesson_id") or d.get("learn_lesson_id")
    if not lid:
        return await m.answer("آزمون قبلی مشخص نیست. لطفاً از همان درس دوباره وارد آزمون شوید.")
    x = await db(); c = await x.execute("SELECT id FROM quizzes WHERE lesson_id=?", (lid,)); q = await c.fetchone(); await x.close()
    if not q:
        return await m.answer("آزمون این درس وجود ندارد.")
    await cancel_quiz_timer(state)
    await state.update_data(learn_lesson_id=lid, quiz_lesson_id=lid, quiz_id=q["id"], q_index=0, score=0, started=now_iso(), quiz_session_id=uuid.uuid4().hex, question_token=None, question_id=None)
    return await send_question(m.bot, m.chat.id, m.from_user.id, state)


# ---------------- Chapters admin ----------------

async def chapter_rows():
    x=await db(); c=await x.execute("SELECT * FROM chapters ORDER BY position,id"); r=await c.fetchall(); await x.close(); return r


async def chapter_menu_page(m,state,push=True):
    if push: await nav_push(state,"chapter_menu")
    await state.set_state(None); await m.answer("📚 مدیریت فصل‌ها",reply_markup=chapter_menu())


@dp.message(F.text == BTN["chapters"])
async def chapter_menu_handler(m,state):
    if await is_admin(m.from_user.id): await state.clear(); await chapter_menu_page(m,state)


# Use unique section-specific add texts to avoid the generic "➕ افزودن" collision.
CH_ADD=BTN["ch_add"]; CH_LIST=BTN["ch_list"]; CH_EDIT=BTN["ch_edit"]; CH_DELETE=BTN["ch_delete"]; CH_REORDER=BTN["ch_reorder"]
LESS_ADD=BTN["less_add"]; LESS_LIST=BTN["less_list"]; LESS_EDIT=BTN["less_edit"]; LESS_DELETE=BTN["less_delete"]


def chapter_menu():
    return markup([[kb(CH_ADD,"success"),kb(CH_LIST,"primary")],[kb(CH_EDIT,"primary"),kb(CH_DELETE,"danger")],[kb(CH_REORDER,"primary")],[kb(BUTTON_BACK,"danger")]])


@dp.message(F.text == CH_ADD)
async def add_chapter(m,state):
    if not await is_admin(m.from_user.id):return
    await state.clear(); await nav_push(state,"chapter_menu"); await nav_push(state,"chapter_add"); await state.set_state(S.ch_title); await m.answer("عنوان فصل را ارسال کنید:",reply_markup=back_kb())


@dp.message(S.ch_title)
async def chapter_title(m,state):
    title=(m.text or "").strip()
    if not title:return await m.answer("عنوان معتبر نیست.")
    x=await db(); c=await x.execute("SELECT id FROM chapters WHERE title=? LIMIT 1",(title,)); dup=await c.fetchone(); await x.close(); await state.update_data(ch_title=title)
    if dup: await state.set_state(S.ch_dup); return await m.answer("⚠️ فصلی با این عنوان وجود دارد. با همین عنوان ادامه می‌دهید؟",reply_markup=markup([[kb(BTN["continue"],"success"),kb(BTN["new"],"danger")],[kb(BUTTON_BACK,"danger")]]))
    await state.set_state(S.ch_desc); await m.answer("توضیحات فصل را ارسال کنید یا «رد کردن».",reply_markup=markup([[kb(BUTTON_SKIP,"primary")],[kb(BUTTON_BACK,"danger")]]))


@dp.message(S.ch_dup)
async def chapter_dup(m,state):
    if m.text==BTN["new"]: await state.set_state(S.ch_title); return await m.answer("عنوان جدید را ارسال کنید:")
    if m.text!=BTN["continue"]: return
    await state.set_state(S.ch_desc); await m.answer("توضیحات فصل را ارسال کنید یا «رد کردن».",reply_markup=markup([[kb(BUTTON_SKIP)],[kb(BUTTON_BACK,"danger")]]))


@dp.message(S.ch_desc)
async def chapter_desc(m,state):
    d=await state.get_data(); desc="" if m.text==BUTTON_SKIP else (m.text or ""); x=await db(); c=await x.execute("SELECT COALESCE(MAX(position),0)+1 p FROM chapters"); pos=(await c.fetchone())["p"]; await x.execute("INSERT INTO chapters(title,description,position) VALUES(?,?,?)",(d["ch_title"],desc,pos)); await x.commit(); await x.close(); await state.clear(); await m.answer("✅ فصل اضافه شد.",reply_markup=chapter_menu())


@dp.message(F.text == CH_LIST)
async def chapter_list(m,state):
    if not await is_admin(m.from_user.id):return
    rows=await chapter_rows(); buttons=[[kb(f"📚 #{r['id']} | {r['title']}","primary")] for r in rows]; await state.clear(); await nav_push(state,"chapter_menu"); await state.set_state(S.ch_select); await m.answer("فصل را انتخاب کنید:",reply_markup=markup(buttons+[[kb(BUTTON_BACK,"danger")]]))


@dp.message(S.ch_select)
async def chapter_select(m,state):
    cid=parse_id(m.text)
    if cid is None:return await m.answer("فصل را از کیبورد انتخاب کنید.")
    await show_chapter(m,state,cid,push=True)


async def show_chapter(m,state,cid,push=True):
    x=await db(); c=await x.execute("SELECT * FROM chapters WHERE id=?",(cid,)); r=await c.fetchone(); c=await x.execute("SELECT COUNT(*) n FROM lessons WHERE chapter_id=?",(cid,)); n=(await c.fetchone())["n"]; await x.close()
    if not r:return await m.answer("فصل پیدا نشد.")
    if push: await nav_push(state,f"chapter_info:{cid}")
    await state.update_data(selected_chapter=cid); await state.set_state(S.ch_info)
    await m.answer(f"📚 <b>{html.escape(r['title'])}</b>\n\n{html.escape(r['description'] or 'بدون توضیحات')}\n\n🎬 تعداد درس: {n}\n📌 ترتیب: {r['position']}",parse_mode="HTML",reply_markup=markup([[kb(BTN["detail_ch_edit"],"primary"),kb(BTN["detail_ch_delete"],"danger")],[kb(BTN["detail_ch_lessons"],"success")],[kb(BUTTON_BACK,"danger")]]))


@dp.message(F.text.in_({CH_EDIT, BTN["detail_ch_edit"]}))
async def chapter_edit_start(m,state):
    if not await is_admin(m.from_user.id):return
    rows=await chapter_rows(); await state.update_data(nav=["admin","chapter_menu"]); await nav_push(state,"chapter_edit_select"); await state.set_state(S.ch_edit_select); await m.answer("فصل را انتخاب کنید:",reply_markup=markup([[kb(f"📚 #{r['id']} | {r['title']}")] for r in rows]+[[kb(BUTTON_BACK,"danger")]]))


@dp.message(S.ch_edit_select)
async def chapter_edit_select(m,state):
    cid=parse_id(m.text)
    if cid is None:return
    await state.update_data(selected_chapter=cid); await nav_push(state,"chapter_edit_title"); await state.set_state(S.ch_edit_title); await m.answer("عنوان جدید را ارسال کنید:",reply_markup=back_kb())


@dp.message(S.ch_edit_title)
async def chapter_edit_title(m,state):
    title=(m.text or "").strip(); d=await state.get_data(); x=await db(); c=await x.execute("SELECT id FROM chapters WHERE title=? AND id<>?",(title,d["selected_chapter"])); dup=await c.fetchone()
    if dup: await x.close(); return await m.answer("⚠️ این عنوان تکراری است. عنوان دیگری انتخاب کنید.")
    await x.execute("UPDATE chapters SET title=? WHERE id=?",(title,d["selected_chapter"])); await x.commit(); await x.close(); await nav_push(state,"chapter_edit_desc"); await state.set_state(S.ch_edit_desc); await m.answer("توضیحات جدید یا «رد کردن»:",reply_markup=markup([[kb(BUTTON_SKIP)],[kb(BUTTON_BACK,"danger")]]))


@dp.message(S.ch_edit_desc)
async def chapter_edit_desc(m,state):
    d=await state.get_data(); x=await db(); await x.execute("UPDATE chapters SET description=? WHERE id=?",("" if m.text==BUTTON_SKIP else (m.text or ""),d["selected_chapter"])); await x.commit(); await x.close(); await show_chapter(m,state,d["selected_chapter"],push=False)


@dp.message(F.text.in_({CH_DELETE, BTN["detail_ch_delete"]}))
async def chapter_delete_start(m,state):
    if not await is_admin(m.from_user.id):return
    rows=await chapter_rows(); await state.update_data(nav=["admin","chapter_menu"]); await nav_push(state,"chapter_delete_select"); await state.set_state(S.ch_delete_select); await m.answer("فصل را انتخاب کنید:",reply_markup=markup([[kb(f"🗑 #{r['id']} | {r['title']}","danger")] for r in rows]+[[kb(BUTTON_BACK,"danger")]]))


@dp.message(S.ch_delete_select)
async def chapter_delete_select(m,state):
    cid=parse_id(m.text)
    if cid is None:return
    await state.update_data(selected_chapter=cid); await state.set_state(S.ch_delete_confirm); await m.answer("آیا از حذف این فصل مطمئن هستید؟ درس‌ها به «بدون فصل» منتقل می‌شوند.",reply_markup=markup([[kb(BUTTON_YES,"danger"),kb(BUTTON_NO,"primary")],[kb(BUTTON_BACK,"danger")]]))


@dp.message(S.ch_delete_confirm)
async def chapter_delete_confirm(m,state):
    if m.text==BUTTON_NO:return await chapter_menu_page(m,state,push=False)
    if m.text!=BUTTON_YES:return
    cid=(await state.get_data()).get("selected_chapter"); x=await db(); await x.execute("DELETE FROM chapters WHERE id=?",(cid,)); await x.commit(); await x.close(); await state.clear(); await m.answer("✅ فصل حذف شد.",reply_markup=chapter_menu())


@dp.message(F.text == CH_REORDER)
async def chapter_reorder_start(m,state):
    rows=await chapter_rows(); await state.update_data(nav=["admin","chapter_menu"]); await nav_push(state,"chapter_reorder_select"); await state.set_state(S.ch_reorder_select); await m.answer("فصل را انتخاب کنید:",reply_markup=markup([[kb(f"↕️ #{r['id']} | {r['title']}")] for r in rows]+[[kb(BUTTON_BACK,"danger")]]))


@dp.message(S.ch_reorder_select)
async def chapter_reorder_select(m,state):
    cid=parse_id(m.text)
    if cid is None:return
    await state.update_data(reorder_id=cid); await state.set_state(S.ch_reorder_target); await m.answer("جایگاه جدید را به عدد وارد کنید:",reply_markup=back_kb())


@dp.message(S.ch_reorder_target)
async def chapter_reorder_target(m,state):
    try:new=max(1,int(m.text))
    except:return await m.answer("عدد معتبر وارد کنید.")
    d=await state.get_data(); rows=await chapter_rows(); ids=[r["id"] for r in rows if r["id"]!=d["reorder_id"]]; ids.insert(min(new-1,len(ids)),d["reorder_id"]); x=await db();
    for i,cid in enumerate(ids,1):await x.execute("UPDATE chapters SET position=? WHERE id=?",(i,cid))
    await x.commit(); await x.close(); await state.clear(); await m.answer("✅ ترتیب فصل‌ها تغییر کرد.",reply_markup=chapter_menu())


@dp.message(F.text == BTN["detail_ch_lessons"])
async def chapter_lessons(m,state):
    cid=(await state.get_data()).get("selected_chapter")
    if not cid:return
    x=await db(); c=await x.execute("SELECT * FROM lessons WHERE chapter_id=? ORDER BY position,id",(cid,)); rows=await c.fetchall(); await x.close()
    await state.set_state(S.l_select); await nav_push(state,f"chapter_info:{cid}")
    await m.answer("🎬 درس‌های این فصل:",reply_markup=lesson_picker(rows))


# ---------------- Lesson admin ----------------

@dp.message(F.text == BTN["lessons"])
async def lesson_menu_handler(m,state):
    if await is_admin(m.from_user.id): await state.clear(); await lesson_menu_page(m,state)


async def lesson_menu_page(m,state,push=True):
    if push: await nav_push(state,"lesson_menu")
    await state.set_state(None); await m.answer("🎬 مدیریت درس‌ها",reply_markup=lesson_menu())


async def lesson_rows():
    x=await db(); c=await x.execute("SELECT l.*,c.title ct FROM lessons l LEFT JOIN chapters c ON c.id=l.chapter_id ORDER BY COALESCE(c.position,999999),l.position,l.id"); r=await c.fetchall(); await x.close(); return r


def lesson_picker(rows,prefix="🎬"):
    return markup([[kb(f"{prefix} #{r['id']} | {r['title']}","primary")] for r in rows]+[[kb(BUTTON_BACK,"danger")]])


async def chapter_picker(include_none=True):
    rows=await chapter_rows(); buttons=[[kb(f"📚 #{r['id']} | {r['title']}","primary")] for r in rows]
    if include_none:buttons.append([kb("📚 بدون فصل","primary")])
    buttons.append([kb(BUTTON_BACK,"danger")]); return markup(buttons)


@dp.message(F.text == LESS_ADD)
async def lesson_add_start(m,state):
    if not await is_admin(m.from_user.id):return
    await state.clear(); await nav_push(state,"lesson_menu"); await nav_push(state,"lesson_add"); await state.set_state(S.l_title); await m.answer("عنوان درس را ارسال کنید:",reply_markup=back_kb())


@dp.message(S.l_title)
async def lesson_title(m,state):
    title=(m.text or "").strip()
    if not title:return await m.answer("عنوان معتبر نیست.")
    x=await db(); c=await x.execute("SELECT id FROM lessons WHERE title=? LIMIT 1",(title,)); dup=await c.fetchone(); await x.close(); await state.update_data(l_title=title)
    if dup: await state.set_state(S.l_dup); return await m.answer("⚠️ درسی با این عنوان وجود دارد. آیا می‌خواهید با همین عنوان ادامه دهید؟",reply_markup=markup([[kb(BTN["continue"],"success"),kb(BTN["new"],"danger")],[kb(BUTTON_BACK,"danger")]]))
    await state.set_state(S.l_chapter); await m.answer("فصل را انتخاب کنید:",reply_markup=await chapter_picker())


@dp.message(S.l_dup)
async def lesson_dup(m,state):
    if m.text==BTN["new"]: await state.set_state(S.l_title); return await m.answer("عنوان جدید را ارسال کنید:")
    if m.text==BTN["continue"]: await state.set_state(S.l_chapter); return await m.answer("فصل را انتخاب کنید:",reply_markup=await chapter_picker())


@dp.message(S.l_chapter)
async def lesson_chapter(m,state):
    cid=None if m.text=="📚 بدون فصل" else parse_id(m.text)
    if m.text!="📚 بدون فصل" and cid is None:return await m.answer("فصل را از کیبورد انتخاب کنید.")
    await state.update_data(l_chapter=cid); await state.set_state(S.l_desc); await m.answer("توضیحات درس را ارسال کنید یا «رد کردن».",reply_markup=markup([[kb(BUTTON_SKIP)],[kb(BUTTON_BACK,"danger")]]))


@dp.message(S.l_desc)
async def lesson_desc(m,state):
    await state.update_data(l_desc="" if m.text==BUTTON_SKIP else (m.text or "")); await state.set_state(S.l_content); await m.answer("📎 محتوای درس را ارسال کنید: Video / Document / Photo / Audio / Voice / Animation / Video Note / Sticker / Text",reply_markup=back_kb())


@dp.message(S.l_content)
async def lesson_content(m,state):
    kind,fid,text,dur=extract_content(m)
    if not kind:return await m.answer("این نوع محتوا قابل ذخیره نیست.")
    await state.update_data(l_type=kind,l_file=fid,l_text=text,l_msg=m.message_id,l_auto_duration=dur)
    if kind=="video":
        await state.set_state(S.l_duration); return await m.answer(f"⏱ مدت ویدیو: {dur} ثانیه. تأیید می‌کنید یا عدد جدید بدهید؟",reply_markup=markup([[kb(BTN["confirm_duration"],"success")],[kb(BUTTON_BACK,"danger")]]))
    await save_new_lesson(m,state,0)


async def save_new_lesson(m,state,duration):
    d=await state.get_data(); x=await db(); c=await x.execute("SELECT COALESCE(MAX(position),0)+1 p FROM lessons WHERE chapter_id IS ?",(d.get("l_chapter"),)); pos=(await c.fetchone())["p"]; await x.execute("INSERT INTO lessons(chapter_id,title,description,position,content_type,content_file_id,content_text,telegram_message_id,duration,video_file_id) VALUES(?,?,?,?,?,?,?,?,?,?)",(d.get("l_chapter"),d["l_title"],d.get("l_desc",""),pos,d["l_type"],d.get("l_file",""),d.get("l_text",""),d["l_msg"],duration,d.get("l_file","") if d["l_type"]=="video" else "")); await x.commit(); await x.close(); await state.clear(); await m.answer("✅ درس ایجاد شد. اکنون می‌توانید آزمون بسازید یا آن را منتشر کنید.",reply_markup=lesson_menu())


@dp.message(S.l_duration)
async def lesson_duration(m,state):
    d=await state.get_data()
    if m.text==BTN["confirm_duration"]:duration=d.get("l_auto_duration",0)
    else:
        try:duration=max(0,int(m.text))
        except:return await m.answer("مدت را به ثانیه وارد کنید.")
    await save_new_lesson(m,state,duration)


@dp.message(F.text == LESS_LIST)
async def lesson_list(m,state):
    if not await is_admin(m.from_user.id):return
    rows=await lesson_rows(); await state.clear(); await nav_push(state,"lesson_menu")
    if not rows:return await m.answer("درسی وجود ندارد.",reply_markup=lesson_menu())
    await state.set_state(S.l_select); await m.answer("درس را انتخاب کنید:",reply_markup=lesson_picker(rows))


@dp.message(S.l_select)
async def lesson_select(m,state):
    lid=parse_id(m.text)
    if lid is None:return
    await show_lesson(m,state,lid,push=True)


async def show_lesson(m,state,lid,push=True):
    x=await db(); c=await x.execute("SELECT l.*,c.title ct FROM lessons l LEFT JOIN chapters c ON c.id=l.chapter_id WHERE l.id=?",(lid,)); l=await c.fetchone(); c=await x.execute("SELECT COUNT(*) n FROM questions q JOIN quizzes qz ON qz.id=q.quiz_id WHERE qz.lesson_id=?",(lid,)); qn=(await c.fetchone())["n"]; c=await x.execute("SELECT id FROM quizzes WHERE lesson_id=?",(lid,)); hasq=await c.fetchone(); await x.close()
    if not l:return await m.answer("درس پیدا نشد.")
    if push: await nav_push(state,f"lesson_info:{lid}")
    await state.update_data(selected_lesson=lid); await state.set_state(S.l_info)
    body=f"🎬 <b>{html.escape(l['title'])}</b>\nفصل: {html.escape(l['ct'] or 'بدون فصل')}\nتوضیحات: {html.escape(l['description'] or '—')}\nنوع محتوا: {l['content_type'] or '—'}\nTelegram Message ID: {l['telegram_message_id']}\n"
    if l["content_type"]=="video":body+=f"مدت Video: {l['duration']} ثانیه\n"
    body+=f"وضعیت انتشار: {'منتشر شده' if l['published'] else 'پیش‌نویس'}\nسؤال‌های آزمون: {qn}\nآزمون: {'دارد' if hasq else 'ندارد'}\nتاریخ ایجاد: {l['created_at']}"
    await m.answer(body,parse_mode="HTML",reply_markup=markup([[kb(BTN["detail_l_edit"],"primary"),kb(BTN["detail_l_delete"],"danger")],[kb(BTN["quiz_manage"],"success"),kb(BTN["publish"],"primary")],[kb(BUTTON_BACK,"danger")]]))


@dp.message(F.text == BTN["publish"])
async def publish_start(m,state):
    rows=await lesson_rows(); await state.set_state(S.l_publish_select); await state.update_data(nav=["admin","lesson_menu"]); await m.answer("درس را انتخاب کنید:",reply_markup=lesson_picker(rows,"📢"))


@dp.message(S.l_publish_select)
async def publish_select(m,state):
    lid=parse_id(m.text)
    if lid is None:return
    x=await db(); await x.execute("UPDATE lessons SET published=1-published WHERE id=?",(lid,)); await x.commit(); await x.close(); await state.clear(); await m.answer("✅ وضعیت انتشار تغییر کرد.",reply_markup=lesson_menu())


@dp.message(F.text.in_({LESS_EDIT, BTN["detail_l_edit"]}))
async def lesson_edit_start(m,state):
    rows=await lesson_rows(); await state.update_data(nav=["admin","lesson_menu"]); await nav_push(state,"lesson_edit_select"); await state.set_state(S.l_edit_select); await m.answer("درس را انتخاب کنید:",reply_markup=lesson_picker(rows,"✏️"))


@dp.message(S.l_edit_select)
async def lesson_edit_select(m,state):
    lid=parse_id(m.text)
    if lid is None:return
    await state.update_data(selected_lesson=lid); await nav_push(state,f"lesson_info:{lid}"); await state.set_state(S.l_edit_field)
    await m.answer("چه چیزی را ویرایش می‌کنید؟",reply_markup=markup([[kb("عنوان","primary"),kb("فصل","primary")],[kb("توضیحات","primary"),kb("محتوا","primary")],[kb("مدت Video","primary"),kb(BTN["quiz_manage"],"success")],[kb("وضعیت انتشار","primary")],[kb(BUTTON_BACK,"danger")]]))


@dp.message(S.l_edit_field)
async def lesson_edit_field(m,state):
    d=await state.get_data(); lid=d["selected_lesson"]
    if m.text=="عنوان": await state.update_data(edit_field="title"); await state.set_state(S.l_edit_value); return await m.answer("عنوان جدید:",reply_markup=back_kb())
    if m.text=="توضیحات": await state.update_data(edit_field="description"); await state.set_state(S.l_edit_value); return await m.answer("توضیحات جدید یا «رد کردن»:",reply_markup=markup([[kb(BUTTON_SKIP)],[kb(BUTTON_BACK,"danger")]]))
    if m.text=="فصل": await state.set_state(S.l_edit_chapter); return await m.answer("فصل را انتخاب کنید:",reply_markup=await chapter_picker())
    if m.text=="محتوا": await state.set_state(S.l_edit_content); return await m.answer("محتوای جدید را ارسال کنید:",reply_markup=back_kb())
    if m.text=="مدت Video":
        x=await db(); c=await x.execute("SELECT content_type FROM lessons WHERE id=?",(lid,)); r=await c.fetchone(); await x.close()
        if not r or r["content_type"]!="video":return await m.answer("این درس Video نیست.")
        await state.update_data(edit_field="duration"); await state.set_state(S.l_edit_value); return await m.answer("مدت جدید به ثانیه:",reply_markup=back_kb())
    if m.text=="وضعیت انتشار":
        x=await db(); await x.execute("UPDATE lessons SET published=1-published WHERE id=?",(lid,)); await x.commit(); await x.close(); return await show_lesson(m,state,lid,push=False)
    if m.text==BTN["quiz_manage"]: return await open_quiz_for_lesson(m,state,lid,push=True)


@dp.message(S.l_edit_value)
async def lesson_edit_value(m,state):
    d=await state.get_data(); field=d["edit_field"]; lid=d["selected_lesson"]
    value="" if field=="description" and m.text==BUTTON_SKIP else (m.text or "")
    if field=="duration":
        try:value=max(0,int(value))
        except:return await m.answer("عدد معتبر وارد کنید.")
    x=await db(); await x.execute(f"UPDATE lessons SET {field}=? WHERE id=?",(value,lid)); await x.commit(); await x.close(); await show_lesson(m,state,lid,push=False)


@dp.message(S.l_edit_chapter)
async def lesson_edit_chapter(m,state):
    cid=None if m.text=="📚 بدون فصل" else parse_id(m.text)
    if m.text!="📚 بدون فصل" and cid is None:return
    lid=(await state.get_data())["selected_lesson"]; x=await db(); await x.execute("UPDATE lessons SET chapter_id=? WHERE id=?",(cid,lid)); await x.commit(); await x.close(); await show_lesson(m,state,lid,push=False)


@dp.message(S.l_edit_content)
async def lesson_edit_content(m,state):
    lid=(await state.get_data())["selected_lesson"]; kind,fid,text,dur=extract_content(m)
    if not kind:return await m.answer("محتوا قابل ذخیره نیست.")
    if kind=="video":
        x=await db(); await x.execute("UPDATE lessons SET content_type=?,content_file_id=?,content_text=?,telegram_message_id=?,duration=?,video_file_id=? WHERE id=?",(kind,fid,text,m.message_id,dur,fid,lid)); await x.commit(); await x.close()
    else:
        x=await db(); await x.execute("UPDATE lessons SET content_type=?,content_file_id=?,content_text=?,telegram_message_id=?,duration=0,video_file_id='' WHERE id=?",(kind,fid,text,m.message_id,lid)); await x.commit(); await x.close()
    await show_lesson(m,state,lid,push=False)


@dp.message(F.text.in_({LESS_DELETE, BTN["detail_l_delete"]}))
async def lesson_delete_start(m,state):
    rows=await lesson_rows(); await state.set_state(S.l_delete_select); await state.update_data(nav=["admin","lesson_menu"]); await m.answer("درس را انتخاب کنید:",reply_markup=lesson_picker(rows,"🗑"))


@dp.message(S.l_delete_select)
async def lesson_delete_select(m,state):
    lid=parse_id(m.text)
    if lid is None:return
    await state.update_data(selected_lesson=lid); await state.set_state(S.l_delete_confirm); await m.answer("آیا از حذف این درس مطمئن هستید؟",reply_markup=markup([[kb(BUTTON_YES,"danger"),kb(BUTTON_NO,"primary")],[kb(BUTTON_BACK,"danger")]]))


@dp.message(S.l_delete_confirm)
async def lesson_delete_confirm(m,state):
    if m.text==BUTTON_NO:return await lesson_menu_page(m,state,push=False)
    if m.text!=BUTTON_YES:return
    lid=(await state.get_data())["selected_lesson"]; x=await db(); await x.execute("DELETE FROM lessons WHERE id=?",(lid,)); await x.commit(); await x.close(); await state.clear(); await m.answer("✅ درس حذف شد.",reply_markup=lesson_menu())


# ---------------- Quiz admin ----------------

@dp.message(F.text == BTN["quizzes"])
async def quiz_menu_handler(m,state):
    if await is_admin(m.from_user.id): await state.clear(); await quiz_menu_page(m,state)


async def quiz_menu_page(m,state,push=True):
    if push:await state.update_data(nav=["admin","quiz_menu"])
    await state.set_state(None); await m.answer("📝 مدیریت آزمون‌ها",reply_markup=quiz_menu())


async def quiz_rows():
    x=await db(); c=await x.execute("SELECT q.*,l.title lesson_title,(SELECT COUNT(*) FROM questions qq WHERE qq.quiz_id=q.id) qn FROM quizzes q JOIN lessons l ON l.id=q.lesson_id ORDER BY l.id"); r=await c.fetchall(); await x.close(); return r


async def quiz_lesson_picker():
    rows=await lesson_rows(); return lesson_picker(rows,"📝")


@dp.message(F.text == BTN["quiz_create"])
async def quiz_create_start(m,state):
    rows=await lesson_rows(); await state.set_state(S.qz_lesson); await state.update_data(nav=["admin","quiz_menu"]); await m.answer("درس را انتخاب کنید:",reply_markup=lesson_picker(rows,"📝"))


@dp.message(S.qz_lesson)
async def quiz_lesson(m,state):
    lid=parse_id(m.text)
    if lid is None:return
    x=await db(); c=await x.execute("SELECT id FROM quizzes WHERE lesson_id=?",(lid,)); exists=await c.fetchone(); await x.close()
    if exists:return await m.answer("این درس از قبل آزمون دارد. از مدیریت آزمون همان درس استفاده کنید.")
    await state.update_data(quiz_lesson=lid); await state.set_state(S.qz_pass); await m.answer("درصد قبولی را وارد کنید (مثلاً 70):",reply_markup=back_kb())


@dp.message(S.qz_retry)
async def quiz_retry(m,state):
    if m.text not in (BTN["quiz_retry_mode"],BTN["quiz_complete_mode"]):return
    d=await state.get_data(); mode="retry" if m.text==BTN["quiz_retry_mode"] else "complete"; x=await db(); await x.execute("INSERT INTO quizzes(lesson_id,pass_percent,retry_mode) VALUES(?,?,?)",(d["quiz_lesson"],d["qz_pass"],mode)); await x.commit(); await x.close(); await state.clear(); await open_quiz_for_lesson(m,state,d["quiz_lesson"],push=False)


@dp.message(F.text == BTN["quiz_list"])
async def quiz_list(m,state):
    rows=await quiz_rows();
    if not rows:return await m.answer("آزمونی وجود ندارد.",reply_markup=quiz_menu())
    await state.set_state(S.qz_select); await state.update_data(nav=["admin","quiz_menu"]); await m.answer("آزمون را انتخاب کنید:",reply_markup=markup([[kb(f"📝 #{r['id']} | {r['lesson_title']}")] for r in rows]+[[kb(BUTTON_BACK,"danger")]]))


@dp.message(S.qz_select)
async def quiz_select(m,state):
    qid=parse_id(m.text)
    if qid is None:return
    x=await db(); c=await x.execute("SELECT lesson_id FROM quizzes WHERE id=?",(qid,)); r=await c.fetchone(); await x.close()
    if r:await open_quiz_for_lesson(m,state,r["lesson_id"],push=True)


async def open_quiz_for_lesson(m,state,lid,push=True):
    x=await db(); c=await x.execute("SELECT q.*,l.title lesson_title FROM quizzes q JOIN lessons l ON l.id=q.lesson_id WHERE q.lesson_id=?",(lid,)); q=await c.fetchone(); c=await x.execute("SELECT * FROM questions WHERE quiz_id=? ORDER BY position,id",(q["id"],)) if q else None; qs=await c.fetchall() if c else []; await x.close()
    if not q:return await m.answer("برای این درس آزمون وجود ندارد.")
    if push:await nav_push(state,f"quiz_for_lesson:{lid}")
    await state.update_data(selected_quiz=q["id"],selected_lesson=lid); await state.set_state(S.qz_question_select)
    await m.answer(f"📝 آزمون درس «{html.escape(q['lesson_title'])}»\nقبولی: {q['pass_percent']}%\nمنطق شکست: {q['retry_mode']}\nسؤال‌ها: {len(qs)}",parse_mode="HTML",reply_markup=markup([[kb(BTN["question_add"],"success"),kb(BTN["question_list"],"primary")],[kb(BTN["question_edit"],"primary"),kb(BTN["question_delete"],"danger")],[kb(BTN["question_reorder"],"primary"),kb(BTN["quiz_settings"],"primary")],[kb(BTN["quiz_delete"],"danger")],[kb(BUTTON_BACK,"danger")]]))


@dp.message(F.text == BTN["quiz_manage"])
async def quiz_manage_from_lesson(m,state):
    lid=(await state.get_data()).get("selected_lesson")
    if lid:return await open_quiz_for_lesson(m,state,lid,push=True)


@dp.message(F.text == BTN["question_add"])
async def question_add_start(m,state):
    d=await state.get_data(); qid=d.get("selected_quiz")
    if not qid:
        rows=await quiz_rows()
        await nav_push(state,"quiz_question_add_select")
        await state.set_state(S.qz_select)
        return await m.answer("آزمون را انتخاب کنید:",reply_markup=markup([[kb(f"📝 #{r['id']} | {r['lesson_title']}")] for r in rows]+[[kb(BUTTON_BACK,"danger")]]))
    await nav_push(state,"quiz_question_add"); await state.set_state(S.q_text); await m.answer("متن سؤال را ارسال کنید:",reply_markup=back_kb())


@dp.message(S.q_text)
async def question_text(m,state):
    await state.update_data(q_text=m.text or ""); await state.set_state(S.q_options); await m.answer("گزینه‌ها را هر کدام در یک خط ارسال کنید:",reply_markup=back_kb())


@dp.message(S.q_options)
async def question_options(m,state):
    opts=[x.strip() for x in (m.text or "").splitlines() if x.strip()]
    ok, result = validate_option_texts(opts)
    if not ok: return await m.answer(result)
    opts=result
    await state.update_data(q_options=opts); await state.set_state(S.q_correct); await m.answer("شماره گزینه صحیح را وارد کنید:",reply_markup=markup([[kb(str(i+1))] for i in range(len(opts))]+[[kb(BUTTON_BACK,"danger")]]))


@dp.message(S.q_correct)
async def question_correct(m,state):
    try:i=int(m.text)-1; opts=(await state.get_data())["q_options"]; assert 0<=i<len(opts)
    except:return await m.answer("شماره گزینه صحیح معتبر نیست.")
    await state.update_data(q_correct=i); await state.set_state(S.q_timer); await m.answer("Timer سؤال را به ثانیه وارد کنید:",reply_markup=back_kb())


@dp.message(S.q_timer)
async def question_timer(m,state):
    try:t=max(1,int(m.text))
    except:return await m.answer("Timer معتبر نیست.")
    d=await state.get_data(); x=await db(); c=await x.execute("SELECT COALESCE(MAX(position),0)+1 p FROM questions WHERE quiz_id=?",(d["selected_quiz"],)); pos=(await c.fetchone())["p"]; c=await x.execute("INSERT INTO questions(quiz_id,text,position,timer) VALUES(?,?,?,?)",(d["selected_quiz"],d["q_text"],pos,t)); qid=c.lastrowid
    for i,text in enumerate(d["q_options"]): await x.execute("INSERT INTO options(question_id,text,is_correct) VALUES(?,?,?)",(qid,text,int(i==d["q_correct"])))
    await x.commit(); await x.close(); await state.clear(); await open_quiz_for_lesson(m,state,d["selected_lesson"],push=False)


@dp.message(F.text == BTN["question_list"])
async def question_list(m,state):
    qid=(await state.get_data()).get("selected_quiz")
    if not qid:return
    x=await db(); c=await x.execute("SELECT * FROM questions WHERE quiz_id=? ORDER BY position,id",(qid,)); rows=await c.fetchall(); await x.close(); await state.set_state(S.qz_question_select); await m.answer("\n".join(f"❓ #{r['id']} | {r['text']} | ⏱ {r['timer']}s" for r in rows) or "سؤالی وجود ندارد.",reply_markup=back_kb())


@dp.message(F.text == BTN["question_edit"])
async def question_edit_start(m,state):
    qid=(await state.get_data()).get("selected_quiz");
    if not qid:return
    x=await db(); c=await x.execute("SELECT * FROM questions WHERE quiz_id=? ORDER BY position,id",(qid,)); rows=await c.fetchall(); await x.close(); await nav_push(state,"quiz_question_edit"); await state.set_state(S.q_edit_select); await m.answer("سؤال را انتخاب کنید:",reply_markup=markup([[kb(f"✏️ #{r['id']} | {r['text']}")] for r in rows]+[[kb(BUTTON_BACK,"danger")]]))


@dp.message(S.q_edit_select)
async def question_edit_select(m,state):
    qid=parse_id(m.text)
    if qid is None:return
    await state.update_data(edit_question=qid); await nav_push(state,"quiz_question_edit_field"); await state.set_state(S.q_edit_field); await m.answer("چه چیزی را ویرایش می‌کنید؟",reply_markup=markup([[kb(BTN["q_edit_text"]) ,kb(BTN["q_edit_options"])],[kb(BTN["q_edit_correct"]),kb(BTN["q_edit_timer"])],[kb(BUTTON_BACK,"danger")]]))


@dp.message(S.q_edit_field)
async def question_edit_field(m,state):
    if m.text==BTN["q_edit_text"]: await state.set_state(S.q_edit_text); return await m.answer("متن جدید سؤال:",reply_markup=back_kb())
    if m.text==BTN["q_edit_options"]: await state.set_state(S.q_edit_options); return await m.answer("گزینه‌های جدید را هر کدام در یک خط ارسال کنید:",reply_markup=back_kb())
    if m.text==BTN["q_edit_correct"]:
        d=await state.get_data(); x=await db(); c=await x.execute("SELECT * FROM options WHERE question_id=? ORDER BY id",(d["edit_question"],)); opts=await c.fetchall(); await x.close(); await state.set_state(S.q_edit_correct); return await m.answer("شماره گزینه صحیح را انتخاب کنید:",reply_markup=markup([[kb(str(i+1))] for i in range(len(opts))]+[[kb(BUTTON_BACK,"danger")]]))
    if m.text==BTN["q_edit_timer"]: await state.set_state(S.q_edit_timer); return await m.answer("Timer جدید به ثانیه:",reply_markup=back_kb())


@dp.message(S.q_edit_text)
async def question_edit_text(m,state):
    d=await state.get_data(); x=await db(); await x.execute("UPDATE questions SET text=? WHERE id=?",(m.text or "",d["edit_question"])); await x.commit(); await x.close(); await open_quiz_for_lesson(m,state,d["selected_lesson"],push=False)


@dp.message(S.q_edit_options)
async def question_edit_options(m,state):
    opts=[x.strip() for x in (m.text or "").splitlines() if x.strip()]
    ok, result = validate_option_texts(opts)
    if not ok: return await m.answer(result)
    opts=result
    d=await state.get_data(); x=await db(); c=await x.execute("SELECT * FROM options WHERE question_id=? ORDER BY id",(d["edit_question"],)); old=await c.fetchall(); correct=next((i for i,o in enumerate(old) if o["is_correct"]),0); await x.execute("DELETE FROM options WHERE question_id=?",(d["edit_question"],))
    for i,text in enumerate(opts): await x.execute("INSERT INTO options(question_id,text,is_correct) VALUES(?,?,?)",(d["edit_question"],text,int(i==min(correct,len(opts)-1))))
    await x.commit(); await x.close(); await open_quiz_for_lesson(m,state,d["selected_lesson"],push=False)


@dp.message(S.q_edit_correct)
async def question_edit_correct(m,state):
    try:i=int(m.text)-1
    except:return await m.answer("شماره معتبر نیست.")
    d=await state.get_data(); x=await db(); c=await x.execute("SELECT id FROM options WHERE question_id=? ORDER BY id",(d["edit_question"],)); opts=await c.fetchall()
    if not 0<=i<len(opts): await x.close(); return await m.answer("شماره معتبر نیست.")
    await x.execute("UPDATE options SET is_correct=0 WHERE question_id=?",(d["edit_question"],)); await x.execute("UPDATE options SET is_correct=1 WHERE id=?",(opts[i]["id"],)); await x.commit(); await x.close(); await open_quiz_for_lesson(m,state,d["selected_lesson"],push=False)


@dp.message(S.q_edit_timer)
async def question_edit_timer(m,state):
    try:t=max(1,int(m.text))
    except:return await m.answer("Timer معتبر نیست.")
    d=await state.get_data(); x=await db(); await x.execute("UPDATE questions SET timer=? WHERE id=?",(t,d["edit_question"])); await x.commit(); await x.close(); await open_quiz_for_lesson(m,state,d["selected_lesson"],push=False)


@dp.message(F.text == BTN["question_delete"])
async def question_delete_start(m,state):
    qid=(await state.get_data()).get("selected_quiz");
    if not qid:return
    x=await db(); c=await x.execute("SELECT * FROM questions WHERE quiz_id=? ORDER BY position,id",(qid,)); rows=await c.fetchall(); await x.close(); await state.set_state(S.q_delete_select); await m.answer("سؤال را انتخاب کنید:",reply_markup=markup([[kb(f"🗑 #{r['id']} | {r['text']}","danger")] for r in rows]+[[kb(BUTTON_BACK,"danger")]]))


@dp.message(S.q_delete_select)
async def question_delete_select(m,state):
    qid=parse_id(m.text)
    if qid is None:return
    await state.update_data(delete_question=qid); await state.set_state(S.q_delete_confirm); await m.answer("آیا سؤال حذف شود؟",reply_markup=markup([[kb(BUTTON_YES,"danger"),kb(BUTTON_NO,"primary")],[kb(BUTTON_BACK,"danger")]]))


@dp.message(S.q_delete_confirm)
async def question_delete_confirm(m,state):
    if m.text==BUTTON_NO:return await open_quiz_for_lesson(m,state,(await state.get_data())["selected_lesson"],push=False)
    if m.text!=BUTTON_YES:return
    d=await state.get_data(); x=await db(); await x.execute("DELETE FROM questions WHERE id=?",(d["delete_question"],)); await x.commit(); await x.close(); await open_quiz_for_lesson(m,state,d["selected_lesson"],push=False)


@dp.message(F.text == BTN["question_reorder"])
async def question_reorder_start(m,state):
    qid=(await state.get_data()).get("selected_quiz");
    if not qid:return
    x=await db(); c=await x.execute("SELECT * FROM questions WHERE quiz_id=? ORDER BY position,id",(qid,)); rows=await c.fetchall(); await x.close(); await state.set_state(S.q_reorder_select); await m.answer("سؤال را انتخاب کنید:",reply_markup=markup([[kb(f"↕️ #{r['id']} | {r['text']}")] for r in rows]+[[kb(BUTTON_BACK,"danger")]]))


@dp.message(S.q_reorder_select)
async def question_reorder_select(m,state):
    qid=parse_id(m.text)
    if qid is None:return
    await state.update_data(reorder_question=qid); await state.set_state(S.q_reorder_target); await m.answer("جایگاه جدید را وارد کنید:",reply_markup=back_kb())


@dp.message(S.q_reorder_target)
async def question_reorder_target(m,state):
    try:new=max(1,int(m.text))
    except:return await m.answer("عدد معتبر وارد کنید.")
    d=await state.get_data(); x=await db(); c=await x.execute("SELECT id FROM questions WHERE quiz_id=? ORDER BY position,id",(d["selected_quiz"],)); ids=[r["id"] for r in await c.fetchall() if r["id"]!=d["reorder_question"]]; ids.insert(min(new-1,len(ids)),d["reorder_question"])
    for i,qid in enumerate(ids,1):await x.execute("UPDATE questions SET position=? WHERE id=?",(i,qid))
    await x.commit(); await x.close(); await open_quiz_for_lesson(m,state,d["selected_lesson"],push=False)


@dp.message(F.text == BTN["quiz_settings"])
async def quiz_settings(m,state):
    d=await state.get_data(); x=await db(); c=await x.execute("SELECT * FROM quizzes WHERE id=?",(d.get("selected_quiz"),)); q=await c.fetchone(); await x.close()
    if not q:return
    await state.update_data(edit_quiz=True); await state.set_state(S.qz_pass); await m.answer(f"درصد قبولی فعلی {q['pass_percent']} است. مقدار جدید:",reply_markup=back_kb())


@dp.message(S.qz_pass)
async def quiz_pass_or_settings(m,state):
    d=await state.get_data()
    if d.get("edit_quiz"):
        try:p=max(1,min(100,int(m.text)))
        except:return await m.answer("درصد معتبر وارد کنید.")
        x=await db(); await x.execute("UPDATE quizzes SET pass_percent=? WHERE id=?",(p,d["selected_quiz"])); await x.commit(); await x.close(); return await open_quiz_for_lesson(m,state,d["selected_lesson"],push=False)
    # This branch is shadowed by the create-flow handler in a real aiogram dispatcher;
    # keep the state-specific logic centralized through the same state.
    try:p=max(1,min(100,int(m.text)))
    except:return await m.answer("درصد معتبر وارد کنید.")
    await state.update_data(qz_pass=p); await state.set_state(S.qz_retry); await m.answer("منطق شکست را انتخاب کنید:",reply_markup=markup([[kb(BTN["quiz_retry_mode"],"success"),kb(BTN["quiz_complete_mode"],"primary")],[kb(BUTTON_BACK,"danger")]]))


@dp.message(F.text == BTN["quiz_delete"])
async def quiz_delete_start(m,state):
    if not (await state.get_data()).get("selected_quiz"):return
    await state.set_state(S.qz_delete_confirm); await m.answer("آیا آزمون این درس حذف شود؟",reply_markup=markup([[kb(BUTTON_YES,"danger"),kb(BUTTON_NO,"primary")],[kb(BUTTON_BACK,"danger")]]))


@dp.message(S.qz_delete_confirm)
async def quiz_delete_confirm(m,state):
    d=await state.get_data()
    if m.text==BUTTON_NO:return await open_quiz_for_lesson(m,state,d["selected_lesson"],push=False)
    if m.text!=BUTTON_YES:return
    x=await db(); await x.execute("DELETE FROM quizzes WHERE id=?",(d["selected_quiz"],)); await x.commit(); await x.close(); await state.clear(); await m.answer("✅ آزمون حذف شد.",reply_markup=quiz_menu())


# ---------------- Users ----------------

@dp.message(F.text == BTN["users"])
async def users_menu(m,state,push=True):
    if not await is_admin(m.from_user.id):return
    await state.clear()
    if push: await state.update_data(nav=["admin", "users"])
    await m.answer("👥 کاربران",reply_markup=markup([[kb(BTN["user_search"],"success"),kb(BTN["user_list"],"primary")],[kb(BUTTON_BACK,"danger")]]))


@dp.message(F.text == BTN["user_list"])
async def user_list(m,state):
    x=await db(); c=await x.execute("SELECT * FROM users ORDER BY last_activity DESC LIMIT 50"); rows=await c.fetchall(); await x.close(); await state.update_data(nav=["admin","users"]); await nav_push(state,"user_select"); await state.set_state(S.user_select); await m.answer("کاربر را انتخاب کنید:",reply_markup=markup([[kb(f"👤 #{r['id']} | {r['first_name'] or '-'} | @{r['username'] or '-'}")] for r in rows]+[[kb(BUTTON_BACK,"danger")]]))


@dp.message(F.text == BTN["user_search"])
async def user_search_start(m,state):
    await state.set_state(S.user_search); await m.answer("Username، نام یا Telegram ID را جستجو کنید:",reply_markup=back_kb())


@dp.message(S.user_search)
async def user_search(m,state):
    q=(m.text or "").strip(); x=await db(); c=await x.execute("SELECT * FROM users WHERE username LIKE ? OR first_name LIKE ? OR CAST(telegram_id AS TEXT)=? LIMIT 30",(q.lstrip('@')+'%',q+'%',q)); rows=await c.fetchall(); await x.close(); await state.set_state(S.user_select); await m.answer("نتیجه جستجو:",reply_markup=markup([[kb(f"👤 #{r['id']} | {r['first_name'] or '-'} | @{r['username'] or '-'}")] for r in rows]+[[kb(BUTTON_BACK,"danger")]]))


@dp.message(S.user_select)
async def user_select(m,state):
    uid=parse_id(m.text)
    if uid is None:return
    await show_user(m,state,uid,push=True)


async def show_user(m,state,uid,push=True):
    x=await db(); c=await x.execute("SELECT * FROM users WHERE id=?",(uid,)); u=await c.fetchone(); c=await x.execute("SELECT COUNT(*) n FROM progress WHERE user_id=? AND completed_at IS NOT NULL",(uid,)); done=(await c.fetchone())["n"]; c=await x.execute("SELECT AVG(score*100.0/(SELECT COUNT(*) FROM questions WHERE quiz_id=a.quiz_id)) a FROM attempts a WHERE user_id=?",(uid,)); avg=(await c.fetchone())["a"]; await x.close()
    if not u:return await m.answer("کاربر پیدا نشد.")
    if push:await nav_push(state,f"user_profile:{uid}")
    await state.update_data(selected_user=uid); await state.set_state(S.user_profile)
    await m.answer(f"👤 <b>{html.escape(u['first_name'] or '-')}</b>\nآخرین درس فعال: #{u['last_lesson_id'] or '-'}\nUsername: @{html.escape(u['username'] or '-')}\nTelegram ID: <code>{u['telegram_id']}</code>\n📈 درس تکمیل‌شده: {done}\n🏆 میانگین نمره: {round(avg or 0,1)}%\n🚫 Block: {'بله' if u['blocked'] else 'خیر'}\n🔐 دسترسی: {'دارد' if u['course_access'] else 'ندارد'}\n🕐 آخرین فعالیت: {u['last_activity']}",parse_mode="HTML",reply_markup=markup([[kb(BTN["user_progress"]),kb(BTN["user_completed"])],[kb(BTN["user_scores"]),kb(BTN["user_reset"],"danger")],[kb(BTN["user_block"],"danger"),kb(BTN["user_access"])],[kb(BTN["user_message"],"success")],[kb(BUTTON_BACK,"danger")]]))


@dp.message(F.text == BTN["user_progress"])
async def user_progress(m,state):
    uid=(await state.get_data()).get("selected_user");
    if not uid:return
    x=await db(); c=await x.execute("SELECT l.title,COALESCE(p.video_done,0) done,COALESCE(p.quiz_passed,0) passed,p.completed_at FROM lessons l LEFT JOIN progress p ON p.lesson_id=l.id AND p.user_id=? WHERE l.published=1 ORDER BY l.id",(uid,)); rows=await c.fetchall(); await x.close(); await m.answer("\n".join(f"{'✅' if r['done'] else '🔒'} {r['title']} | آزمون: {'قبول' if r['passed'] else '—'}" for r in rows) or "Progress خالی است.",reply_markup=back_kb())


@dp.message(F.text == BTN["user_completed"])
async def user_completed(m,state):
    uid=(await state.get_data()).get("selected_user"); x=await db(); c=await x.execute("SELECT l.title,p.completed_at FROM progress p JOIN lessons l ON l.id=p.lesson_id WHERE p.user_id=? AND p.completed_at IS NOT NULL ORDER BY p.completed_at DESC",(uid,)); rows=await c.fetchall(); await x.close(); await m.answer("\n".join(f"✅ {r['title']} — {r['completed_at']}" for r in rows) or "هنوز تکمیل نشده.",reply_markup=back_kb())


@dp.message(F.text == BTN["user_scores"])
async def user_scores(m,state):
    uid=(await state.get_data()).get("selected_user"); x=await db(); c=await x.execute("SELECT l.title,a.score,a.passed,a.finished_at FROM attempts a JOIN quizzes q ON q.id=a.quiz_id JOIN lessons l ON l.id=q.lesson_id WHERE a.user_id=? ORDER BY a.finished_at DESC",(uid,)); rows=await c.fetchall(); await x.close(); await m.answer("\n".join(f"📝 {r['title']} — {r['score']} | {'قبول' if r['passed'] else 'رد'} | {r['finished_at']}" for r in rows) or "نمره‌ای وجود ندارد.",reply_markup=back_kb())


@dp.message(F.text == BTN["user_reset"])
async def user_reset(m,state):
    uid=(await state.get_data()).get("selected_user"); x=await db(); await x.execute("DELETE FROM progress WHERE user_id=?",(uid,)); await x.execute("DELETE FROM attempts WHERE user_id=?",(uid,)); await x.commit(); await x.close(); await m.answer("✅ Progress و نمرات Reset شد.",reply_markup=back_kb())


@dp.message(F.text == BTN["user_block"])
async def user_block(m,state):
    uid=(await state.get_data()).get("selected_user"); x=await db(); await x.execute("UPDATE users SET blocked=1-blocked WHERE id=?",(uid,)); await x.commit(); await x.close(); await show_user(m,state,uid,push=False)


@dp.message(F.text == BTN["user_access"])
async def user_access(m,state):
    uid=(await state.get_data()).get("selected_user"); x=await db(); await x.execute("UPDATE users SET course_access=1-course_access WHERE id=?",(uid,)); await x.commit(); await x.close(); await show_user(m,state,uid,push=False)


@dp.message(F.text == BTN["user_message"])
async def user_message_start(m,state):
    uid=(await state.get_data()).get("selected_user"); x=await db(); c=await x.execute("SELECT telegram_id FROM users WHERE id=?",(uid,)); u=await c.fetchone(); await x.close(); await nav_push(state,"user_message"); await state.set_state(S.user_message); await state.update_data(user_tid=u["telegram_id"]); await m.answer("پیام را ارسال کنید:",reply_markup=back_kb())


@dp.message(S.user_message)
async def user_message_send(m,state):
    tid=(await state.get_data()).get("user_tid")
    try:await m.bot.copy_message(tid,m.chat.id,m.message_id)
    except Exception as e:return await m.answer(f"❌ ارسال نشد: {html.escape(str(e))}",parse_mode="HTML")
    await state.clear(); await m.answer("✅ پیام ارسال شد.",reply_markup=admin_kb())


# ---------------- Support ----------------

@dp.message(F.text == BUTTON_SUPPORT)
async def support_start(m,state):
    u=await access_user(m)
    if not u:return
    x=await db(); c=await x.execute("SELECT id FROM tickets WHERE user_id=? AND status='open' ORDER BY id DESC LIMIT 1",(u["id"],)); t=await c.fetchone()
    if not t:
        c=await x.execute("INSERT INTO tickets(user_id) VALUES(?)",(u["id"],)); tid=c.lastrowid; await x.commit()
    else:tid=t["id"]
    await x.close(); await nav_push(state,"home"); await state.update_data(ticket_id=tid); await state.set_state(S.support_message); await m.answer(f"💬 {await setting('support_text')}\n🎫 Ticket #{tid}\nپیام خود را ارسال کنید:",reply_markup=back_kb())


@dp.message(S.support_message)
async def support_message_receive(m,state):
    d=await state.get_data(); u=await get_user_by_tid(m.from_user.id); kind,_,text,_=extract_content(m); x=await db(); await x.execute("INSERT INTO ticket_messages(ticket_id,sender_id,text,content_type,telegram_message_id) VALUES(?,?,?,?,?)",(d["ticket_id"],m.from_user.id,text or "",kind or "unknown",m.message_id)); await x.commit(); await x.close()
    try:await m.bot.send_message(OWNER_ID,f"💬 تیکت #{d['ticket_id']}\n👤 {html.escape(m.from_user.full_name)}\nپیام جدید دریافت شد.",parse_mode="HTML")
    except Exception:pass
    await m.answer("✅ پیام شما ثبت شد. برای پیام بعدی دوباره ارسال کنید.",reply_markup=back_kb())


@dp.message(F.text == BTN["tickets"])
async def tickets_menu(m,state):
    if await is_admin(m.from_user.id): await support_admin(m,state,push=True)


async def support_admin(m,state,push=True):
    x=await db(); c=await x.execute("SELECT t.id,u.first_name,u.username,COUNT(tm.id) n FROM tickets t JOIN users u ON u.id=t.user_id LEFT JOIN ticket_messages tm ON tm.ticket_id=t.id WHERE t.status='open' GROUP BY t.id ORDER BY t.id DESC"); rows=await c.fetchall(); await x.close()
    if push:await nav_push(state,"tickets")
    await state.set_state(S.ticket_select); await m.answer("🎫 Ticketهای باز را انتخاب کنید:",reply_markup=markup([[kb(f"🎫 #{r['id']} | {r['first_name'] or '-'} ({r['n']})")] for r in rows]+[[kb(BUTTON_BACK,"danger")]]))


@dp.message(S.ticket_select)
async def ticket_select(m,state):
    tid=parse_id(m.text)
    if tid is None:return
    x=await db(); c=await x.execute("SELECT t.id,u.first_name,u.telegram_id FROM tickets t JOIN users u ON u.id=t.user_id WHERE t.id=?",(tid,)); t=await c.fetchone(); c=await x.execute("SELECT * FROM ticket_messages WHERE ticket_id=? ORDER BY id",(tid,)); msgs=await c.fetchall(); await x.close()
    if not t:return
    body="\n".join(f"{'👤' if z['sender_id']==t['telegram_id'] else '🛡'} {z['created_at']} | {html.escape(z['text'] or '['+z['content_type']+']')}" for z in msgs) or "بدون پیام"
    await state.update_data(ticket_id=tid,ticket_user_tid=t["telegram_id"]); await nav_push(state,"ticket_info"); await state.set_state(S.ticket_reply); await m.answer(f"🎫 <b>#{tid}</b> — {html.escape(t['first_name'] or '-') }\n\n{body}",parse_mode="HTML",reply_markup=markup([[kb(BTN["ticket_reply"],"success"),kb(BTN["ticket_close"],"danger")],[kb(BUTTON_BACK,"danger")]]))


@dp.message(F.text == BTN["ticket_reply"], S.ticket_reply)
async def ticket_reply_prompt(m,state):
    await m.answer("پاسخ را ارسال کنید:",reply_markup=back_kb())


@dp.message(F.text == BTN["ticket_close"], S.ticket_reply)
async def ticket_close(m,state):
    tid=(await state.get_data()).get("ticket_id"); x=await db(); await x.execute("UPDATE tickets SET status='closed',closed_at=? WHERE id=?",(now_iso(),tid)); await x.commit(); await x.close(); await state.clear(); await m.answer("🔒 Ticket بسته شد.",reply_markup=admin_kb())


@dp.message(S.ticket_reply)
async def ticket_reply_send(m,state):
    d=await state.get_data(); tid=d.get("ticket_id")
    if not tid:return
    if m.text in (BTN["ticket_reply"],BTN["ticket_close"]):return
    try:await m.bot.copy_message(d["ticket_user_tid"],m.chat.id,m.message_id)
    except Exception as e:return await m.answer(f"❌ ارسال نشد: {html.escape(str(e))}",parse_mode="HTML")
    kind,_,text,_=extract_content(m); x=await db(); await x.execute("INSERT INTO ticket_messages(ticket_id,sender_id,text,content_type,telegram_message_id) VALUES(?,?,?,?,?)",(tid,m.from_user.id,text or "",kind or "unknown",m.message_id)); await x.commit(); await x.close(); await m.answer("✅ پاسخ ارسال شد.",reply_markup=back_kb())


# ---------------- Admins ----------------

@dp.message(F.text == BTN["admins"])
async def admins_menu(m,state):
    if await is_admin(m.from_user.id):await admins_page(m,state,push=True)


async def admins_page(m,state,push=True):
    x=await db(); c=await x.execute("SELECT telegram_id,role FROM admins ORDER BY telegram_id"); rows=await c.fetchall(); await x.close()
    if push:await nav_push(state,"admins")
    body="👑 <b>ادمین‌ها</b>\n\nOwner اصلی: <code>%s</code>\n%s"%(OWNER_ID,"\n".join(f"• <code>{r['telegram_id']}</code> — {r['role']}" for r in rows) or "ادمین دیگری ثبت نشده.")
    await state.set_state(None); await m.answer(body,parse_mode="HTML",reply_markup=markup([[kb(BTN["admin_add"],"success"),kb(BTN["admin_delete"],"danger")],[kb(BUTTON_BACK,"danger")]]))


@dp.message(F.text == BTN["admin_add"])
async def admin_add_start(m,state):
    if m.from_user.id!=OWNER_ID:return
    await state.set_state(S.admin_add); await m.answer("Username مثل @user یا Forward پیام کاربر را ارسال کنید.",reply_markup=back_kb())


@dp.message(S.admin_add)
async def admin_add(m,state):
    if m.from_user.id!=OWNER_ID:return
    uid=None; origin=getattr(m,"forward_origin",None); sender=getattr(origin,"sender_user",None)
    if sender:uid=sender.id
    elif (m.text or "").startswith("@"):
        x=await db(); c=await x.execute("SELECT telegram_id FROM users WHERE username=?",(m.text[1:],)); r=await c.fetchone(); await x.close(); uid=r["telegram_id"] if r else None
    if not uid:return await m.answer("کاربر پیدا نشد. از Forward پیام او یا Username استفاده کنید.")
    x=await db(); await x.execute("INSERT OR IGNORE INTO admins(telegram_id) VALUES(?)",(uid,)); await x.commit(); await x.close(); await state.clear(); await admins_page(m,state,push=False)


@dp.message(F.text == BTN["admin_delete"])
async def admin_delete_start(m,state):
    if m.from_user.id!=OWNER_ID:return
    x=await db(); c=await x.execute("SELECT telegram_id,role FROM admins ORDER BY telegram_id"); rows=await c.fetchall(); await x.close(); await state.set_state(S.admin_delete); await m.answer("ادمین را انتخاب کنید:",reply_markup=markup([[kb(f"🗑 #{r['telegram_id']} | {r['role']}","danger")] for r in rows]+[[kb(BUTTON_BACK,"danger")]]))


@dp.message(S.admin_delete)
async def admin_delete(m,state):
    uid=parse_id(m.text)
    if uid is None:return
    if uid==OWNER_ID:return await m.answer("⛔ Owner اصلی قابل حذف نیست.")
    await state.update_data(delete_admin=uid); await state.set_state(S.admin_delete_confirm); await m.answer("آیا حذف شود؟",reply_markup=markup([[kb(BUTTON_YES,"danger"),kb(BUTTON_NO,"primary")],[kb(BUTTON_BACK,"danger")]]))


@dp.message(S.admin_delete_confirm)
async def admin_delete_confirm(m,state):
    if m.text==BUTTON_NO:return await admins_page(m,state,push=False)
    if m.text!=BUTTON_YES:return
    uid=(await state.get_data())["delete_admin"]; x=await db(); await x.execute("DELETE FROM admins WHERE telegram_id<>? AND telegram_id=?",(OWNER_ID,uid)); await x.commit(); await x.close(); await admins_page(m,state,push=False)


# ---------------- Forced join ----------------

@dp.message(F.text == BTN["join"])
async def channels_menu(m,state):
    if await is_admin(m.from_user.id):await channels_page(m,state,push=True)


async def channels_page(m,state,push=True):
    x=await db(); c=await x.execute("SELECT * FROM channels ORDER BY id"); rows=await c.fetchall(); await x.close()
    if push:await nav_push(state,"channels")
    body="\n".join(f"{'🟢' if r['active'] else '🔴'} #{r['id']} | {html.escape(r['title'])} | {html.escape(r['username'] or '-') }" for r in rows) or "کانالی ثبت نشده."
    await state.set_state(None); await m.answer("🔐 <b>جوین اجباری</b>\n\n"+body,parse_mode="HTML",reply_markup=markup([[kb(BTN["channel_add"],"success"),kb(BTN["channel_delete"],"danger")],[kb(BTN["channel_toggle"],"primary"),kb(BTN["channel_test"],"primary")],[kb(BUTTON_BACK,"danger")]]))


@dp.message(F.text == BTN["channel_add"])
async def channel_add_start(m,state):
    await state.set_state(S.channel_add_username); await m.answer("Username کانال مثل @channel را ارسال کنید:",reply_markup=back_kb())


@dp.message(S.channel_add_username)
async def channel_add_username(m,state):
    username=(m.text or "").strip()
    if not username.startswith("@"):return await m.answer("Username باید با @ شروع شود.")
    try:
        chat=await m.bot.get_chat(username)
        me=await m.bot.get_me()
        member=await m.bot.get_chat_member(chat.id, me.id)
        if member.status not in ("administrator", "creator"):
            return await m.answer("❌ ربات ادمین این کانال نیست یا دسترسی لازم را ندارد. ابتدا ربات را به‌عنوان Admin کانال اضافه کنید و دوباره تلاش کنید.")
    except Exception as e:
        return await m.answer("❌ ربات نتوانست کانال را بررسی کند. مطمئن شوید Username صحیح است و ربات Admin کانال است.\n\n" + html.escape(str(e)), parse_mode="HTML")
    await state.update_data(channel_username=username,channel_id=str(chat.id)); await state.set_state(S.channel_add_title); await m.answer("عنوان نمایشی کانال را بفرستید:",reply_markup=back_kb())


@dp.message(S.channel_add_title)
async def channel_add_title(m,state):
    d=await state.get_data(); x=await db(); await x.execute("INSERT INTO channels(title,chat_id,username,link) VALUES(?,?,?,?)",(m.text or d["channel_username"],d["channel_id"],d["channel_username"],f"https://t.me/{d['channel_username'].lstrip('@')}")); await x.commit(); await x.close(); await channels_page(m,state,push=False)


@dp.message(F.text == BTN["channel_delete"])
async def channel_delete_start(m,state):
    x=await db(); c=await x.execute("SELECT * FROM channels ORDER BY id"); rows=await c.fetchall(); await x.close(); await state.set_state(S.channel_delete); await m.answer("کانال را انتخاب کنید:",reply_markup=markup([[kb(f"🗑 #{r['id']} | {r['title']}","danger")] for r in rows]+[[kb(BUTTON_BACK,"danger")]]))


@dp.message(S.channel_delete)
async def channel_delete(m,state):
    cid=parse_id(m.text)
    if cid is None:return
    x=await db(); await x.execute("DELETE FROM channels WHERE id=?",(cid,)); await x.commit(); await x.close(); await channels_page(m,state,push=False)


@dp.message(F.text == BTN["channel_toggle"])
async def channel_toggle_start(m,state):
    x=await db(); c=await x.execute("SELECT * FROM channels ORDER BY id"); rows=await c.fetchall(); await x.close(); await state.set_state(S.channel_toggle); await m.answer("کانال را انتخاب کنید:",reply_markup=markup([[kb(f"🔄 #{r['id']} | {r['title']}")] for r in rows]+[[kb(BUTTON_BACK,"danger")]]))


@dp.message(S.channel_toggle)
async def channel_toggle(m,state):
    cid=parse_id(m.text)
    if cid is None:return
    x=await db(); await x.execute("UPDATE channels SET active=1-active WHERE id=?",(cid,)); await x.commit(); await x.close(); await channels_page(m,state,push=False)


@dp.message(F.text == BTN["channel_test"])
async def channel_test(m):
    if not await is_admin(m.from_user.id):return
    x=await db(); c=await x.execute("SELECT * FROM channels WHERE active=1 ORDER BY id"); channels=await c.fetchall(); await x.close()
    if not channels: return await m.answer("ℹ️ کانال فعالی ثبت نشده است.", reply_markup=admin_kb())
    me=await m.bot.get_me(); problems=[]
    for ch in channels:
        try:
            member=await m.bot.get_chat_member(ch["chat_id"], me.id)
            if member.status not in ("administrator", "creator"): problems.append(f"❌ {ch['title']}: ربات Admin نیست.")
        except Exception as e: problems.append(f"❌ {ch['title']}: دسترسی بررسی نشد ({e}).")
    if problems: return await m.answer("\n".join(problems)+"\n\nربات باید Admin کانال باشد.", reply_markup=admin_kb())
    missing=await check_required_join(m.bot,m.from_user.id)
    await m.answer("❌ عضویت ناقص است." if missing else "✅ تست عضویت و دسترسی ربات موفق بود.",reply_markup=admin_kb())


# ---------------- Broadcast ----------------

@dp.message(F.text == BTN["broadcast"])
async def broadcast_start(m,state):
    if not await is_admin(m.from_user.id):return
    await state.set_state(S.broadcast); await m.answer("پیام یا Media برای Broadcast ارسال کنید:",reply_markup=back_kb())


@dp.message(S.broadcast)
async def broadcast_send(m,state):
    x=await db(); c=await x.execute("SELECT telegram_id FROM users WHERE blocked=0 AND course_access=1"); users=await c.fetchall(); await x.close(); ok=bad=0
    for u in users:
        try:await m.bot.copy_message(u["telegram_id"],m.chat.id,m.message_id); ok+=1
        except Exception as e: bad+=1; log.warning("Broadcast failed for %s: %s",u["telegram_id"],e)
    await state.clear(); await m.answer(f"📣 Broadcast تمام شد.\n✅ موفق: {ok}\n❌ ناموفق: {bad}",reply_markup=admin_kb())


# ---------------- Statistics ----------------

@dp.message(F.text == BTN["stats"])
async def stats(m):
    if not await is_admin(m.from_user.id):return
    x=await db()
    async def n(q,args=()):
        c=await x.execute(q,args); r=await c.fetchone(); return r[0] or 0
    now=datetime.now(timezone.utc); day=now.date().isoformat(); week=(now-timedelta(days=7)).isoformat(); month=(now-timedelta(days=30)).isoformat()
    vals={
      "users":await n("SELECT COUNT(*) FROM users"),"active":await n("SELECT COUNT(*) FROM users WHERE last_activity>=?",(week,)),"today":await n("SELECT COUNT(*) FROM users WHERE created_at>=?",(day,)),"week":await n("SELECT COUNT(*) FROM users WHERE created_at>=?",(week,)),"month":await n("SELECT COUNT(*) FROM users WHERE created_at>=?",(month,)),"chapters":await n("SELECT COUNT(*) FROM chapters"),"lessons":await n("SELECT COUNT(*) FROM lessons"),"published":await n("SELECT COUNT(*) FROM lessons WHERE published=1"),"quizzes":await n("SELECT COUNT(*) FROM quizzes"),"tickets":await n("SELECT COUNT(*) FROM tickets"),"blocked":await n("SELECT COUNT(*) FROM users WHERE blocked=1"),"completed":await n("SELECT COUNT(DISTINCT user_id) FROM progress WHERE completed_at IS NOT NULL"),"passed":await n("SELECT COUNT(*) FROM attempts WHERE passed=1"),"failed":await n("SELECT COUNT(*) FROM attempts WHERE passed=0")}
    c=await x.execute("SELECT AVG(v) a FROM (SELECT user_id,AVG(CASE WHEN completed_at IS NOT NULL THEN 1.0 ELSE 0 END) v FROM progress GROUP BY user_id)"); avg=(await c.fetchone())["a"] or 0
    c=await x.execute("SELECT l.title,COUNT(*) n FROM progress p JOIN lessons l ON l.id=p.lesson_id WHERE p.completed_at IS NOT NULL GROUP BY l.id ORDER BY n DESC LIMIT 5"); popular=await c.fetchall(); await x.close()
    pop="\n".join(f"• {r['title']} — {r['n']}" for r in popular) or "—"
    await m.answer(f"📊 <b>آمار</b>\n👥 کل: {vals['users']}\n🟢 فعال: {vals['active']}\n🆕 امروز: {vals['today']} | هفته: {vals['week']} | ماه: {vals['month']}\n📚 فصل: {vals['chapters']} | 🎬 درس: {vals['lessons']} | منتشر: {vals['published']}\n📝 آزمون: {vals['quizzes']}\n🎫 Ticket: {vals['tickets']}\n🚫 Block: {vals['blocked']}\n📈 میانگین Progress: {round(avg*100,1)}%\n🏁 تکمیل دوره: {vals['completed']}\n🏆 قبول: {vals['passed']} | ❌ رد: {vals['failed']}\n\n🔥 محبوب‌ترین درس‌ها:\n{pop}",parse_mode="HTML",reply_markup=admin_kb())


# ---------------- Settings ----------------

@dp.message(F.text == BTN["settings"])
async def settings_menu_handler(m,state):
    if await is_admin(m.from_user.id):await state.clear(); await settings_page(m,state,push=True)


async def settings_page(m,state,push=True):
    if push:await state.update_data(nav=["admin","settings"])
    vals={k:await setting(k) for k in ("bot_enabled","forced_join_enabled","quiz_enabled","registration_enabled","default_retry_mode")}
    await state.set_state(None)
    await m.answer(f"⚙️ <b>تنظیمات</b>\n🤖 ربات: {'فعال' if vals['bot_enabled']=='1' else 'غیرفعال'}\n🔐 Forced Join: {'فعال' if vals['forced_join_enabled']=='1' else 'غیرفعال'}\n📝 آزمون: {'فعال' if vals['quiz_enabled']=='1' else 'غیرفعال'}\n📝 ثبت‌نام: {'فعال' if vals['registration_enabled']=='1' else 'غیرفعال'}\n🔁 تلاش مجدد پیش‌فرض: {vals['default_retry_mode']}",parse_mode="HTML",reply_markup=markup([[kb(BTN["settings_bot"]),kb(BTN["settings_join"])],[kb(BTN["settings_quiz"]),kb(BTN["settings_reg"])],[kb(BTN["settings_start"]),kb(BTN["settings_support"])],[kb(BTN["settings_lesson"]),kb(BTN["settings_retry"])],[kb(BUTTON_BACK,"danger")]]))


@dp.message(F.text.in_({BTN["settings_bot"],BTN["settings_join"],BTN["settings_quiz"],BTN["settings_reg"]}))
async def settings_toggle(m,state):
    key={BTN["settings_bot"]:"bot_enabled",BTN["settings_join"]:"forced_join_enabled",BTN["settings_quiz"]:"quiz_enabled",BTN["settings_reg"]:"registration_enabled"}[m.text]; await set_setting(key,"0" if await setting(key,"1")=="1" else "1"); await settings_page(m,state,push=False)


@dp.message(F.text.in_({BTN["settings_start"],BTN["settings_support"],BTN["settings_lesson"]}))
async def settings_text_start(m,state):
    key={BTN["settings_start"]:"start_text",BTN["settings_support"]:"support_text",BTN["settings_lesson"]:"lesson_text"}[m.text]; await state.set_state(S.settings_value); await state.update_data(settings_key=key); await m.answer("متن جدید را ارسال کنید:",reply_markup=back_kb())


@dp.message(S.settings_value)
async def settings_text_save(m,state):
    key=(await state.get_data()).get("settings_key"); await set_setting(key,m.text or ""); await settings_page(m,state,push=False)


@dp.message(F.text == BTN["settings_retry"])
async def settings_retry(m,state):
    cur=await setting("default_retry_mode","retry"); new="complete" if cur=="retry" else "retry"; await set_setting("default_retry_mode",new); await settings_page(m,state,push=False)


# ---------------- Admin command fallbacks / errors ----------------

async def on_startup(bot):
    verify_keyboard_api(); await init_db(); log.info("Bot startup complete; DB=%s",DB)


async def main():
    if not TOKEN: raise RuntimeError("BOT_TOKEN is not set")
    bot=Bot(TOKEN); await on_startup(bot); await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
