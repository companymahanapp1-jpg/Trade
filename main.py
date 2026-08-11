
import asyncio
import html
import logging
import os
import re
from datetime import datetime, timedelta, timezone

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

# Premium Custom Emoji IDs supplied with the original project.
START_E = os.getenv("START_EMOJI_ID", "5935946026308342844")
SUPPORT_E = os.getenv("SUPPORT_EMOJI_ID", "5938359183748370657")
ADMIN_E = os.getenv("ADMIN_EMOJI_ID", "5935933089866846598")
CHAPTER_E = "5938069973535559743"

# Central button text registry. These strings are the actual Telegram button text.
BUTTON_START = "شروع یادگیری"
BUTTON_SUPPORT = "پشتیبانی"
BUTTON_ADMIN = "پنل مدیریت"
BUTTON_BACK = "بازگشت"
BUTTON_YES = "بله، حذف شود"
BUTTON_NO = "لغو"
BUTTON_SKIP = "رد کردن"
BUTTON_NEXT = "بعدی"

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
log = logging.getLogger("trading_course_bot")

dp = Dispatcher()
runtime_bot = None


# ---------------- Database ----------------

async def db():
    os.makedirs(os.path.dirname(DB) or ".", exist_ok=True)
    conn = await aiosqlite.connect(DB)
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA foreign_keys=ON")
    return conn


async def init_db():
    x = await db()
    await x.executescript("""
    CREATE TABLE IF NOT EXISTS settings(
        key TEXT PRIMARY KEY, value TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_id INTEGER UNIQUE NOT NULL,
        username TEXT, first_name TEXT, last_name TEXT,
        blocked INTEGER DEFAULT 0, course_access INTEGER DEFAULT 1,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        last_activity TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS admins(
        telegram_id INTEGER PRIMARY KEY, role TEXT DEFAULT 'admin',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS chapters(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL, description TEXT DEFAULT '',
        position INTEGER DEFAULT 0, active INTEGER DEFAULT 1,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS lessons(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chapter_id INTEGER REFERENCES chapters(id) ON DELETE SET NULL,
        title TEXT NOT NULL, description TEXT DEFAULT '',
        position INTEGER DEFAULT 0,
        content_type TEXT DEFAULT '', content_file_id TEXT DEFAULT '',
        content_text TEXT DEFAULT '',
        telegram_message_id INTEGER DEFAULT 0,
        duration INTEGER DEFAULT 0,
        active INTEGER DEFAULT 1, published INTEGER DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS quizzes(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lesson_id INTEGER UNIQUE REFERENCES lessons(id) ON DELETE CASCADE,
        pass_percent INTEGER DEFAULT 70, time_limit INTEGER DEFAULT 180,
        retry_mode TEXT DEFAULT 'retry', created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS questions(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        quiz_id INTEGER REFERENCES quizzes(id) ON DELETE CASCADE,
        text TEXT NOT NULL, position INTEGER DEFAULT 0, timer INTEGER DEFAULT 30
    );
    CREATE TABLE IF NOT EXISTS options(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        question_id INTEGER REFERENCES questions(id) ON DELETE CASCADE,
        text TEXT NOT NULL, is_correct INTEGER DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS progress(
        user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
        lesson_id INTEGER REFERENCES lessons(id) ON DELETE CASCADE,
        video_started TEXT, video_done INTEGER DEFAULT 0,
        quiz_passed INTEGER DEFAULT 0, completed_at TEXT,
        PRIMARY KEY(user_id, lesson_id)
    );
    CREATE TABLE IF NOT EXISTS attempts(
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
        quiz_id INTEGER, score INTEGER DEFAULT 0, passed INTEGER DEFAULT 0,
        started_at TEXT, finished_at TEXT
    );
    CREATE TABLE IF NOT EXISTS channels(
        id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL,
        chat_id TEXT NOT NULL, username TEXT DEFAULT '', link TEXT DEFAULT '',
        active INTEGER DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS tickets(
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
        status TEXT DEFAULT 'open', created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        closed_at TEXT
    );
    CREATE TABLE IF NOT EXISTS ticket_messages(
        id INTEGER PRIMARY KEY AUTOINCREMENT, ticket_id INTEGER,
        sender_id INTEGER, text TEXT DEFAULT '', content_type TEXT DEFAULT 'text',
        telegram_message_id INTEGER DEFAULT 0, created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """)
    # Non-destructive migrations from the supplied V3 database.
    migrations = {
        "users": [("last_name", "TEXT"), ("course_access", "INTEGER DEFAULT 1"), ("last_activity", "TEXT")],
        "lessons": [
            ("content_type", "TEXT DEFAULT ''"), ("content_file_id", "TEXT DEFAULT ''"),
            ("content_text", "TEXT DEFAULT ''"), ("telegram_message_id", "INTEGER DEFAULT 0"),
            ("published", "INTEGER DEFAULT 0"), ("created_at", "TEXT DEFAULT CURRENT_TIMESTAMP")
        ],
        "questions": [("timer", "INTEGER DEFAULT 30")],
        "tickets": [("closed_at", "TEXT")],
        "ticket_messages": [
            ("content_type", "TEXT DEFAULT 'text'"), ("telegram_message_id", "INTEGER DEFAULT 0")
        ],
    }
    for table, cols in migrations.items():
        cur = await x.execute(f"PRAGMA table_info({table})")
        existing = {r["name"] for r in await cur.fetchall()}
        for name, typ in cols:
            if name not in existing:
                await x.execute(f"ALTER TABLE {table} ADD COLUMN {name} {typ}")
    # Preserve V3 lesson media instead of discarding the old video_file_id field.
    try:
        await x.execute("""UPDATE lessons SET content_type='video', content_file_id=video_file_id
                           WHERE (content_file_id IS NULL OR content_file_id='') AND video_file_id IS NOT NULL AND video_file_id<>''""")
    except Exception:
        pass
    defaults = {
        "registration_enabled": "1", "quiz_enabled": "1", "forced_join_enabled": "1",
        "start_text": "آکادمی آموزش ترید؛ آموزش‌ها مرحله‌به‌مرحله هستند.",
        "support_text": "پیامت را ارسال کن تا پشتیبانی بررسی کند.",
        "lesson_text": "درس‌ها به ترتیب باز می‌شوند. ابتدا درس قبلی را کامل کن.",
        "bot_enabled": "1", "default_retry_mode": "retry"
    }
    for k, v in defaults.items():
        await x.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)", (k, v))
    await x.commit()
    await x.close()


async def setting(key, default=""):
    x = await db()
    c = await x.execute("SELECT value FROM settings WHERE key=?", (key,))
    r = await c.fetchone()
    await x.close()
    return r["value"] if r else default


async def set_setting(key, value):
    x = await db()
    await x.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, str(value)))
    await x.commit()
    await x.close()


async def is_admin(uid):
    if uid == OWNER_ID:
        return True
    x = await db()
    c = await x.execute("SELECT 1 FROM admins WHERE telegram_id=?", (uid,))
    r = await c.fetchone()
    await x.close()
    return bool(r)


async def ensure_user(u):
    now = datetime.now(timezone.utc).isoformat()
    x = await db()
    await x.execute("""
        INSERT INTO users(telegram_id,username,first_name,last_name,last_activity)
        VALUES(?,?,?,?,?)
        ON CONFLICT(telegram_id) DO UPDATE SET
        username=excluded.username, first_name=excluded.first_name,
        last_name=excluded.last_name, last_activity=excluded.last_activity
    """, (u.id, u.username, u.first_name, u.last_name, now))
    await x.commit()
    c = await x.execute("SELECT * FROM users WHERE telegram_id=?", (u.id,))
    r = await c.fetchone()
    await x.close()
    return r


# ---------------- Keyboard / Navigation ----------------

def verify_keyboard_api():
    fields = getattr(KeyboardButton, "model_fields", {})
    missing = [f for f in ("style", "icon_custom_emoji_id") if f not in fields]
    if missing:
        raise RuntimeError(
            "This aiogram version does not expose Telegram Bot API KeyboardButton "
            f"fields: {', '.join(missing)}. Upgrade aiogram; do not downgrade."
        )


def kb(text, style="primary", emoji_id=None):
    args = {"text": text}
    if style:
        args["style"] = style
    if emoji_id:
        args["icon_custom_emoji_id"] = str(emoji_id)
    return KeyboardButton(**args)


def markup(rows):
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, is_persistent=True)


def user_kb(admin=False):
    rows = [[kb(BUTTON_START, "success", START_E), kb(BUTTON_SUPPORT, "primary", SUPPORT_E)]]
    if admin:
        rows.append([kb(BUTTON_ADMIN, "primary", ADMIN_E)])
    return markup(rows)


def back_kb(*extra):
    rows = []
    if extra:
        rows.append([kb(v, "primary") for v in extra])
    rows.append([kb(BUTTON_BACK, "danger")])
    return markup(rows)


def admin_kb():
    return markup([
        [kb("📚 مدیریت فصل‌ها", "success"), kb("🎬 مدیریت درس‌ها", "success")],
        [kb("📝 مدیریت آزمون‌ها", "primary"), kb("👥 کاربران", "primary")],
        [kb("👑 ادمین‌ها", "primary"), kb("💬 پیام‌های پشتیبانی", "primary")],
        [kb("📢 جوین اجباری", "success"), kb("📣 پیام همگانی", "primary")],
        [kb("📊 آمار", "success"), kb("⚙️ تنظیمات", "primary")],
        [kb(BUTTON_BACK, "danger")]
    ])


def simple_menu(*rows):
    return markup([[kb(a, style) for a, style in row] for row in rows] + [[kb(BUTTON_BACK, "danger")]])


def parse_id(text):
    m = re.search(r"#(\d+)", text or "")
    return int(m.group(1)) if m else None


async def push_nav(state: FSMContext, screen):
    data = await state.get_data()
    stack = list(data.get("nav_stack", []))
    if not stack or stack[-1] != screen:
        stack.append(screen)
    await state.update_data(nav_stack=stack)


async def pop_nav(state: FSMContext):
    data = await state.get_data()
    stack = list(data.get("nav_stack", []))
    if len(stack) > 1:
        stack.pop()
        await state.update_data(nav_stack=stack)
        return stack[-1]
    return "home"


async def home(m):
    if await setting("bot_enabled", "1") != "1" and not await is_admin(m.from_user.id):
        return await m.answer("⛔ ربات موقتاً غیرفعال است.")
    text = await setting("start_text")
    await m.answer(f"✨ <b>آکادمی آموزش ترید</b>\n\n{html.escape(text)}",
                   parse_mode="HTML", reply_markup=user_kb(await is_admin(m.from_user.id)))


# ---------------- Content / Join ----------------

def extract_content(m):
    if m.video:
        return "video", m.video.file_id, "", m.video.duration or 0
    if m.document:
        return "document", m.document.file_id, "", 0
    if m.photo:
        return "photo", m.photo[-1].file_id, "", 0
    if m.audio:
        return "audio", m.audio.file_id, "", m.audio.duration or 0
    if m.voice:
        return "voice", m.voice.file_id, "", 0
    if m.animation:
        return "animation", m.animation.file_id, "", m.animation.duration or 0
    if m.video_note:
        return "video_note", m.video_note.file_id, "", 0
    if m.text:
        return "text", "", m.text, 0
    if m.sticker:
        return "sticker", m.sticker.file_id, "", 0
    return None, "", "", 0


async def send_saved_content(bot, chat_id, lesson):
    t = lesson["content_type"]
    fid = lesson["content_file_id"]
    text = lesson["content_text"]
    if t == "video":
        return await bot.send_video(chat_id, fid, caption=lesson["description"] or None)
    if t == "document":
        return await bot.send_document(chat_id, fid, caption=lesson["description"] or None)
    if t == "photo":
        return await bot.send_photo(chat_id, fid, caption=lesson["description"] or None)
    if t == "audio":
        return await bot.send_audio(chat_id, fid, caption=lesson["description"] or None)
    if t == "voice":
        return await bot.send_voice(chat_id, fid)
    if t == "animation":
        return await bot.send_animation(chat_id, fid, caption=lesson["description"] or None)
    if t == "video_note":
        return await bot.send_video_note(chat_id, fid)
    if t == "sticker":
        return await bot.send_sticker(chat_id, fid)
    return await bot.send_message(chat_id, text or "")


async def check_required_join(bot, uid):
    if await setting("forced_join_enabled", "1") != "1":
        return []
    x = await db()
    c = await x.execute("SELECT * FROM channels WHERE active=1 ORDER BY id")
    channels = await c.fetchall()
    await x.close()
    missing = []
    for ch in channels:
        try:
            member = await bot.get_chat_member(ch["chat_id"], uid)
            if member.status in ("left", "kicked"):
                missing.append(ch)
        except Exception:
            missing.append(ch)
    return missing


# ---------------- States ----------------

class S(StatesGroup):
    # chapter
    add_ch_title = State(); add_ch_desc = State(); add_ch_dup = State()
    chapter_select = State(); edit_ch_select = State(); edit_ch_title = State(); edit_ch_desc = State()
    delete_ch_select = State(); delete_ch_confirm = State(); reorder_ch_select = State(); reorder_ch_target = State()
    # lesson
    add_l_title = State(); add_l_dup = State(); add_l_chapter = State(); add_l_desc = State()
    add_l_content = State(); add_l_duration = State()
    lesson_select = State(); edit_l_select = State(); edit_l_field = State(); edit_l_value = State(); edit_l_chapter = State(); edit_l_content = State()
    delete_l_select = State(); delete_l_confirm = State()
    publish_l_select = State()
    # quiz
    quiz_lesson_select = State(); quiz_pass = State(); quiz_time = State(); quiz_retry = State()
    question_quiz_select = State(); question_select = State(); question_text = State()
    question_options = State(); question_correct = State(); question_timer = State()
    edit_q_select = State(); edit_q_text = State(); delete_q_select = State(); delete_q_confirm = State(); quiz_delete_select = State(); quiz_delete_confirm = State(); delete_question_select = State()
    # users
    user_search = State(); user_select = State(); user_action = State(); user_message = State()
    # support
    ticket_select = State(); ticket_reply = State()
    # admins
    add_admin = State(); delete_admin_select = State(); delete_admin_confirm = State()
    # channels
    add_channel_username = State(); add_channel_title = State(); delete_channel_select = State(); toggle_channel_select = State()
    # broadcast
    broadcast = State()
    # settings
    settings_value = State()
    # learner
    lesson_learn_select = State(); quiz_answer = State()


# ---------------- Common back ----------------

async def go_back(m: Message, state: FSMContext):
    if await is_admin(m.from_user.id):
        # For nested screens, use stored screen marker to provide a practical stack.
        data = await state.get_data()
        screen = data.get("screen")
        await state.clear()
        if screen and screen.startswith("chapter"):
            return await m.answer("📚 مدیریت فصل‌ها", reply_markup=chapter_menu())
        if screen and screen.startswith("lesson"):
            return await m.answer("🎬 مدیریت درس‌ها", reply_markup=lesson_menu())
        if screen and screen.startswith("quiz"):
            return await m.answer("📝 مدیریت آزمون‌ها", reply_markup=quiz_menu())
        return await m.answer("👑 پنل مدیریت", reply_markup=admin_kb())
    await state.clear()
    await home(m)


@dp.message(F.text == BUTTON_BACK)
async def back_handler(m: Message, state: FSMContext):
    await go_back(m, state)


# ---------------- Start / user menu ----------------

@dp.message(CommandStart())
async def start(m: Message, state: FSMContext):
    await state.clear()
    u = await ensure_user(m.from_user)
    if u["blocked"]:
        return await m.answer("⛔ دسترسی شما مسدود شده است.")
    if not u["course_access"]:
        return await m.answer("⛔ دسترسی شما به دوره محدود شده است.")
    missing = await check_required_join(m.bot, m.from_user.id)
    if missing:
        lines = []
        for c in missing:
            link = c["link"] or (f"https://t.me/{c['username'].lstrip('@')}" if c["username"] else c["chat_id"])
            lines.append(f"📢 {html.escape(c['title'])}: {html.escape(link)}")
        return await m.answer("🔐 <b>عضویت اجباری</b>\n\nابتدا عضو کانال‌های زیر شوید و سپس /start را بزنید:\n\n" + "\n".join(lines),
                               parse_mode="HTML", reply_markup=user_kb(await is_admin(m.from_user.id)))
    await home(m)


@dp.message(F.text == BUTTON_START)
async def user_learning(m: Message, state: FSMContext):
    u = await ensure_user(m.from_user)
    if u["blocked"] or not u["course_access"]:
        return await m.answer("⛔ دسترسی شما محدود شده است.")
    missing = await check_required_join(m.bot, m.from_user.id)
    if missing:
        return await m.answer("🔐 ابتدا عضویت اجباری را کامل کنید و دوباره تلاش کنید.")
    x = await db()
    c = await x.execute("SELECT l.*,c.title ct FROM lessons l LEFT JOIN chapters c ON c.id=l.chapter_id WHERE l.published=1 ORDER BY COALESCE(c.position,999999),l.position,l.id")
    lessons = await c.fetchall()
    await x.close()
    if not lessons:
        return await m.answer("📚 هنوز آموزش منتشر نشده است.", reply_markup=user_kb(await is_admin(m.from_user.id)))
    await state.set_state(S.lesson_learn_select)
    await state.update_data(screen="learner")
    rows = []
    for l in lessons:
        rows.append([kb(f"🔒 #{l['id']} | {l['title']}", "primary")])
    await m.answer(await setting("lesson_text"), reply_markup=markup(rows + [[kb(BUTTON_BACK, "danger")]]))


@dp.message(S.lesson_learn_select)
async def learner_select(m: Message, state: FSMContext):
    lid = parse_id(m.text)
    if not lid:
        return await m.answer("لطفاً درس را از کیبورد انتخاب کنید.")
    x = await db()
    c = await x.execute("SELECT l.*,c.title ct FROM lessons l LEFT JOIN chapters c ON c.id=l.chapter_id WHERE l.id=? AND l.published=1", (lid,))
    lesson = await c.fetchone()
    c = await x.execute("SELECT id FROM users WHERE telegram_id=?", (m.from_user.id,))
    user = await c.fetchone()
    await x.close()
    if not lesson or not user:
        return await m.answer("❌ درس پیدا نشد.")
    # Sequential lock: only the immediately preceding published lesson blocks access.
    x = await db()
    c = await x.execute("""
        SELECT l.id,l.position,COALESCE(c.position,999999) chapter_pos,
               COALESCE(p.quiz_passed,0) quiz_passed,COALESCE(p.video_done,0) video_done
        FROM lessons l LEFT JOIN chapters c ON c.id=l.chapter_id
        LEFT JOIN progress p ON p.lesson_id=l.id AND p.user_id=?
        WHERE l.published=1
        ORDER BY chapter_pos,l.position,l.id
    """,(user["id"],))
    ordered=await c.fetchall()
    await x.close()
    idx=next((i for i,r in enumerate(ordered) if r["id"]==lid),0)
    if idx>0:
        prev=ordered[idx-1]
        x=await db();c=await x.execute("SELECT id FROM quizzes WHERE lesson_id=?",(prev["id"],));q=await c.fetchone();await x.close()
        if q and not prev["quiz_passed"]:
            return await m.answer("🔒 این درس قفل است؛ ابتدا درس قبلی و آزمون آن را با موفقیت کامل کنید.")
        if not q and not prev["video_done"]:
            return await m.answer("🔒 این درس قفل است؛ ابتدا درس قبلی را کامل کنید.")
    await state.update_data(lesson_id=lid)
    await send_saved_content(m.bot, m.chat.id, lesson)
    x = await db()
    await x.execute("""INSERT INTO progress(user_id,lesson_id,video_started) VALUES(?,?,?)
        ON CONFLICT(user_id,lesson_id) DO UPDATE SET video_started=COALESCE(progress.video_started,excluded.video_started)""",
        (user["id"], lid, datetime.now(timezone.utc).isoformat()))
    c = await x.execute("SELECT id FROM quizzes WHERE lesson_id=?", (lid,))
    quiz = await c.fetchone()
    await x.commit(); await x.close()
    if quiz and await setting("quiz_enabled", "1") == "1":
        await m.answer("📝 محتوای درس ارسال شد. برای شروع آزمون آماده‌ای؟",
                       reply_markup=markup([[kb("📝 شروع آزمون", "success")], [kb(BUTTON_BACK, "danger")]]))
    else:
        x = await db()
        await x.execute("UPDATE progress SET video_done=1,completed_at=? WHERE user_id=? AND lesson_id=?",
                        (datetime.now(timezone.utc).isoformat(), user["id"], lid))
        await x.commit(); await x.close()
        await m.answer("✅ درس تکمیل شد.", reply_markup=user_kb(await is_admin(m.from_user.id)))


@dp.message(F.text == "📝 شروع آزمون", S.lesson_learn_select)
async def learner_quiz_start(m: Message, state: FSMContext):
    data = await state.get_data()
    lid = data.get("lesson_id")
    if not lid:
        return await m.answer("آزمون انتخاب نشده است.")
    x = await db()
    c = await x.execute("SELECT * FROM quizzes WHERE lesson_id=?", (lid,))
    quiz = await c.fetchone()
    c = await x.execute("SELECT * FROM questions WHERE quiz_id=? ORDER BY position,id", (quiz["id"],)) if quiz else None
    questions = await c.fetchall() if c else []
    await x.close()
    if not quiz or not questions:
        return await m.answer("این درس هنوز سؤال آزمون ندارد.")
    await state.update_data(quiz_id=quiz["id"], q_index=0, score=0, started=datetime.now(timezone.utc).isoformat())
    await send_question(m, state)


async def send_question(m, state):
    await send_question_to_bot(m.bot, m.chat.id, m.from_user.id, state)


async def send_question_to_bot(bot, chat_id, user_id, state):
    data = await state.get_data()
    x = await db()
    c = await x.execute("SELECT * FROM questions WHERE quiz_id=? ORDER BY position,id", (data["quiz_id"],))
    questions = await c.fetchall()
    if not questions or data.get("q_index", 0) >= len(questions):
        await x.close()
        return
    q = questions[data["q_index"]]
    c = await x.execute("SELECT * FROM options WHERE question_id=? ORDER BY id", (q["id"],))
    opts = await c.fetchall()
    await x.close()
    await state.set_state(S.quiz_answer)
    deadline = asyncio.get_running_loop().time() + q["timer"]
    await state.update_data(question_id=q["id"], deadline=deadline)
    rows = [[kb(f"🔹 {o['text']}", "primary")] for o in opts]
    await bot.send_message(chat_id, f"❓ <b>{html.escape(q['text'])}</b>\n\n⏱ {q['timer']} ثانیه",
                           parse_mode="HTML", reply_markup=markup(rows + [[kb(BUTTON_BACK, "danger")]]))
    asyncio.create_task(question_timeout(bot, chat_id, user_id, state, q["timer"], q["id"]))


async def question_timeout(bot, chat_id, user_id, state, seconds, question_id):
    await asyncio.sleep(max(1, seconds))
    data = await state.get_data()
    if data.get("question_id") != question_id:
        return
    if data.get("deadline", 0) > asyncio.get_running_loop().time():
        return
    # Timeout is a real answer event: record no answer, advance, and eventually score the attempt.
    x = await db()
    c = await x.execute("SELECT * FROM questions WHERE quiz_id=? ORDER BY position,id", (data["quiz_id"],))
    questions = await c.fetchall()
    idx = data["q_index"] + 1
    score = data.get("score", 0)
    await x.close()
    await state.update_data(q_index=idx, score=score, question_id=None)
    await bot.send_message(chat_id, "⏰ زمان این سؤال تمام شد.")
    if idx < len(questions):
        await send_question_to_bot(bot, chat_id, user_id, state)
        return
    # Finish attempt exactly like a normal final answer.
    x = await db()
    c = await x.execute("SELECT * FROM quizzes WHERE id=?", (data["quiz_id"],)); quiz = await c.fetchone()
    c = await x.execute("SELECT id FROM users WHERE telegram_id=?", (user_id,)); u = await c.fetchone()
    passed = (score * 100 // len(questions)) >= quiz["pass_percent"]
    now = datetime.now(timezone.utc).isoformat()
    await x.execute("INSERT INTO attempts(user_id,quiz_id,score,passed,started_at,finished_at) VALUES(?,?,?,?,?,?)",
                    (u["id"], quiz["id"], score, int(passed), data.get("started"), now))
    await x.execute("""INSERT INTO progress(user_id,lesson_id,video_done,quiz_passed,completed_at)
                       VALUES(?,?,?,?,?) ON CONFLICT(user_id,lesson_id) DO UPDATE SET
                       video_done=1,quiz_passed=excluded.quiz_passed,completed_at=excluded.completed_at""",
                    (u["id"], data["lesson_id"], 1, int(passed), now if passed else None))
    await x.commit(); await x.close(); await state.clear()
    await bot.send_message(chat_id,
        f"{'🏆 قبول شدی!' if passed else '❌ قبول نشدی.'}\nنمره: {score}/{len(questions)}",
        reply_markup=user_kb(await is_admin(user_id)))




# ---------------- Chapter management ----------------

def chapter_menu():
    return markup([
        [kb("➕ افزودن فصل", "success"), kb("📋 لیست فصل‌ها", "primary")],
        [kb("✏️ ویرایش فصل", "primary"), kb("🗑 حذف فصل", "danger")],
        [kb("↕️ تغییر ترتیب فصل‌ها", "primary")],
        [kb(BUTTON_BACK, "danger")]
    ])


@dp.message(F.text == "📚 مدیریت فصل‌ها")
async def chapter_menu_handler(m, state):
    if await is_admin(m.from_user.id):
        await state.clear(); await state.update_data(screen="chapter_menu")
        await m.answer("📚 مدیریت فصل‌ها", reply_markup=chapter_menu())


@dp.message(F.text == "➕ افزودن فصل")
async def add_chapter(m, state):
    if not await is_admin(m.from_user.id): return
    await state.set_state(S.add_ch_title); await state.update_data(screen="chapter_add")
    await m.answer("عنوان فصل را ارسال کنید:", reply_markup=back_kb())


@dp.message(S.add_ch_title)
async def add_chapter_title(m, state):
    title = (m.text or "").strip()
    if not title: return await m.answer("عنوان معتبر ارسال کنید.")
    x = await db(); c = await x.execute("SELECT id FROM chapters WHERE title=? LIMIT 1", (title,)); dup = await c.fetchone(); await x.close()
    await state.update_data(title=title)
    if dup:
        await state.set_state(S.add_ch_dup)
        return await m.answer("⚠️ فصلی با این عنوان وجود دارد. با همین عنوان ادامه می‌دهید؟",
                               reply_markup=markup([[kb("بله، ادامه بده", "success"), kb("عنوان جدید", "danger")],
                                                    [kb(BUTTON_BACK, "danger")]]))
    await state.set_state(S.add_ch_desc)
    await m.answer("توضیحات فصل را بفرستید یا «رد کردن» را بزنید.",
                    reply_markup=markup([[kb(BUTTON_SKIP, "primary")], [kb(BUTTON_BACK, "danger")]]))


@dp.message(S.add_ch_dup)
async def add_ch_dup(m, state):
    if m.text == "عنوان جدید":
        await state.set_state(S.add_ch_title); return await m.answer("عنوان جدید فصل را بفرستید:")
    if m.text != "بله، ادامه بده": return await m.answer("یکی از گزینه‌های کیبورد را انتخاب کنید.")
    await state.set_state(S.add_ch_desc)
    await m.answer("توضیحات فصل را بفرستید یا «رد کردن» را بزنید.",
                    reply_markup=markup([[kb(BUTTON_SKIP, "primary")], [kb(BUTTON_BACK, "danger")]]))


@dp.message(S.add_ch_desc)
async def add_ch_desc(m, state):
    d = "" if m.text == BUTTON_SKIP else (m.text or "")
    z = await state.get_data()
    x = await db()
    c = await x.execute("SELECT COALESCE(MAX(position),0)+1 p FROM chapters"); pos = (await c.fetchone())["p"]
    await x.execute("INSERT INTO chapters(title,description,position) VALUES(?,?,?)", (z["title"], d, pos))
    await x.commit(); await x.close(); await state.clear()
    await m.answer("✅ فصل ساخته شد.", reply_markup=chapter_menu())


async def chapter_rows():
    x=await db(); c=await x.execute("SELECT * FROM chapters ORDER BY position,id"); rows=await c.fetchall(); await x.close(); return rows


@dp.message(F.text == "📋 لیست فصل‌ها")
async def chapter_list(m):
    if not await is_admin(m.from_user.id): return
    rows = await chapter_rows()
    if not rows: return await m.answer("📚 فصلی وجود ندارد.", reply_markup=chapter_menu())
    await m.answer("📋 فصل‌ها:", reply_markup=markup([[kb(f"📚 #{r['id']} | {r['title']}", "primary")] for r in rows] + [[kb(BUTTON_BACK,"danger")]]))


@dp.message(F.text.regexp(r"^📚 #\d+ \|"))
async def chapter_info(m, state):
    if not await is_admin(m.from_user.id): return
    cid=parse_id(m.text)
    x=await db(); c=await x.execute("SELECT * FROM chapters WHERE id=?", (cid,)); r=await c.fetchone()
    c=await x.execute("SELECT COUNT(*) n FROM lessons WHERE chapter_id=?", (cid,)); n=(await c.fetchone())["n"]; await x.close()
    if not r: return await m.answer("❌ فصل پیدا نشد.")
    await state.update_data(selected_chapter=cid,screen="chapter_info")
    await m.answer(f"📚 <b>{html.escape(r['title'])}</b>\n\n📝 {html.escape(r['description'] or '—')}\n🎬 درس‌ها: {n}",
                   parse_mode="HTML", reply_markup=markup([[kb("✏️ ویرایش همین فصل","primary"),kb("🗑 حذف همین فصل","danger")],
                                                            [kb(BUTTON_BACK,"danger")]]))


@dp.message(F.text == "✏️ ویرایش فصل")
async def edit_chapter_start(m,state):
    if not await is_admin(m.from_user.id): return
    rows=await chapter_rows()
    await state.set_state(S.edit_ch_select); await state.update_data(screen="chapter_edit")
    await m.answer("فصل را انتخاب کنید:", reply_markup=markup([[kb(f"📚 #{r['id']} | {r['title']}","primary")] for r in rows]+[[kb(BUTTON_BACK,"danger")]]))


@dp.message(F.text == "✏️ ویرایش همین فصل")
async def edit_same_chapter(m,state):
    cid=(await state.get_data()).get("selected_chapter")
    if cid:
        await state.update_data(chapter_edit_id=cid); await state.set_state(S.edit_ch_title)
        return await m.answer("عنوان جدید فصل:", reply_markup=back_kb())
    await edit_chapter_start(m,state)


@dp.message(S.edit_ch_select)
async def edit_ch_select(m,state):
    cid=parse_id(m.text)
    if not cid: return await m.answer("فصل را از کیبورد انتخاب کنید.")
    await state.update_data(chapter_edit_id=cid); await state.set_state(S.edit_ch_title)
    await m.answer("عنوان جدید فصل:", reply_markup=back_kb())


@dp.message(S.edit_ch_title)
async def edit_ch_title(m,state):
    z=await state.get_data(); title=(m.text or "").strip()
    if not title:return await m.answer("عنوان معتبر نیست.")
    x=await db();await x.execute("UPDATE chapters SET title=? WHERE id=?",(title,z["chapter_edit_id"]));await x.commit();await x.close()
    await state.set_state(S.edit_ch_desc);await m.answer("توضیحات جدید را بفرستید یا «رد کردن».",reply_markup=markup([[kb(BUTTON_SKIP,"primary")],[kb(BUTTON_BACK,"danger")]]))


@dp.message(S.edit_ch_desc)
async def edit_ch_desc(m,state):
    z=await state.get_data(); d="" if m.text==BUTTON_SKIP else (m.text or "")
    x=await db();await x.execute("UPDATE chapters SET description=? WHERE id=?",(d,z["chapter_edit_id"]));await x.commit();await x.close();await state.clear()
    await m.answer("✅ فصل ویرایش شد.",reply_markup=chapter_menu())


@dp.message(F.text == "🗑 حذف فصل")
async def delete_ch_start(m,state):
    if not await is_admin(m.from_user.id): return
    rows=await chapter_rows();await state.set_state(S.delete_ch_select);await state.update_data(screen="chapter_delete")
    await m.answer("فصل را انتخاب کنید:",reply_markup=markup([[kb(f"🗑 #{r['id']} | {r['title']}","danger")] for r in rows]+[[kb(BUTTON_BACK,"danger")]]))


@dp.message(F.text == "🗑 حذف همین فصل")
async def delete_same_ch(m,state):
    cid=(await state.get_data()).get("selected_chapter")
    if not cid:return await delete_ch_start(m,state)
    await state.update_data(delete_ch_id=cid);await state.set_state(S.delete_ch_confirm)
    await m.answer("آیا از حذف این فصل مطمئن هستید؟ درس‌ها به «بدون فصل» منتقل می‌شوند.",
                    reply_markup=markup([[kb(BUTTON_YES,"danger"),kb(BUTTON_NO,"primary")],[kb(BUTTON_BACK,"danger")]]))


@dp.message(S.delete_ch_select)
async def delete_ch_select(m,state):
    cid=parse_id(m.text)
    if not cid:return await m.answer("فصل را از کیبورد انتخاب کنید.")
    await state.update_data(delete_ch_id=cid);await state.set_state(S.delete_ch_confirm)
    await m.answer("آیا از حذف این فصل مطمئن هستید؟",reply_markup=markup([[kb(BUTTON_YES,"danger"),kb(BUTTON_NO,"primary")],[kb(BUTTON_BACK,"danger")]]))


@dp.message(S.delete_ch_confirm)
async def delete_ch_confirm(m,state):
    if m.text==BUTTON_NO:return await state.clear() or await m.answer("لغو شد.",reply_markup=chapter_menu())
    if m.text!=BUTTON_YES:return
    cid=(await state.get_data()).get("delete_ch_id");x=await db();await x.execute("DELETE FROM chapters WHERE id=?",(cid,));await x.commit();await x.close();await state.clear()
    await m.answer("✅ فصل حذف شد.",reply_markup=chapter_menu())


@dp.message(F.text == "↕️ تغییر ترتیب فصل‌ها")
async def reorder_ch_start(m,state):
    rows=await chapter_rows()
    if not rows:return await m.answer("فصلی وجود ندارد.",reply_markup=chapter_menu())
    await state.set_state(S.reorder_ch_select);await state.update_data(screen="chapter_reorder")
    await m.answer("فصل را انتخاب کنید:",reply_markup=markup([[kb(f"↕️ #{r['id']} | {r['title']}","primary")] for r in rows]+[[kb(BUTTON_BACK,"danger")]]))


@dp.message(S.reorder_ch_select)
async def reorder_ch_select(m,state):
    cid=parse_id(m.text)
    if not cid:return await m.answer("فصل را از کیبورد انتخاب کنید.")
    await state.update_data(reorder_id=cid);await state.set_state(S.reorder_ch_target)
    await m.answer("شماره جایگاه جدید را وارد کنید (۱، ۲، ...):",reply_markup=back_kb())


@dp.message(S.reorder_ch_target)
async def reorder_ch_target(m,state):
    try:new=int(m.text)
    except:return await m.answer("شماره معتبر وارد کنید.")
    z=await state.get_data()
    if z.get("reorder_question_id"):
        qid=z["reorder_quiz"];selected=z["reorder_question_id"]
        x=await db();c=await x.execute("SELECT id FROM questions WHERE quiz_id=? ORDER BY position,id",(qid,));rows=await c.fetchall()
        ids=[r["id"] for r in rows if r["id"]!=selected];new=max(1,min(new,len(ids)+1));ids.insert(new-1,selected)
        for i,item in enumerate(ids,1):await x.execute("UPDATE questions SET position=? WHERE id=?",(i,item))
        await x.commit();await x.close();await state.clear();return await m.answer("✅ ترتیب سؤال‌ها تغییر کرد.",reply_markup=quiz_menu())
    rows=await chapter_rows();ids=[r["id"] for r in rows if r["id"]!=z["reorder_id"]];new=max(1,min(new,len(ids)+1));ids.insert(new-1,z["reorder_id"])
    x=await db()
    for i,cid in enumerate(ids,1):await x.execute("UPDATE chapters SET position=? WHERE id=?",(i,cid))
    await x.commit();await x.close();await state.clear();await m.answer("✅ ترتیب فصل‌ها تغییر کرد.",reply_markup=chapter_menu())


# ---------------- Lesson management ----------------

def lesson_menu():
    return markup([
        [kb("➕ افزودن درس","success"),kb("📋 لیست درس‌ها","primary")],
        [kb("✏️ ویرایش درس","primary"),kb("🗑 حذف درس","danger")],
        [kb("📢 انتشار/لغو انتشار","success")],[kb(BUTTON_BACK,"danger")]
    ])


async def lesson_rows():
    x=await db();c=await x.execute("SELECT l.*,c.title ct FROM lessons l LEFT JOIN chapters c ON c.id=l.chapter_id ORDER BY COALESCE(c.position,999999),l.position,l.id");r=await c.fetchall();await x.close();return r


async def chapter_select_kb():
    rows=await chapter_rows()
    return markup([[kb(f"📚 {r['title']}","success")] for r in rows]+[[kb("بدون فصل","primary")],[kb(BUTTON_BACK,"danger")]])


@dp.message(F.text=="🎬 مدیریت درس‌ها")
async def lesson_menu_handler(m,state):
    if await is_admin(m.from_user.id):
        await state.clear();await state.update_data(screen="lesson_menu");await m.answer("🎬 مدیریت درس‌ها",reply_markup=lesson_menu())


@dp.message(F.text=="➕ افزودن درس")
async def add_lesson(m,state):
    if not await is_admin(m.from_user.id):return
    await state.set_state(S.add_l_title);await state.update_data(screen="lesson_add")
    await m.answer("عنوان درس را ارسال کنید:",reply_markup=back_kb())


@dp.message(S.add_l_title)
async def add_lesson_title(m,state):
    title=(m.text or "").strip()
    if not title:return await m.answer("عنوان معتبر ارسال کنید.")
    x=await db();c=await x.execute("SELECT id FROM lessons WHERE title=? LIMIT 1",(title,));dup=await c.fetchone();await x.close()
    await state.update_data(title=title)
    if dup:
        await state.set_state(S.add_l_dup);return await m.answer("⚠️ درسی با این عنوان وجود دارد. آیا می‌خواهید با همین عنوان ادامه دهید؟",
            reply_markup=markup([[kb("بله، ادامه بده","success"),kb("عنوان جدید","danger")],[kb(BUTTON_BACK,"danger")]]))
    await state.set_state(S.add_l_chapter);await m.answer("فصل را انتخاب کنید:",reply_markup=await chapter_select_kb())


@dp.message(S.add_l_dup)
async def add_lesson_dup(m,state):
    if m.text=="عنوان جدید":await state.set_state(S.add_l_title);return await m.answer("عنوان جدید را ارسال کنید:")
    if m.text!="بله، ادامه بده":return
    await state.set_state(S.add_l_chapter);await m.answer("فصل را انتخاب کنید:",reply_markup=await chapter_select_kb())


@dp.message(S.add_l_chapter)
async def add_lesson_chapter(m,state):
    if m.text=="بدون فصل":cid=None
    else:
        x=await db();c=await x.execute("SELECT id FROM chapters WHERE title=? LIMIT 1",(m.text.replace("📚 ","",1),));r=await c.fetchone();await x.close()
        if not r:return await m.answer("فصل را از کیبورد انتخاب کنید.",reply_markup=await chapter_select_kb())
        cid=r["id"]
    await state.update_data(chapter_id=cid);await state.set_state(S.add_l_desc)
    await m.answer("توضیحات درس را بفرستید یا «رد کردن» را بزنید.",reply_markup=markup([[kb(BUTTON_SKIP,"primary")],[kb(BUTTON_BACK,"danger")]]))


@dp.message(S.add_l_desc)
async def add_lesson_desc(m,state):
    await state.update_data(description="" if m.text==BUTTON_SKIP else (m.text or ""));await state.set_state(S.add_l_content)
    await m.answer("📎 محتوای اصلی درس را ارسال کنید: Video، Document، Photo، Audio، Voice، Animation، Video Note، Sticker یا Text.",
                    reply_markup=back_kb())


@dp.message(S.add_l_content)
async def add_lesson_content(m,state):
    kind,fid,text,dur=extract_content(m)
    if not kind:return await m.answer("این نوع محتوا قابل ذخیره نیست.")
    await state.update_data(content_type=kind,content_file_id=fid,content_text=text,auto_duration=dur,telegram_message_id=m.message_id)
    if kind=="video":
        await state.set_state(S.add_l_duration)
        return await m.answer(f"⏱ مدت ویدیو تشخیص داده شد: {dur} ثانیه.\nاگر صحیح است «تأیید مدت» را بزنید یا مدت را به ثانیه وارد کنید.",
                               reply_markup=markup([[kb("تأیید مدت","success")],[kb(BUTTON_BACK,"danger")]]))
    await persist_lesson(m,state,0)


async def persist_lesson(m,state,duration):
    z=await state.get_data();x=await db()
    if z.get("chapter_id") is None:c=await x.execute("SELECT COALESCE(MAX(position),0)+1 p FROM lessons WHERE chapter_id IS NULL")
    else:c=await x.execute("SELECT COALESCE(MAX(position),0)+1 p FROM lessons WHERE chapter_id=?",(z["chapter_id"],))
    pos=(await c.fetchone())["p"]
    await x.execute("""INSERT INTO lessons(chapter_id,title,description,position,content_type,content_file_id,content_text,telegram_message_id,duration)
                       VALUES(?,?,?,?,?,?,?,?,?)""",(z["chapter_id"],z["title"],z["description"],pos,z["content_type"],z["content_file_id"],z["content_text"],z["telegram_message_id"],duration))
    await x.commit();await x.close();await state.clear()
    await m.answer("✅ درس ایجاد شد. از «انتشار/لغو انتشار» می‌توانید آن را منتشر کنید.",reply_markup=lesson_menu())


def lesson_picker(rows,prefix):
    return markup([[kb(f"{prefix} #{r['id']} | {r['title']}","primary")] for r in rows]+[[kb(BUTTON_BACK,"danger")]])


@dp.message(F.text=="📋 لیست درس‌ها")
async def list_lessons(m,state):
    if not await is_admin(m.from_user.id):return
    rows=await lesson_rows()
    if not rows:return await m.answer("🎬 درسی وجود ندارد.",reply_markup=lesson_menu())
    await state.set_state(S.lesson_select);await state.update_data(screen="lesson_list")
    await m.answer("درس را انتخاب کنید:",reply_markup=lesson_picker(rows,"🎬"))


@dp.message(S.lesson_select)
async def select_lesson(m,state):
    lid=parse_id(m.text)
    if not lid:return await m.answer("درس را از کیبورد انتخاب کنید.")
    await show_lesson(m,state,lid)


@dp.message(F.text.regexp(r"^🎬 #\d+ \|"))
async def lesson_detail_button(m,state):
    if await is_admin(m.from_user.id):
        await show_lesson(m,state,parse_id(m.text))


async def show_lesson(m,state,lid):
    x=await db();c=await x.execute("SELECT l.*,c.title ct FROM lessons l LEFT JOIN chapters c ON c.id=l.chapter_id WHERE l.id=?",(lid,));r=await c.fetchone()
    c=await x.execute("SELECT COUNT(*) n FROM questions q JOIN quizzes qz ON qz.id=q.quiz_id WHERE qz.lesson_id=?",(lid,));qn=(await c.fetchone())["n"]
    c=await x.execute("SELECT id FROM quizzes WHERE lesson_id=?",(lid,));quiz=await c.fetchone();await x.close()
    if not r:return await m.answer("❌ درس پیدا نشد.")
    await state.clear();await state.update_data(selected_lesson=lid,screen="lesson_info")
    text=f"""🎬 <b>{html.escape(r['title'])}</b>
📚 فصل: {html.escape(r['ct'] or 'بدون فصل')}
📝 توضیحات: {html.escape(r['description'] or '—')}
📎 نوع محتوا: {r['content_type']}
🆔 Message ID: {r['telegram_message_id']}
⏱ مدت Video: {r['duration'] if r['content_type']=='video' else '—'}
📣 وضعیت انتشار: {'منتشر شده' if r['published'] else 'پیش‌نویس'}
❓ سؤال‌های آزمون: {qn}
🕐 تاریخ ایجاد: {r['created_at']}"""
    rows=[[kb("✏️ ویرایش","primary"),kb("🗑 حذف","danger")],[kb("📝 مدیریت آزمون","success"),kb("📣 انتشار/لغو انتشار","primary")],[kb(BUTTON_BACK,"danger")]]
    await m.answer(text,parse_mode="HTML",reply_markup=markup(rows))


@dp.message(F.text=="📣 انتشار/لغو انتشار")
async def publish_lesson_start(m,state):
    if not await is_admin(m.from_user.id):return
    rows=await lesson_rows();await state.set_state(S.publish_l_select);await state.update_data(screen="lesson_publish")
    await m.answer("درس را انتخاب کنید:",reply_markup=lesson_picker(rows,"📣"))


@dp.message(S.publish_l_select)
async def publish_lesson_select(m,state):
    lid=parse_id(m.text)
    if not lid:return
    x=await db();await x.execute("UPDATE lessons SET published=CASE published WHEN 1 THEN 0 ELSE 1 END WHERE id=?",(lid,));await x.commit();await x.close();await state.clear()
    await m.answer("✅ وضعیت انتشار تغییر کرد.",reply_markup=lesson_menu())


@dp.message(F.text=="✏️ ویرایش درس")
async def edit_lesson_start(m,state):
    rows=await lesson_rows();await state.set_state(S.edit_l_select);await state.update_data(screen="lesson_edit")
    await m.answer("درس را انتخاب کنید:",reply_markup=lesson_picker(rows,"✏️"))


@dp.message(F.text=="✏️ ویرایش")
async def edit_lesson_same(m,state):
    lid=(await state.get_data()).get("selected_lesson")
    if lid:return await edit_lesson_fields(m,state,lid)
    await edit_lesson_start(m,state)


@dp.message(S.edit_l_select)
async def edit_l_select(m,state):
    lid=parse_id(m.text)
    if not lid:return await m.answer("درس را از کیبورد انتخاب کنید.")
    await edit_lesson_fields(m,state,lid)


async def edit_lesson_fields(m,state,lid):
    await state.update_data(edit_lesson_id=lid,screen="lesson_edit_fields")
    await state.set_state(S.edit_l_field)
    await m.answer("چه چیزی را ویرایش می‌کنید؟",reply_markup=markup([
        [kb("عنوان","primary"),kb("فصل","primary")],[kb("توضیحات","primary"),kb("محتوا","primary")],
        [kb("مدت Video","primary"),kb("آزمون","success")],[kb("وضعیت انتشار","primary")],[kb(BUTTON_BACK,"danger")]]))


@dp.message(S.edit_l_field)
async def edit_l_field(m,state):
    z=await state.get_data();lid=z["edit_lesson_id"]; choice=m.text
    if choice=="آزمون":return await open_quiz_for_lesson(m,state,lid)
    if choice=="وضعیت انتشار":
        x=await db();await x.execute("UPDATE lessons SET published=1-published WHERE id=?",(lid,));await x.commit();await x.close()
        return await m.answer("✅ وضعیت انتشار تغییر کرد.",reply_markup=lesson_menu())
    if choice=="فصل":
        await state.set_state(S.edit_l_chapter);await state.update_data(editing_lesson=lid)
        return await m.answer("فصل جدید را انتخاب کنید:",reply_markup=await chapter_select_kb())
    if choice=="محتوا":
        await state.set_state(S.edit_l_content);await state.update_data(editing_lesson=lid)
        return await m.answer("محتوای جدید را ارسال کنید:",reply_markup=back_kb())
    if choice=="مدت Video":
        await state.set_state(S.edit_l_value);await state.update_data(edit_field="duration")
        return await m.answer("مدت را به ثانیه وارد کنید:",reply_markup=back_kb())
    await state.set_state(S.edit_l_value);await state.update_data(edit_field={"عنوان":"title","توضیحات":"description"}.get(choice))
    await m.answer("مقدار جدید را ارسال کنید یا برای توضیحات «رد کردن».",reply_markup=back_kb(BUTTON_SKIP) if choice=="توضیحات" else back_kb())


@dp.message(S.edit_l_value)
async def edit_l_value(m,state):
    z=await state.get_data();field=z.get("edit_field")
    value="" if field=="description" and m.text==BUTTON_SKIP else (m.text or "")
    if field=="duration":
        try:value=int(value)
        except:return await m.answer("مدت را به ثانیه وارد کنید.")
    x=await db();await x.execute(f"UPDATE lessons SET {field}=? WHERE id=?",(value,z["edit_lesson_id"]));await x.commit();await x.close();await state.clear()
    await m.answer("✅ درس ویرایش شد.",reply_markup=lesson_menu())


@dp.message(F.text=="🗑 حذف درس")
async def delete_lesson_start(m,state):
    rows=await lesson_rows();await state.set_state(S.delete_l_select);await state.update_data(screen="lesson_delete")
    await m.answer("درس را انتخاب کنید:",reply_markup=lesson_picker(rows,"🗑"))


@dp.message(F.text=="🗑 حذف")
async def delete_same_lesson(m,state):
    lid=(await state.get_data()).get("selected_lesson")
    if not lid:return await delete_lesson_start(m,state)
    await state.update_data(delete_lesson_id=lid);await state.set_state(S.delete_l_confirm)
    await m.answer("⚠️ آیا از حذف این درس مطمئن هستید؟",reply_markup=markup([[kb(BUTTON_YES,"danger"),kb(BUTTON_NO,"primary")],[kb(BUTTON_BACK,"danger")]]))


@dp.message(S.delete_l_select)
async def delete_l_select(m,state):
    lid=parse_id(m.text)
    if not lid:return await m.answer("درس را از کیبورد انتخاب کنید.")
    await state.update_data(delete_lesson_id=lid);await state.set_state(S.delete_l_confirm)
    await m.answer("⚠️ آیا از حذف این درس مطمئن هستید؟",reply_markup=markup([[kb(BUTTON_YES,"danger"),kb(BUTTON_NO,"primary")],[kb(BUTTON_BACK,"danger")]]))


@dp.message(S.delete_l_confirm)
async def delete_l_confirm(m,state):
    if m.text==BUTTON_NO:await state.clear();return await m.answer("لغو شد.",reply_markup=lesson_menu())
    if m.text!=BUTTON_YES:return
    lid=(await state.get_data()).get("delete_lesson_id");x=await db();await x.execute("DELETE FROM lessons WHERE id=?",(lid,));await x.commit();await x.close();await state.clear()
    await m.answer("🗑 درس حذف شد.",reply_markup=lesson_menu())


@dp.message(S.edit_l_chapter)
async def edit_lesson_chapter(m,state):
    lid=(await state.get_data()).get("editing_lesson")
    if m.text=="بدون فصل": cid=None
    else:
        x=await db();c=await x.execute("SELECT id FROM chapters WHERE title=? LIMIT 1",(m.text.replace("📚 ","",1),));r=await c.fetchone();await x.close()
        if not r:return await m.answer("فصل را از کیبورد انتخاب کنید.")
        cid=r["id"]
    x=await db();await x.execute("UPDATE lessons SET chapter_id=? WHERE id=?",(cid,lid));await x.commit();await x.close();await state.clear()
    await m.answer("✅ فصل درس تغییر کرد.",reply_markup=lesson_menu())


@dp.message(S.edit_l_content)
async def edit_lesson_content(m,state):
    lid=(await state.get_data()).get("editing_lesson")
    kind,fid,text,dur=extract_content(m)
    if not kind:return await m.answer("محتوای قابل ذخیره ارسال کنید.")
    if kind=="video":
        await state.update_data(edit_duration=dur,edit_kind=kind,edit_fid=fid,edit_text=text,edit_msg=m.message_id)
        await state.set_state(S.add_l_duration)
        return await m.answer(f"مدت ویدیو: {dur} ثانیه. «تأیید مدت» یا مقدار جدید را بفرستید.")
    x=await db();await x.execute("""UPDATE lessons SET content_type=?,content_file_id=?,content_text=?,telegram_message_id=?,duration=0 WHERE id=?""",
                                  (kind,fid,text,m.message_id,lid));await x.commit();await x.close();await state.clear()
    await m.answer("✅ محتوای درس به‌روزرسانی شد.",reply_markup=lesson_menu())


# When duration state is used by content editing, update instead of creating a new lesson.
@dp.message(S.add_l_duration)
async def add_lesson_duration_final(m,state):
    z=await state.get_data()
    if z.get("editing_lesson"):
        if m.text=="تأیید مدت":dur=int(z.get("edit_duration") or 0)
        else:
            try:dur=int(m.text)
            except:return await m.answer("مدت را به ثانیه وارد کنید.")
        x=await db();await x.execute("""UPDATE lessons SET content_type=?,content_file_id=?,content_text=?,telegram_message_id=?,duration=? WHERE id=?""",
                                      (z["edit_kind"],z["edit_fid"],z["edit_text"],z["edit_msg"],dur,z["editing_lesson"]))
        await x.commit();await x.close();await state.clear();return await m.answer("✅ محتوای درس به‌روزرسانی شد.",reply_markup=lesson_menu())
    # original creation path
    if m.text=="تأیید مدت":dur=int(z.get("auto_duration") or 0)
    else:
        try:dur=int(m.text)
        except:return await m.answer("مدت را به ثانیه وارد کنید.")
    await persist_lesson(m,state,dur)




@dp.message(F.text=="📝 مدیریت آزمون")
async def lesson_quiz_manage_button(m,state):
    lid=(await state.get_data()).get("selected_lesson")
    if not lid:
        return await m.answer("ابتدا یک درس را انتخاب کنید.")
    await open_quiz_for_lesson(m,state,lid)


@dp.message(F.text=="✏️ تنظیم آزمون")
async def quiz_settings_start(m,state):
    qid=(await state.get_data()).get("selected_quiz")
    if not qid:
        rows=await quiz_rows()
        if not rows:return await m.answer("آزمونی وجود ندارد.",reply_markup=quiz_menu())
        await state.set_state(S.quiz_lesson_select)
        return await m.answer("آزمون را انتخاب کنید:",reply_markup=markup([[kb(f"📝 #{r['id']} | {r['lt']}","primary")] for r in rows]+[[kb(BUTTON_BACK,"danger")]]))
    await state.set_state(S.quiz_time);await state.update_data(edit_quiz_id=qid)
    await m.answer("زمان کل آزمون جدید را به ثانیه وارد کنید:",reply_markup=back_kb())


@dp.message(F.text=="🗑 حذف آزمون")
async def quiz_delete_start(m,state):
    rows=await quiz_rows()
    if not rows:return await m.answer("آزمونی وجود ندارد.",reply_markup=quiz_menu())
    await state.set_state(S.quiz_delete_select);await state.update_data(screen="quiz_delete")
    await m.answer("آزمون را انتخاب کنید:",reply_markup=markup([[kb(f"🗑 #{r['id']} | {r['lt']}","danger")] for r in rows]+[[kb(BUTTON_BACK,"danger")]]))


@dp.message(S.quiz_delete_select)
async def quiz_delete_confirm(m,state):
    qid=parse_id(m.text)
    if not qid:return
    await state.update_data(delete_quiz_id=qid);await state.set_state(S.quiz_delete_confirm)
    await m.answer("⚠️ حذف این آزمون و همه سؤال‌هایش تأیید شود؟",reply_markup=markup([[kb(BUTTON_YES,"danger"),kb(BUTTON_NO,"primary")],[kb(BUTTON_BACK,"danger")]]))


@dp.message(S.quiz_delete_confirm,F.text.in_({BUTTON_YES,BUTTON_NO}))
async def quiz_delete_confirm_action(m,state):
    if m.text==BUTTON_NO:
        await state.clear();return await m.answer("لغو شد.",reply_markup=quiz_menu())
    qid=(await state.get_data()).get("delete_quiz_id")
    x=await db();await x.execute("DELETE FROM quizzes WHERE id=?",(qid,));await x.commit();await x.close();await state.clear()
    await m.answer("🗑 آزمون حذف شد.",reply_markup=quiz_menu())


@dp.message(F.text=="↕️ ترتیب سؤال‌ها")
async def reorder_questions_start(m,state):
    qid=(await state.get_data()).get("selected_quiz")
    if not qid:return await m.answer("ابتدا آزمون را انتخاب کنید.")
    x=await db();c=await x.execute("SELECT * FROM questions WHERE quiz_id=? ORDER BY position,id",(qid,));rows=await c.fetchall();await x.close()
    if not rows:return await m.answer("سؤالی وجود ندارد.")
    await state.set_state(S.question_select);await state.update_data(reorder_quiz=qid,reorder_mode=True)
    await m.answer("سؤال را انتخاب کنید:",reply_markup=markup([[kb(f"↕️ #{r['id']} | {r['text'][:40]}","primary")] for r in rows]+[[kb(BUTTON_BACK,"danger")]]))


# ---------------- Quiz management ----------------

def quiz_menu():
    return markup([
        [kb("➕ ساخت آزمون","success"),kb("📋 لیست آزمون‌ها","primary")],
        [kb("➕ افزودن سؤال","primary"),kb("✏️ ویرایش سؤال","primary")],
        [kb("🗑 حذف سؤال","danger"),kb("🗑 حذف آزمون","danger")],
        [kb(BUTTON_BACK,"danger")]
    ])


async def quiz_rows():
    x=await db();c=await x.execute("SELECT q.*,l.title lt FROM quizzes q JOIN lessons l ON l.id=q.lesson_id ORDER BY q.id DESC");r=await c.fetchall();await x.close();return r


async def open_quiz_for_lesson(m,state,lid):
    x=await db();c=await x.execute("SELECT * FROM quizzes WHERE lesson_id=?",(lid,));q=await c.fetchone();await x.close()
    if not q:
        await state.set_state(S.quiz_pass);await state.update_data(quiz_lesson=lid,screen="quiz_create")
        return await m.answer("درصد قبولی را وارد کنید (مثلاً 70):",reply_markup=back_kb())
    await state.clear();await state.update_data(selected_quiz=q["id"],screen="quiz_info")
    await m.answer(f"📝 آزمون درس\nقبولی: {q['pass_percent']}٪\nTimer کل: {q['time_limit']} ثانیه\nRetry: {q['retry_mode']}",
                   reply_markup=markup([[kb("➕ افزودن سؤال","success"),kb("📋 سؤال‌ها","primary")],[kb("✏️ تنظیم آزمون","primary"),kb("🗑 حذف آزمون","danger")],[kb("↕️ ترتیب سؤال‌ها","primary")],[kb(BUTTON_BACK,"danger")]]))


@dp.message(F.text=="📝 مدیریت آزمون‌ها")
async def quiz_menu_handler(m,state):
    if await is_admin(m.from_user.id):await state.clear();await state.update_data(screen="quiz_menu");await m.answer("📝 مدیریت آزمون‌ها",reply_markup=quiz_menu())


@dp.message(F.text=="➕ ساخت آزمون")
async def quiz_create_start(m,state):
    rows=await lesson_rows();await state.set_state(S.quiz_lesson_select);await state.update_data(screen="quiz_create")
    await m.answer("درس را انتخاب کنید:",reply_markup=lesson_picker(rows,"📝"))


@dp.message(S.quiz_lesson_select)
async def quiz_lesson_select(m,state):
    lid=parse_id(m.text)
    if not lid:return
    await state.update_data(quiz_lesson=lid);await state.set_state(S.quiz_pass);await m.answer("درصد قبولی را وارد کنید:")


@dp.message(S.quiz_pass)
async def quiz_pass(m,state):
    try:p=max(1,min(100,int(m.text)))
    except:return await m.answer("یک عدد بین 1 تا 100 وارد کنید.")
    await state.update_data(pass_percent=p);await state.set_state(S.quiz_time);await m.answer("زمان کل آزمون را به ثانیه وارد کنید:")


@dp.message(S.quiz_time)
async def quiz_time(m,state):
    try:t=max(1,int(m.text))
    except:return await m.answer("زمان را به ثانیه وارد کنید.")
    await state.update_data(time_limit=t);await state.set_state(S.quiz_retry)
    await m.answer("منطق تلاش مجدد را انتخاب کنید:",reply_markup=markup([[kb("تلاش مجدد","success"),kb("یک‌بار فقط","danger")],[kb(BUTTON_BACK,"danger")]]))


@dp.message(S.quiz_retry)
async def quiz_retry(m,state):
    if m.text not in ("تلاش مجدد","یک‌بار فقط"):return
    z=await state.get_data();x=await db()
    await x.execute("""INSERT INTO quizzes(lesson_id,pass_percent,time_limit,retry_mode)
                       VALUES(?,?,?,?) ON CONFLICT(lesson_id) DO UPDATE SET pass_percent=excluded.pass_percent,time_limit=excluded.time_limit,retry_mode=excluded.retry_mode""",
                    (z["quiz_lesson"],z["pass_percent"],z["time_limit"],"retry" if m.text=="تلاش مجدد" else "once"))
    await x.commit();await x.close();await state.clear();await m.answer("✅ آزمون ذخیره شد.",reply_markup=quiz_menu())


@dp.message(F.text=="📋 لیست آزمون‌ها")
async def list_quizzes(m):
    rows=await quiz_rows()
    if not rows:return await m.answer("آزمونی وجود ندارد.",reply_markup=quiz_menu())
    await m.answer("📝 آزمون‌ها:",reply_markup=markup([[kb(f"📝 #{r['id']} | {r['lt']}","primary")] for r in rows]+[[kb(BUTTON_BACK,"danger")]]))


@dp.message(F.text=="➕ افزودن سؤال")
async def add_question_start(m,state):
    rows=await quiz_rows();await state.set_state(S.question_quiz_select);await state.update_data(screen="quiz_question_add")
    await m.answer("آزمون را انتخاب کنید:",reply_markup=markup([[kb(f"📝 #{r['id']} | {r['lt']}","primary")] for r in rows]+[[kb(BUTTON_BACK,"danger")]]))


@dp.message(S.question_quiz_select)
async def question_quiz_select(m,state):
    qid=parse_id(m.text)
    if not qid:return
    await state.update_data(question_quiz=qid);await state.set_state(S.question_text);await m.answer("متن سؤال را ارسال کنید:",reply_markup=back_kb())


@dp.message(S.question_text)
async def question_text(m,state):
    await state.update_data(question_text=m.text or "");await state.set_state(S.question_options)
    await m.answer("گزینه‌ها را هرکدام در یک خط بفرستید (حداقل 2 گزینه):",reply_markup=back_kb())


@dp.message(S.question_options)
async def question_options(m,state):
    opts=[x.strip() for x in (m.text or "").splitlines() if x.strip()]
    if len(opts)<2:return await m.answer("حداقل 2 گزینه لازم است.")
    await state.update_data(options=opts);await state.set_state(S.question_correct)
    await m.answer("شماره گزینه صحیح را بفرستید:",reply_markup=back_kb())


@dp.message(S.question_correct)
async def question_correct(m,state):
    z=await state.get_data()
    try:correct=int(m.text)-1
    except:return await m.answer("شماره گزینه صحیح را وارد کنید.")
    if correct<0 or correct>=len(z["options"]):return await m.answer("شماره گزینه نامعتبر است.")
    await state.update_data(correct=correct);await state.set_state(S.question_timer)
    await m.answer("Timer این سؤال به ثانیه؟",reply_markup=back_kb())


@dp.message(S.question_timer)
async def question_timer(m,state):
    try:timer=max(1,int(m.text))
    except:return await m.answer("Timer معتبر وارد کنید.")
    z=await state.get_data();x=await db()
    c=await x.execute("SELECT COALESCE(MAX(position),0)+1 p FROM questions WHERE quiz_id=?",(z["question_quiz"],));pos=(await c.fetchone())["p"]
    c=await x.execute("INSERT INTO questions(quiz_id,text,position,timer) VALUES(?,?,?,?)",(z["question_quiz"],z["question_text"],pos,timer));qid=c.lastrowid
    for i,o in enumerate(z["options"]):await x.execute("INSERT INTO options(question_id,text,is_correct) VALUES(?,?,?)",(qid,o,int(i==z["correct"])))
    await x.commit();await x.close();await state.clear();await m.answer("✅ سؤال اضافه شد.",reply_markup=quiz_menu())


@dp.message(F.text=="📋 سؤال‌ها")
async def question_list(m,state):
    qid=(await state.get_data()).get("selected_quiz")
    if not qid:return await m.answer("ابتدا آزمون را انتخاب کنید.")
    x=await db();c=await x.execute("SELECT * FROM questions WHERE quiz_id=? ORDER BY position,id",(qid,));rows=await c.fetchall();await x.close()
    await m.answer("📋 سؤال‌ها:",reply_markup=markup([[kb(f"❓ #{r['id']} | {r['text'][:40]}","primary")] for r in rows]+[[kb(BUTTON_BACK,"danger")]]))


@dp.message(F.text=="✏️ ویرایش سؤال")
async def edit_question_start(m,state):
    rows=await quiz_rows()
    if not rows:return await m.answer("آزمونی وجود ندارد.")
    # Choose quiz, then question.
    await state.set_state(S.edit_q_select);await state.update_data(screen="quiz_edit_question")
    await m.answer("شماره آزمون را انتخاب کنید:",reply_markup=markup([[kb(f"📝 #{r['id']} | {r['lt']}","primary")] for r in rows]+[[kb(BUTTON_BACK,"danger")]]))


@dp.message(S.edit_q_select)
async def edit_q_select(m,state):
    qid=parse_id(m.text)
    if not qid:return
    x=await db();c=await x.execute("SELECT * FROM questions WHERE quiz_id=? ORDER BY position,id",(qid,));rows=await c.fetchall();await x.close()
    if not rows:return await m.answer("این آزمون سؤال ندارد.")
    await state.update_data(edit_quiz=qid);await state.set_state(S.question_select)
    await m.answer("سؤال را انتخاب کنید:",reply_markup=markup([[kb(f"❓ #{r['id']} | {r['text'][:40]}","primary")] for r in rows]+[[kb(BUTTON_BACK,"danger")]]))


@dp.message(S.question_select)
async def question_select(m,state):
    qid=parse_id(m.text)
    if not qid:return
    z=await state.get_data()
    if z.get("reorder_mode"):
        await state.update_data(reorder_question_id=qid)
        await state.set_state(S.reorder_ch_target)
        return await m.answer("جایگاه جدید سؤال را وارد کنید (۱، ۲، ...):",reply_markup=back_kb())
    await state.update_data(edit_question_id=qid);await state.set_state(S.edit_q_text);await m.answer("متن جدید سؤال:",reply_markup=back_kb())


@dp.message(S.edit_q_text)
async def edit_q_text(m,state):
    z=await state.get_data();x=await db();await x.execute("UPDATE questions SET text=? WHERE id=?",(m.text or "",z["edit_question_id"]));await x.commit();await x.close();await state.clear();await m.answer("✅ سؤال ویرایش شد.",reply_markup=quiz_menu())


@dp.message(F.text=="🗑 حذف سؤال")
async def delete_question_start(m,state):
    rows=await quiz_rows();await state.set_state(S.delete_q_select);await state.update_data(screen="quiz_delete_question")
    await m.answer("آزمون را انتخاب کنید:",reply_markup=markup([[kb(f"📝 #{r['id']} | {r['lt']}","primary")] for r in rows]+[[kb(BUTTON_BACK,"danger")]]))


@dp.message(S.delete_q_select)
async def delete_q_select(m,state):
    qid=parse_id(m.text)
    if not qid:return
    x=await db();c=await x.execute("SELECT * FROM questions WHERE quiz_id=? ORDER BY position,id",(qid,));rows=await c.fetchall();await x.close()
    await state.update_data(delete_quiz=qid);await state.set_state(S.delete_question_select)
    await m.answer("سؤال را انتخاب کنید:",reply_markup=markup([[kb(f"🗑 #{r['id']} | {r['text'][:40]}","danger")] for r in rows]+[[kb(BUTTON_BACK,"danger")]]))


@dp.message(S.delete_question_select)
async def delete_question_select(m,state):
    qid=parse_id(m.text)
    if not qid:return
    await state.update_data(delete_question_id=qid);await state.set_state(S.delete_q_confirm)
    await m.answer("⚠️ آیا از حذف این سؤال مطمئن هستید؟",reply_markup=markup([[kb(BUTTON_YES,"danger"),kb(BUTTON_NO,"primary")],[kb(BUTTON_BACK,"danger")]]))


@dp.message(S.delete_q_confirm,F.text.in_({BUTTON_YES,BUTTON_NO}))
async def delete_question_confirm(m,state):
    if m.text==BUTTON_NO:
        await state.clear();return await m.answer("لغو شد.",reply_markup=quiz_menu())
    z=await state.get_data();x=await db();await x.execute("DELETE FROM questions WHERE id=?",(z["delete_question_id"],));await x.commit();await x.close();await state.clear()
    await m.answer("🗑 سؤال حذف شد.",reply_markup=quiz_menu())




# ---------------- Users ----------------

@dp.message(F.text=="👥 کاربران")
async def users_menu(m,state):
    if not await is_admin(m.from_user.id):return
    x=await db();c=await x.execute("SELECT COUNT(*) n FROM users");n=(await c.fetchone())["n"];await x.close()
    await state.set_state(S.user_search);await state.update_data(screen="users")
    await m.answer(f"👥 کل کاربران: {n}\nجستجو با Username، نام یا Telegram ID:",reply_markup=back_kb("📋 آخرین کاربران"))


@dp.message(S.user_search)
async def user_search(m,state):
    if m.text=="📋 آخرین کاربران":
        term=""
    else:term=(m.text or "").strip()
    x=await db()
    if term:
        like=f"%{term.lstrip('@')}%"
        c=await x.execute("""SELECT * FROM users WHERE CAST(telegram_id AS TEXT) LIKE ? OR username LIKE ? OR first_name LIKE ?
                             ORDER BY id DESC LIMIT 30""",(like,like,like))
    else:c=await x.execute("SELECT * FROM users ORDER BY id DESC LIMIT 30")
    rows=await c.fetchall();await x.close()
    if not rows:return await m.answer("کاربری پیدا نشد.")
    await state.set_state(S.user_select)
    await m.answer("کاربر را انتخاب کنید:",reply_markup=markup([[kb(f"👤 #{r['id']} | {r['first_name'] or '-'} | @{r['username'] or '-'}","primary")] for r in rows]+[[kb(BUTTON_BACK,"danger")]]))


@dp.message(S.user_select)
async def user_select(m,state):
    uid=parse_id(m.text)
    if not uid:return
    await show_user(m,state,uid)


async def show_user(m,state,uid):
    x=await db();c=await x.execute("SELECT * FROM users WHERE id=?",(uid,));u=await c.fetchone()
    if not u:return await x.close() or await m.answer("کاربر پیدا نشد.")
    c=await x.execute("SELECT COUNT(*) n FROM progress WHERE user_id=? AND (video_done=1 OR quiz_passed=1)",(uid,));done=(await c.fetchone())["n"]
    c=await x.execute("SELECT AVG(score) a FROM attempts WHERE user_id=?",(uid,));avg=(await c.fetchone())["a"]
    await x.close()
    await state.clear();await state.update_data(selected_user=uid,screen="user_profile")
    await m.answer(f"""👤 <b>{html.escape(u['first_name'] or '-')}</b>
Username: @{html.escape(u['username'] or '-')}
Telegram ID: <code>{u['telegram_id']}</code>
📈 تکمیل: {done}
🏆 میانگین نمره: {round(avg or 0,1)}
🚫 Block: {'بله' if u['blocked'] else 'خیر'}
🔐 دسترسی دوره: {'دارد' if u['course_access'] else 'ندارد'}
🕐 آخرین فعالیت: {u['last_activity']}""",parse_mode="HTML",
                   reply_markup=markup([[kb("📈 Progress","primary"),kb("📚 درس‌های تکمیل‌شده","primary")],
                                        [kb("🔄 Reset Progress","danger"),kb("🚫 Block/Unblock","danger")],
                                        [kb("🔐 دسترسی دوره","primary"),kb("📨 ارسال پیام","success")],
                                        [kb(BUTTON_BACK,"danger")]]))


@dp.message(F.text=="📈 Progress")
async def user_progress(m,state):
    uid=(await state.get_data()).get("selected_user")
    if not uid:return
    x=await db();c=await x.execute("""SELECT l.title,COALESCE(p.video_done,0) video_done,COALESCE(p.quiz_passed,0) quiz_passed
                                       FROM lessons l LEFT JOIN progress p ON p.lesson_id=l.id AND p.user_id=?
                                       ORDER BY l.id""",(uid,));rows=await c.fetchall();await x.close()
    await m.answer("\n".join(f"{'✅' if r['video_done'] and (r['quiz_passed'] or True) else '🔒'} {r['title']} | آزمون: {'قبول' if r['quiz_passed'] else '—'}" for r in rows) or "Progress خالی است.")


@dp.message(F.text=="📚 درس‌های تکمیل‌شده")
async def user_completed(m,state):
    uid=(await state.get_data()).get("selected_user")
    if not uid:return
    x=await db();c=await x.execute("""SELECT l.title,p.completed_at FROM progress p JOIN lessons l ON l.id=p.lesson_id
                                       WHERE p.user_id=? AND (p.video_done=1 OR p.quiz_passed=1) ORDER BY p.completed_at DESC""",(uid,));rows=await c.fetchall();await x.close()
    await m.answer("\n".join(f"✅ {r['title']} — {r['completed_at'] or '—'}" for r in rows) or "هنوز درسی تکمیل نشده.")


@dp.message(F.text=="🔄 Reset Progress")
async def reset_progress(m,state):
    uid=(await state.get_data()).get("selected_user")
    if not uid:return
    x=await db();await x.execute("DELETE FROM progress WHERE user_id=?",(uid,));await x.execute("DELETE FROM attempts WHERE user_id=?",(uid,));await x.commit();await x.close();await m.answer("✅ Progress کاربر Reset شد.")


@dp.message(F.text=="🚫 Block/Unblock")
async def toggle_block(m,state):
    uid=(await state.get_data()).get("selected_user")
    if not uid:return
    x=await db();await x.execute("UPDATE users SET blocked=1-blocked WHERE id=?",(uid,));await x.commit();await x.close();await m.answer("✅ وضعیت Block تغییر کرد.")


@dp.message(F.text=="🔐 دسترسی دوره")
async def toggle_access(m,state):
    uid=(await state.get_data()).get("selected_user")
    if not uid:return
    x=await db();await x.execute("UPDATE users SET course_access=1-course_access WHERE id=?",(uid,));await x.commit();await x.close();await m.answer("✅ دسترسی دوره تغییر کرد.")


@dp.message(F.text=="📨 ارسال پیام")
async def user_message_start(m,state):
    uid=(await state.get_data()).get("selected_user")
    if not uid:return
    x=await db();c=await x.execute("SELECT telegram_id FROM users WHERE id=?",(uid,));u=await c.fetchone();await x.close()
    await state.set_state(S.user_message);await state.update_data(user_tid=u["telegram_id"])
    await m.answer("پیام خود را ارسال کنید؛ متن یا Media قابل ارسال.",reply_markup=back_kb())


@dp.message(S.user_message)
async def user_message_send(m,state):
    z=await state.get_data()
    try:await m.bot.copy_message(z["user_tid"],m.chat.id,m.message_id)
    except Exception as e:return await m.answer(f"❌ ارسال نشد: {html.escape(str(e))}",parse_mode="HTML")
    await state.clear();await m.answer("✅ پیام ارسال شد.",reply_markup=admin_kb())


# ---------------- Support ----------------

@dp.message(F.text==BUTTON_SUPPORT)
async def user_support(m,state):
    u=await ensure_user(m.from_user)
    x=await db();c=await x.execute("SELECT id FROM tickets WHERE user_id=? AND status='open' ORDER BY id DESC LIMIT 1",(u["id"],));t=await c.fetchone()
    if not t:
        c=await x.execute("INSERT INTO tickets(user_id) VALUES(?)",(u["id"],));tid=c.lastrowid;await x.commit()
    else:tid=t["id"]
    await x.close();await state.clear();await state.update_data(screen="support")
    await m.answer(f"💬 {await setting('support_text')}\n🎫 تیکت #{tid}\nپیامت را بفرست:",reply_markup=back_kb())


@dp.message(F.text=="💬 پیام‌های پشتیبانی")
async def support_admin(m,state):
    if not await is_admin(m.from_user.id):return
    x=await db();c=await x.execute("""SELECT t.id,u.first_name,COUNT(tm.id) n FROM tickets t JOIN users u ON u.id=t.user_id
                                       LEFT JOIN ticket_messages tm ON tm.ticket_id=t.id WHERE t.status='open' GROUP BY t.id ORDER BY t.id DESC""");rows=await c.fetchall();await x.close()
    if not rows:return await m.answer("🎫 تیکت بازی وجود ندارد.",reply_markup=admin_kb())
    await state.set_state(S.ticket_select);await state.update_data(screen="support_admin")
    await m.answer("تیکت را انتخاب کنید:",reply_markup=markup([[kb(f"🎫 #{r['id']} | {r['first_name'] or '-'} ({r['n']})","primary")] for r in rows]+[[kb(BUTTON_BACK,"danger")]]))


@dp.message(S.ticket_select)
async def ticket_select(m,state):
    tid=parse_id(m.text)
    if not tid:return
    x=await db();c=await x.execute("SELECT t.id,u.first_name,u.telegram_id FROM tickets t JOIN users u ON u.id=t.user_id WHERE t.id=?",(tid,));t=await c.fetchone()
    c=await x.execute("SELECT * FROM ticket_messages WHERE ticket_id=? ORDER BY id",(tid,));msgs=await c.fetchall();await x.close()
    body="\n".join(f"{'👤' if z['sender_id']==t['telegram_id'] else '🛡'} {z['created_at']} | {html.escape(z['text'] or '['+z['content_type']+']')}" for z in msgs) or "بدون پیام ذخیره‌شده."
    await state.update_data(ticket_id=tid,ticket_user_tid=t["telegram_id"]);await state.set_state(S.ticket_reply)
    await m.answer(f"🎫 <b>#{tid}</b> — {html.escape(t['first_name'] or '-')}\n\n{body}",
                   parse_mode="HTML",reply_markup=markup([[kb("📨 پاسخ","success"),kb("🔒 بستن","danger")],[kb(BUTTON_BACK,"danger")]]))


@dp.message(F.text=="📨 پاسخ",S.ticket_reply)
async def ticket_reply_prompt(m,state):
    await m.answer("پاسخ را ارسال کنید:",reply_markup=back_kb())


@dp.message(S.ticket_reply)
async def ticket_reply_send(m,state):
    z=await state.get_data()
    if not z.get("ticket_id"):return
    # If the admin sends the action button, don't store it as a ticket message.
    if m.text in ("🔒 بستن","📨 پاسخ"):return
    try:await m.bot.copy_message(z["ticket_user_tid"],m.chat.id,m.message_id)
    except Exception as e:return await m.answer(f"❌ ارسال نشد: {html.escape(str(e))}",parse_mode="HTML")
    kind,_,text,_=extract_content(m);x=await db()
    await x.execute("INSERT INTO ticket_messages(ticket_id,sender_id,text,content_type,telegram_message_id) VALUES(?,?,?,?,?)",
                    (z["ticket_id"],m.from_user.id,text or "",kind or "unknown",m.message_id))
    await x.commit();await x.close();await state.clear();await m.answer("✅ پاسخ ارسال شد.",reply_markup=admin_kb())


@dp.message(F.text=="🔒 بستن",S.ticket_reply)
async def ticket_close(m,state):
    z=await state.get_data();x=await db();await x.execute("UPDATE tickets SET status='closed',closed_at=? WHERE id=?",(datetime.now(timezone.utc).isoformat(),z["ticket_id"]));await x.commit();await x.close();await state.clear();await m.answer("🔒 تیکت بسته شد.",reply_markup=admin_kb())


# Catch only non-command user messages; this is intentionally not a global business-command catch-all.
@dp.message()
async def user_ticket_message(m,state):
    if await is_admin(m.from_user.id) or m.text in (BUTTON_START,BUTTON_SUPPORT,BUTTON_ADMIN,BUTTON_BACK):
        return
    u=await ensure_user(m.from_user)
    x=await db();c=await x.execute("SELECT id FROM tickets WHERE user_id=? AND status='open' ORDER BY id DESC LIMIT 1",(u["id"],));t=await c.fetchone()
    if not t:await x.close();return
    kind,_,text,_=extract_content(m)
    await x.execute("INSERT INTO ticket_messages(ticket_id,sender_id,text,content_type,telegram_message_id) VALUES(?,?,?,?,?)",
                    (t["id"],m.from_user.id,text or "",kind or "unknown",m.message_id));await x.commit();await x.close()
    try:
        await m.bot.send_message(OWNER_ID,f"💬 تیکت #{t['id']}\n👤 {html.escape(m.from_user.full_name)}\n\nپیام جدید دریافت شد.",parse_mode="HTML")
    except Exception:pass
    await m.answer("✅ پیام شما برای پشتیبانی ثبت شد.",reply_markup=user_kb(False))


# ---------------- Admins ----------------

@dp.message(F.text=="👑 ادمین‌ها")
async def admins_menu(m,state):
    if not await is_admin(m.from_user.id):return
    x=await db();c=await x.execute("SELECT telegram_id,role FROM admins ORDER BY telegram_id");rows=await c.fetchall();await x.close()
    body="👑 <b>ادمین‌ها</b>\n\nOwner اصلی: <code>%s</code>\n%s" % (OWNER_ID, "\n".join(f"• <code>{r['telegram_id']}</code> — {r['role']}" for r in rows) or "ادمین دیگری ثبت نشده.")
    await m.answer(body,parse_mode="HTML",reply_markup=markup([[kb("➕ افزودن ادمین","success"),kb("🗑 حذف ادمین","danger")],[kb(BUTTON_BACK,"danger")]]))


@dp.message(F.text=="➕ افزودن ادمین")
async def add_admin_start(m,state):
    if m.from_user.id!=OWNER_ID:return
    await state.set_state(S.add_admin);await m.answer("Username مثل @user یا Forward پیام کاربر را ارسال کنید.",reply_markup=back_kb())


@dp.message(S.add_admin)
async def add_admin(m,state):
    if m.from_user.id!=OWNER_ID:return
    uid=None
    origin=getattr(m,"forward_origin",None)
    sender=getattr(origin,"sender_user",None)
    if sender:uid=sender.id
    elif (m.text or "").startswith("@"):
        x=await db();c=await x.execute("SELECT telegram_id FROM users WHERE username=?",(m.text[1:],));r=await c.fetchone();await x.close();uid=r["telegram_id"] if r else None
    elif (m.text or "").isdigit(): uid=int(m.text)  # compatibility fallback
    if not uid:return await m.answer("کاربر پیدا نشد. ابتدا کاربر باید با ربات تعامل کرده باشد یا پیامش را Forward کنید.")
    x=await db();await x.execute("INSERT OR IGNORE INTO admins(telegram_id) VALUES(?)",(uid,));await x.commit();await x.close();await state.clear();await m.answer("✅ ادمین اضافه شد.",reply_markup=admin_kb())


@dp.message(F.text=="🗑 حذف ادمین")
async def delete_admin_start(m,state):
    if m.from_user.id!=OWNER_ID:return
    x=await db();c=await x.execute("SELECT telegram_id,role FROM admins ORDER BY telegram_id");rows=await c.fetchall();await x.close()
    await state.set_state(S.delete_admin_select);await m.answer("ادمین را انتخاب کنید:",reply_markup=markup([[kb(f"🗑 #{r['telegram_id']} | {r['role']}","danger")] for r in rows]+[[kb(BUTTON_BACK,"danger")]]))


@dp.message(S.delete_admin_select)
async def delete_admin_select(m,state):
    uid=parse_id(m.text)
    if not uid:return
    if uid==OWNER_ID:return await m.answer("⛔ Owner اصلی قابل حذف نیست.")
    await state.update_data(delete_admin_id=uid);await state.set_state(S.delete_admin_confirm)
    await m.answer("آیا از حذف این Admin مطمئن هستید؟",reply_markup=markup([[kb(BUTTON_YES,"danger"),kb(BUTTON_NO,"primary")],[kb(BUTTON_BACK,"danger")]]))


@dp.message(S.delete_admin_confirm)
async def delete_admin_confirm(m,state):
    if m.text==BUTTON_NO:await state.clear();return await m.answer("لغو شد.",reply_markup=admin_kb())
    if m.text!=BUTTON_YES:return
    uid=(await state.get_data()).get("delete_admin_id");x=await db();await x.execute("DELETE FROM admins WHERE telegram_id=? AND telegram_id<>?",(uid,OWNER_ID));await x.commit();await x.close();await state.clear();await m.answer("✅ ادمین حذف شد.",reply_markup=admin_kb())


# ---------------- Forced join ----------------

@dp.message(F.text=="📢 جوین اجباری")
async def channels_menu(m,state):
    if not await is_admin(m.from_user.id):return
    x=await db();c=await x.execute("SELECT * FROM channels ORDER BY id");rows=await c.fetchall();await x.close()
    body="\n".join(f"{'🟢' if r['active'] else '🔴'} #{r['id']} | {html.escape(r['title'])} | @{html.escape(r['username'] or '-')}" for r in rows) or "کانالی ثبت نشده."
    await m.answer("📢 <b>جوین اجباری</b>\n\n"+body,parse_mode="HTML",
                   reply_markup=markup([[kb("➕ افزودن کانال","success"),kb("🗑 حذف کانال","danger")],[kb("🔄 فعال/غیرفعال","primary"),kb("🧪 تست عضویت","primary")],[kb(BUTTON_BACK,"danger")]]))


@dp.message(F.text=="➕ افزودن کانال")
async def add_channel_start(m,state):
    await state.set_state(S.add_channel_username);await m.answer("Username کانال مثل @channel را ارسال کنید.",reply_markup=back_kb())


@dp.message(S.add_channel_username)
async def add_channel_username(m,state):
    username=(m.text or "").strip()
    if not username.startswith("@"):return await m.answer("Username باید با @ شروع شود.")
    try:chat=await m.bot.get_chat(username)
    except Exception as e:return await m.answer(f"❌ کانال پیدا نشد یا ربات دسترسی ندارد.\n{html.escape(str(e))}")
    await state.update_data(channel_username=username,channel_id=str(chat.id));await state.set_state(S.add_channel_title)
    await m.answer("عنوان نمایشی کانال را بفرستید:",reply_markup=back_kb())


@dp.message(S.add_channel_title)
async def add_channel_title(m,state):
    z=await state.get_data();username=z["channel_username"];link=f"https://t.me/{username.lstrip('@')}"
    x=await db();await x.execute("INSERT INTO channels(title,chat_id,username,link) VALUES(?,?,?,?)",(m.text or username,z["channel_id"],username,link));await x.commit();await x.close();await state.clear()
    await m.answer("✅ کانال اضافه شد. مطمئن شوید Bot دسترسی لازم برای getChatMember دارد.",reply_markup=admin_kb())


@dp.message(F.text=="🗑 حذف کانال")
async def delete_channel_start(m,state):
    x=await db();c=await x.execute("SELECT * FROM channels ORDER BY id");rows=await c.fetchall();await x.close()
    await state.set_state(S.delete_channel_select);await m.answer("کانال را انتخاب کنید:",reply_markup=markup([[kb(f"🗑 #{r['id']} | {r['title']}","danger")] for r in rows]+[[kb(BUTTON_BACK,"danger")]]))


@dp.message(S.delete_channel_select)
async def delete_channel_select(m,state):
    cid=parse_id(m.text)
    if not cid:return
    await state.update_data(delete_channel_id=cid);x=await db();await x.execute("DELETE FROM channels WHERE id=?",(cid,));await x.commit();await x.close();await state.clear();await m.answer("🗑 کانال حذف شد.",reply_markup=admin_kb())


@dp.message(F.text=="🔄 فعال/غیرفعال")
async def toggle_channel_start(m,state):
    x=await db();c=await x.execute("SELECT * FROM channels ORDER BY id");rows=await c.fetchall();await x.close()
    await state.set_state(S.toggle_channel_select);await m.answer("کانال را انتخاب کنید:",reply_markup=markup([[kb(f"🔄 #{r['id']} | {r['title']}","primary")] for r in rows]+[[kb(BUTTON_BACK,"danger")]]))


@dp.message(S.toggle_channel_select)
async def toggle_channel_select(m,state):
    cid=parse_id(m.text)
    if not cid:return
    x=await db();await x.execute("UPDATE channels SET active=1-active WHERE id=?",(cid,));await x.commit();await x.close();await state.clear();await m.answer("✅ وضعیت کانال تغییر کرد.",reply_markup=admin_kb())


@dp.message(F.text=="🧪 تست عضویت")
async def test_join(m):
    if not await is_admin(m.from_user.id):return
    missing=await check_required_join(m.bot,m.from_user.id)
    await m.answer("❌ عضویت ناقص است." if missing else "✅ تست عضویت موفق بود.",reply_markup=admin_kb())


# ---------------- Broadcast ----------------

@dp.message(F.text=="📣 پیام همگانی")
async def broadcast_start(m,state):
    if not await is_admin(m.from_user.id):return
    await state.set_state(S.broadcast);await m.answer("پیام یا Media برای Broadcast ارسال کنید.",reply_markup=back_kb())


@dp.message(S.broadcast)
async def broadcast_send(m,state):
    x=await db();c=await x.execute("SELECT telegram_id FROM users WHERE blocked=0 AND course_access=1");users=await c.fetchall();await x.close()
    ok=bad=0
    for u in users:
        try:await m.bot.copy_message(u["telegram_id"],m.chat.id,m.message_id);ok+=1
        except Exception:bad+=1
    await state.clear();await m.answer(f"📣 Broadcast تمام شد.\n✅ موفق: {ok}\n❌ ناموفق: {bad}",reply_markup=admin_kb())


# ---------------- Statistics ----------------

@dp.message(F.text=="📊 آمار")
async def stats(m):
    if not await is_admin(m.from_user.id):return
    x=await db()
    async def n(q, args=()):
        c=await x.execute(q,args);r=await c.fetchone();return r[0] or 0
    now=datetime.now(timezone.utc);today=now.date().isoformat()
    week=(now-timedelta(days=7)).isoformat();month=(now-timedelta(days=30)).isoformat()
    vals={
        "users":await n("SELECT COUNT(*) FROM users"),"active":await n("SELECT COUNT(*) FROM users WHERE last_activity>=?",(week,)),
        "today":await n("SELECT COUNT(*) FROM users WHERE created_at>=?",(today,)),
        "week":await n("SELECT COUNT(*) FROM users WHERE created_at>=?",(week,)),
        "month":await n("SELECT COUNT(*) FROM users WHERE created_at>=?",(month,)),
        "chapters":await n("SELECT COUNT(*) FROM chapters"),"lessons":await n("SELECT COUNT(*) FROM lessons"),
        "published":await n("SELECT COUNT(*) FROM lessons WHERE published=1"),"quizzes":await n("SELECT COUNT(*) FROM quizzes"),
        "tickets":await n("SELECT COUNT(*) FROM tickets"),"blocked":await n("SELECT COUNT(*) FROM users WHERE blocked=1"),
        "completed":await n("SELECT COUNT(*) FROM progress WHERE completed_at IS NOT NULL"),
        "passed":await n("SELECT COUNT(*) FROM attempts WHERE passed=1"),"failed":await n("SELECT COUNT(*) FROM attempts WHERE passed=0"),
        "avgprog":await n("SELECT COUNT(*) FROM progress WHERE video_done=1")
    }
    c=await x.execute("SELECT AVG(v) FROM (SELECT user_id,AVG(CASE WHEN video_done=1 THEN 1.0 ELSE 0 END) v FROM progress GROUP BY user_id)");avg=c.fetchone()
    avgprog=(await avg)["AVG(v)"] or 0
    c=await x.execute("""SELECT l.title,COUNT(p.user_id) n FROM progress p JOIN lessons l ON l.id=p.lesson_id
                         WHERE p.video_done=1 GROUP BY l.id ORDER BY n DESC LIMIT 5""");popular=await c.fetchall();await x.close()
    pop="\n".join(f"• {r['title']} — {r['n']}" for r in popular) or "—"
    await m.answer(f"""📊 <b>آمار آکادمی</b>
👥 کل کاربران: {vals['users']}
🟢 فعال: {vals['active']}
🆕 امروز: {vals['today']} | هفته: {vals['week']} | ماه: {vals['month']}
📚 فصل‌ها: {vals['chapters']}
🎬 درس‌ها: {vals['lessons']} | منتشرشده: {vals['published']}
📝 آزمون‌ها: {vals['quizzes']}
🎫 Ticketها: {vals['tickets']}
🚫 Block شده: {vals['blocked']}
📈 میانگین Progress: {round(avgprog*100,1)}%
🏁 تکمیل دوره: {vals['completed']}
🏆 قبولی آزمون: {vals['passed']} | رد: {vals['failed']}

🔥 محبوب‌ترین درس‌ها:
{pop}""",parse_mode="HTML",reply_markup=admin_kb())


# ---------------- Settings ----------------

@dp.message(F.text=="⚙️ تنظیمات")
async def settings_menu(m,state):
    if not await is_admin(m.from_user.id):return
    vals={k:await setting(k) for k in ("registration_enabled","quiz_enabled","forced_join_enabled","bot_enabled")}
    await state.clear();await state.update_data(screen="settings")
    await m.answer(f"""⚙️ <b>تنظیمات</b>
📝 ثبت‌نام: {'🟢' if vals['registration_enabled']=='1' else '🔴'}
📝 آزمون: {'🟢' if vals['quiz_enabled']=='1' else '🔴'}
📢 جوین اجباری: {'🟢' if vals['forced_join_enabled']=='1' else '🔴'}
🤖 وضعیت ربات: {'🟢' if vals['bot_enabled']=='1' else '🔴'}""",parse_mode="HTML",
                   reply_markup=markup([[kb("🔄 ثبت‌نام","primary"),kb("🔄 آزمون","primary")],
                                        [kb("🔄 جوین اجباری","primary"),kb("🔄 وضعیت ربات","primary")],
                                        [kb("✏️ متن Start","primary"),kb("✏️ متن پشتیبانی","primary")],
                                        [kb("✏️ متن آموزش","primary")],[kb(BUTTON_BACK,"danger")]]))


@dp.message(F.text.in_({"🔄 ثبت‌نام","🔄 آزمون","🔄 جوین اجباری","🔄 وضعیت ربات"}))
async def toggle_setting(m):
    mapping={"🔄 ثبت‌نام":"registration_enabled","🔄 آزمون":"quiz_enabled","🔄 جوین اجباری":"forced_join_enabled","🔄 وضعیت ربات":"bot_enabled"}
    k=mapping[m.text];v=await setting(k,"1");await set_setting(k,"0" if v=="1" else "1");await m.answer("✅ تنظیم ذخیره شد.")


@dp.message(F.text.in_({"✏️ متن Start","✏️ متن پشتیبانی","✏️ متن آموزش"}))
async def text_setting_start(m,state):
    mapping={"✏️ متن Start":"start_text","✏️ متن پشتیبانی":"support_text","✏️ متن آموزش":"lesson_text"}
    await state.set_state(S.settings_value);await state.update_data(setting_key=mapping[m.text]);await m.answer("متن جدید را ارسال کنید.",reply_markup=back_kb())


@dp.message(S.settings_value)
async def settings_value(m,state):
    z=await state.get_data();await set_setting(z["setting_key"],m.text or "");await state.clear();await m.answer("✅ تنظیم ذخیره شد.",reply_markup=admin_kb())


# ---------------- Quiz learner finalization ----------------

async def finish_or_next(bot,chat_id,user_id,state,timed_out=False):
    if bot is None:
        return
    data=await state.get_data()
    if not data.get("question_id"):return
    x=await db();c=await x.execute("SELECT * FROM options WHERE question_id=?",(data["question_id"],));opts=await c.fetchall()
    c=await x.execute("SELECT * FROM questions WHERE quiz_id=? ORDER BY position,id",(data["quiz_id"],));questions=await c.fetchall();await x.close()
    idx=data["q_index"];score=data.get("score",0)
    if timed_out:
        pass
    await state.update_data(q_index=idx+1,score=score)
    if idx+1 < len(questions):
        # This helper cannot send through a Message object; caller paths use send_question directly.
        return


@dp.message(S.quiz_answer)
async def learner_answer(m,state):
    data=await state.get_data()
    x=await db();c=await x.execute("SELECT * FROM options WHERE question_id=?",(data["question_id"],));opts=await c.fetchall()
    correct=next((o for o in opts if o["is_correct"]),None);await x.close()
    if m.text and correct and m.text.replace("🔹 ","",1)==correct["text"]:
        score=data.get("score",0)+1
    else:score=data.get("score",0)
    x=await db();c=await x.execute("SELECT * FROM questions WHERE quiz_id=? ORDER BY position,id",(data["quiz_id"],));questions=await c.fetchall();await x.close()
    idx=data["q_index"]+1
    await state.update_data(q_index=idx,score=score,question_id=None)
    if idx < len(questions):
        return await send_question(m,state)
    x=await db();c=await x.execute("SELECT * FROM quizzes WHERE id=?",(data["quiz_id"],));quiz=await c.fetchone()
    c=await x.execute("SELECT id FROM users WHERE telegram_id=?",(m.from_user.id,));u=await c.fetchone()
    passed=(score*100//len(questions)) >= quiz["pass_percent"]
    await x.execute("INSERT INTO attempts(user_id,quiz_id,score,passed,started_at,finished_at) VALUES(?,?,?,?,?,?)",
                    (u["id"],quiz["id"],score,int(passed),data.get("started"),datetime.now(timezone.utc).isoformat()))
    await x.execute("""INSERT INTO progress(user_id,lesson_id,video_done,quiz_passed,completed_at) VALUES(?,?,?,?,?)
                       ON CONFLICT(user_id,lesson_id) DO UPDATE SET video_done=1,quiz_passed=excluded.quiz_passed,completed_at=excluded.completed_at""",
                    (u["id"],data["lesson_id"],1,int(passed),datetime.now(timezone.utc).isoformat() if passed else None))
    await x.commit();await x.close();await state.clear()
    if passed:
        await m.answer(f"🏆 قبول شدی!\nنمره: {score}/{len(questions)}\nدرس بعدی باز شد.",reply_markup=user_kb(await is_admin(m.from_user.id)))
    else:
        await m.answer(f"❌ قبول نشدی.\nنمره: {score}/{len(questions)}\nبرای تلاش مجدد دوباره وارد درس شو.",reply_markup=user_kb(await is_admin(m.from_user.id)))


# ---------------- Startup ----------------

async def main():
    if not TOKEN: raise RuntimeError("BOT_TOKEN is missing")
    if not OWNER_ID: raise RuntimeError("OWNER_ID is missing")
    verify_keyboard_api()
    await init_db()
    bot=Bot(TOKEN)
    me=await bot.get_me()
    log.info("Starting @%s", me.username)
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__=="__main__":
    asyncio.run(main())
