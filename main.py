import asyncio, os, html
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
import aiosqlite
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

load_dotenv()
TOKEN=os.getenv("BOT_TOKEN","")
OWNER_ID=int(os.getenv("OWNER_ID","0"))
if not TOKEN: raise RuntimeError("BOT_TOKEN is missing")
DB="data/bot.db"
START_E=os.getenv("START_EMOJI_ID","") or None
SUPPORT_E=os.getenv("SUPPORT_EMOJI_ID","") or None
ADMIN_E=os.getenv("ADMIN_EMOJI_ID","") or None

async def db():
    os.makedirs("data",exist_ok=True)
    x=await aiosqlite.connect(DB); x.row_factory=aiosqlite.Row
    await x.execute("PRAGMA foreign_keys=ON"); return x

async def init_db():
    x=await db()
    await x.executescript("""
    CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, telegram_id INTEGER UNIQUE, username TEXT, first_name TEXT, blocked INTEGER DEFAULT 0, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS admins(telegram_id INTEGER PRIMARY KEY, role TEXT DEFAULT 'admin');
    CREATE TABLE IF NOT EXISTS chapters(id INTEGER PRIMARY KEY AUTOINCREMENT,title TEXT,description TEXT DEFAULT '',position INTEGER DEFAULT 0,active INTEGER DEFAULT 1);
    CREATE TABLE IF NOT EXISTS lessons(id INTEGER PRIMARY KEY AUTOINCREMENT,chapter_id INTEGER REFERENCES chapters(id) ON DELETE CASCADE,title TEXT,description TEXT DEFAULT '',position INTEGER DEFAULT 0,video_file_id TEXT,duration INTEGER DEFAULT 0,active INTEGER DEFAULT 1);
    CREATE TABLE IF NOT EXISTS quizzes(id INTEGER PRIMARY KEY AUTOINCREMENT,lesson_id INTEGER UNIQUE REFERENCES lessons(id) ON DELETE CASCADE,pass_percent INTEGER DEFAULT 70,time_limit INTEGER DEFAULT 180,cooldown INTEGER DEFAULT 300);
    CREATE TABLE IF NOT EXISTS questions(id INTEGER PRIMARY KEY AUTOINCREMENT,quiz_id INTEGER REFERENCES quizzes(id) ON DELETE CASCADE,text TEXT,position INTEGER DEFAULT 0);
    CREATE TABLE IF NOT EXISTS options(id INTEGER PRIMARY KEY AUTOINCREMENT,question_id INTEGER REFERENCES questions(id) ON DELETE CASCADE,text TEXT,is_correct INTEGER DEFAULT 0);
    CREATE TABLE IF NOT EXISTS progress(user_id INTEGER,lesson_id INTEGER,video_started TEXT,video_done INTEGER DEFAULT 0,quiz_passed INTEGER DEFAULT 0,PRIMARY KEY(user_id,lesson_id));
    CREATE TABLE IF NOT EXISTS attempts(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,quiz_id INTEGER,score INTEGER,passed INTEGER,started_at TEXT,finished_at TEXT);
    CREATE TABLE IF NOT EXISTS channels(id INTEGER PRIMARY KEY AUTOINCREMENT,title TEXT,chat_id TEXT,link TEXT,active INTEGER DEFAULT 1);
    CREATE TABLE IF NOT EXISTS tickets(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,status TEXT DEFAULT 'open',created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS ticket_messages(id INTEGER PRIMARY KEY AUTOINCREMENT,ticket_id INTEGER,sender_id INTEGER,text TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    """)
    await x.commit(); await x.close()

async def is_admin(uid):
    if uid==OWNER_ID:return True
    x=await db(); c=await x.execute("SELECT 1 FROM admins WHERE telegram_id=?",(uid,));r=await c.fetchone();await x.close();return bool(r)

async def ensure_user(u):
    x=await db()
    await x.execute("""INSERT INTO users(telegram_id,username,first_name) VALUES(?,?,?)
    ON CONFLICT(telegram_id) DO UPDATE SET username=excluded.username,first_name=excluded.first_name""",(u.id,u.username,u.first_name))
    await x.commit();await x.close()

# Telegram Bot API 9.4+ reply keyboard style/icon fields.
# No inline keyboard is used anywhere in this project.
def kb_button(text, style="primary", emoji_id=None):
    kw={"text":text}
    if style: kw["style"]=style
    if emoji_id: kw["icon_custom_emoji_id"]=emoji_id
    return KeyboardButton(**kw)

def user_kb(admin=False):
    rows=[
        [kb_button("🎓 شروع یادگیری","success",START_E),kb_button("💬 پشتیبانی","primary",SUPPORT_E)],
    ]
    if admin: rows.append([kb_button("👑 پنل مدیریت","primary",ADMIN_E)])
    return ReplyKeyboardMarkup(keyboard=rows,resize_keyboard=True,is_persistent=True)

def back_kb(*buttons):
    rows=[[kb_button(b,"primary") for b in buttons]]
    rows.append([kb_button("⬅️ بازگشت","danger")])
    return ReplyKeyboardMarkup(keyboard=rows,resize_keyboard=True,is_persistent=True)

def admin_kb():
    rows=[
      [kb_button("📚 مدیریت فصل‌ها","success"),kb_button("🎬 مدیریت درس‌ها","success")],
      [kb_button("📝 مدیریت آزمون‌ها","primary"),kb_button("👥 کاربران","primary")],
      [kb_button("👑 ادمین‌ها","primary"),kb_button("💬 پشتیبانی","primary")],
      [kb_button("📢 جوین اجباری","success"),kb_button("📣 پیام همگانی","primary")],
      [kb_button("📊 آمار","success"),kb_button("⚙️ تنظیمات","primary")],
      [kb_button("⬅️ بازگشت","danger")]
    ]
    return ReplyKeyboardMarkup(keyboard=rows,resize_keyboard=True,is_persistent=True)

def chapter_manage_kb():
    return ReplyKeyboardMarkup(keyboard=[
      [kb_button("➕ افزودن فصل","success"),kb_button("✏️ ویرایش فصل","primary")],
      [kb_button("🗑 حذف فصل","danger"),kb_button("📋 لیست فصل‌ها","primary")],
      [kb_button("⬅️ بازگشت","danger")]],resize_keyboard=True,is_persistent=True)

def lesson_manage_kb():
    return ReplyKeyboardMarkup(keyboard=[
      [kb_button("➕ افزودن درس","success"),kb_button("✏️ ویرایش درس","primary")],
      [kb_button("🗑 حذف درس","danger"),kb_button("📋 لیست درس‌ها","primary")],
      [kb_button("⬅️ بازگشت","danger")]],resize_keyboard=True,is_persistent=True)

def quiz_manage_kb():
    return ReplyKeyboardMarkup(keyboard=[
      [kb_button("➕ ساخت آزمون","success"),kb_button("➕ افزودن سؤال","primary")],
      [kb_button("✏️ تنظیم آزمون","primary"),kb_button("🗑 حذف آزمون","danger")],
      [kb_button("📋 لیست آزمون‌ها","primary"),kb_button("⬅️ بازگشت","danger")]],resize_keyboard=True,is_persistent=True)

class S(StatesGroup):
    add_ch_title=State(); add_ch_desc=State()
    edit_ch_id=State(); edit_ch_title=State(); edit_ch_desc=State()
    del_ch_id=State()
    add_l_ch=State(); add_l_title=State(); add_l_desc=State(); add_l_duration=State(); add_l_video=State()
    edit_l_id=State(); edit_l_title=State(); edit_l_desc=State(); edit_l_duration=State()
    del_l_id=State()
    quiz_lesson=State(); quiz_pass=State(); quiz_time=State()
    question_quiz=State(); question_text=State(); question_options=State(); question_correct=State()
    ticket_user=State(); ticket_reply=State()
    add_admin=State(); del_admin=State()
    add_channel_title=State(); add_channel_id=State(); add_channel_link=State(); del_channel=State()
    broadcast=State()

async def home(m):
    await m.answer("✨ <b>آکادمی آموزش ترید</b>\n\n🎓 آموزش‌ها مرحله‌به‌مرحله هستند.\n💬 پشتیبانی همیشه در دسترس است.",
                   parse_mode="HTML",reply_markup=user_kb(await is_admin(m.from_user.id)))

async def chapters_for_user(m):
    x=await db();c=await x.execute("SELECT * FROM chapters WHERE active=1 ORDER BY position,id");rows=await c.fetchall();await x.close()
    if not rows:return await m.answer("📚 هنوز فصلی اضافه نشده.",reply_markup=user_kb(await is_admin(m.from_user.id)))
    text="📚 <b>فصل‌ها</b>\n\n"+"\n".join(f"• {i+1}. {html.escape(r['title'])}" for i,r in enumerate(rows))
    # Reply keyboard: chapters become actual keyboard buttons.
    rows_k=[[kb_button(f"📚 {r['title']}","success")] for r in rows]
    rows_k.append([kb_button("⬅️ بازگشت","danger")])
    await m.answer(text,parse_mode="HTML",reply_markup=ReplyKeyboardMarkup(keyboard=rows_k,resize_keyboard=True,is_persistent=True))

async def check_required_join(bot,uid):
    x=await db();c=await x.execute("SELECT * FROM channels WHERE active=1");chs=await c.fetchall();await x.close()
    missing=[]
    for ch in chs:
        try:
            member=await bot.get_chat_member(ch["chat_id"],uid)
            if member.status in ("left","kicked"):missing.append(ch)
        except Exception: missing.append(ch)
    return missing

@__import__("functools").lru_cache(maxsize=1)
def dummy(): return None

bot=None
dp=Dispatcher()

@dp.message(CommandStart())
async def start(m:Message,state:FSMContext):
    await state.clear();await ensure_user(m.from_user)
    missing=await check_required_join(m.bot,m.from_user.id)
    if missing:
        links="\n".join(f"📢 {html.escape(c['title'])}: {c['link'] or c['chat_id']}" for c in missing)
        return await m.answer(f"🔐 <b>عضویت اجباری</b>\n\nابتدا در کانال‌های زیر عضو شو:\n\n{links}\n\nبعد دوباره /start را بزن.",parse_mode="HTML",reply_markup=user_kb(await is_admin(m.from_user.id)))
    await home(m)

@dp.message(F.text=="🎓 شروع یادگیری")
async def learn(m:Message):
    await chapters_for_user(m)

@dp.message(F.text=="⬅️ بازگشت")
async def back(m:Message,state:FSMContext):
    await state.clear();await home(m)

@dp.message(F.text=="💬 پشتیبانی")
async def support(m:Message):
    x=await db();c=await x.execute("SELECT id FROM users WHERE telegram_id=?",(m.from_user.id,));u=await c.fetchone()
    c=await x.execute("SELECT id FROM tickets WHERE user_id=? AND status='open' LIMIT 1",(u["id"],));t=await c.fetchone()
    if not t:
        c=await x.execute("INSERT INTO tickets(user_id) VALUES(?)",(u["id"],));tid=c.lastrowid;await x.commit()
    else:tid=t["id"]
    await x.close()
    await m.answer(f"💬 <b>پشتیبانی</b>\n\nپیامت را بفرست تا برای مدیریت ارسال شود.\n🎫 تیکت #{tid}",parse_mode="HTML",reply_markup=back_kb())

@dp.message(F.text=="👑 پنل مدیریت")
async def admin_panel(m:Message):
    if not await is_admin(m.from_user.id):return await m.answer("⛔ دسترسی ندارید.")
    await m.answer("👑 <b>پنل مدیریت</b>\n\nهمه عملیات از همین کیبورد انجام می‌شود.",parse_mode="HTML",reply_markup=admin_kb())

# -------- Chapters --------
@dp.message(F.text=="📚 مدیریت فصل‌ها")
async def ch_menu(m:Message):
    if await is_admin(m.from_user.id):await m.answer("📚 مدیریت فصل‌ها",reply_markup=chapter_manage_kb())

@dp.message(F.text=="➕ افزودن فصل")
async def ch_add(m:Message,state:FSMContext):
    if not await is_admin(m.from_user.id):return
    await state.set_state(S.add_ch_title);await m.answer("عنوان فصل را بفرست:")

@dp.message(S.add_ch_title)
async def ch_add_title(m:Message,state:FSMContext):
    await state.update_data(title=m.text);await state.set_state(S.add_ch_desc);await m.answer("توضیح فصل را بفرست یا «-» بزن:")

@dp.message(S.add_ch_desc)
async def ch_add_desc(m:Message,state:FSMContext):
    d= "" if m.text=="-" else m.text;x=await db()
    c=await x.execute("SELECT COALESCE(MAX(position),0)+1 p FROM chapters");p=(await c.fetchone())["p"]
    await x.execute("INSERT INTO chapters(title,description,position) VALUES(?,?,?)",( (await state.get_data())["title"],d,p));await x.commit();await x.close()
    await state.clear();await m.answer("✅ فصل ساخته شد.",reply_markup=chapter_manage_kb())

@dp.message(F.text=="📋 لیست فصل‌ها")
async def ch_list(m:Message):
    if not await is_admin(m.from_user.id):return
    x=await db();c=await x.execute("SELECT * FROM chapters ORDER BY position,id");r=await c.fetchall();await x.close()
    await m.answer("📚 فصل‌ها:\n\n"+"\n".join(f"#{z['id']} — {z['title']}" for z in r) if r else "هیچ فصلی وجود ندارد.",reply_markup=chapter_manage_kb())

@dp.message(F.text=="✏️ ویرایش فصل")
async def ch_edit(m:Message,state:FSMContext):
    if await is_admin(m.from_user.id):await state.set_state(S.edit_ch_id);await m.answer("ID فصل را بفرست:")

@dp.message(S.edit_ch_id)
async def ch_edit_id(m:Message,state:FSMContext):
    await state.update_data(id=int(m.text));await state.set_state(S.edit_ch_title);await m.answer("عنوان جدید:")

@dp.message(S.edit_ch_title)
async def ch_edit_title(m:Message,state:FSMContext):
    await state.update_data(title=m.text);await state.set_state(S.edit_ch_desc);await m.answer("توضیح جدید یا - :")

@dp.message(S.edit_ch_desc)
async def ch_edit_desc(m:Message,state:FSMContext):
    d="" if m.text=="-" else m.text;z=await state.get_data();x=await db()
    await x.execute("UPDATE chapters SET title=?,description=? WHERE id=?",(z["title"],d,z["id"]));await x.commit();await x.close();await state.clear()
    await m.answer("✅ فصل ویرایش شد.",reply_markup=chapter_manage_kb())

@dp.message(F.text=="🗑 حذف فصل")
async def ch_del(m:Message,state:FSMContext):
    if await is_admin(m.from_user.id):await state.set_state(S.del_ch_id);await m.answer("ID فصل برای حذف:")

@dp.message(S.del_ch_id)
async def ch_del_id(m:Message,state:FSMContext):
    x=await db();await x.execute("DELETE FROM chapters WHERE id=?",(int(m.text),));await x.commit();await x.close();await state.clear();await m.answer("🗑 فصل حذف شد.",reply_markup=chapter_manage_kb())

# -------- Lessons --------
@dp.message(F.text=="🎬 مدیریت درس‌ها")
async def l_menu(m:Message):
    if await is_admin(m.from_user.id):await m.answer("🎬 مدیریت درس‌ها",reply_markup=lesson_manage_kb())

@dp.message(F.text=="➕ افزودن درس")
async def l_add(m:Message,state:FSMContext):
    if not await is_admin(m.from_user.id):return
    await state.set_state(S.add_l_ch);await m.answer("ID فصل را بفرست:")

@dp.message(S.add_l_ch)
async def l_ch(m:Message,state:FSMContext):
    await state.update_data(ch=int(m.text));await state.set_state(S.add_l_title);await m.answer("عنوان درس:")

@dp.message(S.add_l_title)
async def l_title(m:Message,state:FSMContext):
    await state.update_data(title=m.text);await state.set_state(S.add_l_desc);await m.answer("توضیح درس یا - :")

@dp.message(S.add_l_desc)
async def l_desc(m:Message,state:FSMContext):
    await state.update_data(desc="" if m.text=="-" else m.text);await state.set_state(S.add_l_duration);await m.answer("مدت ویدیو به ثانیه (مثلاً 900):")

@dp.message(S.add_l_duration)
async def l_duration(m:Message,state:FSMContext):
    await state.update_data(duration=int(m.text));await state.set_state(S.add_l_video);await m.answer("حالا خود ویدیو را همینجا بفرست:")

@dp.message(S.add_l_video, F.video)
async def l_video(m:Message,state:FSMContext):
    z=await state.get_data();x=await db()
    c=await x.execute("SELECT COALESCE(MAX(position),0)+1 p FROM lessons WHERE chapter_id=?",(z["ch"],));p=(await c.fetchone())["p"]
    await x.execute("INSERT INTO lessons(chapter_id,title,description,position,video_file_id,duration) VALUES(?,?,?,?,?,?)",(z["ch"],z["title"],z["desc"],p,m.video.file_id,z["duration"]))
    await x.commit();await x.close();await state.clear();await m.answer("✅ درس + ویدیو ذخیره شد.",reply_markup=lesson_manage_kb())

@dp.message(S.add_l_video)
async def l_video_wrong(m:Message): await m.answer("❗ لطفاً ویدیو را به صورت Video تلگرام بفرست.")

@dp.message(F.text=="📋 لیست درس‌ها")
async def l_list(m:Message):
    if not await is_admin(m.from_user.id):return
    x=await db();c=await x.execute("SELECT l.*,c.title ct FROM lessons l JOIN chapters c ON c.id=l.chapter_id ORDER BY c.position,l.position");r=await c.fetchall();await x.close()
    await m.answer("🎬 درس‌ها:\n\n"+"\n".join(f"#{z['id']} | فصل {z['chapter_id']} | {z['title']} | {z['duration']}s" for z in r) if r else "هیچ درسی نیست.",reply_markup=lesson_manage_kb())

@dp.message(F.text=="🗑 حذف درس")
async def l_del(m:Message,state:FSMContext):
    if await is_admin(m.from_user.id):await state.set_state(S.del_l_id);await m.answer("ID درس:")

@dp.message(S.del_l_id)
async def l_del_id(m:Message,state:FSMContext):
    x=await db();await x.execute("DELETE FROM lessons WHERE id=?",(int(m.text),));await x.commit();await x.close();await state.clear();await m.answer("🗑 درس حذف شد.",reply_markup=lesson_manage_kb())

@dp.message(F.text=="✏️ ویرایش درس")
async def l_edit(m:Message,state:FSMContext):
    if await is_admin(m.from_user.id):await state.set_state(S.edit_l_id);await m.answer("ID درس:")

@dp.message(S.edit_l_id)
async def l_edit_id(m:Message,state:FSMContext):
    await state.update_data(id=int(m.text));await state.set_state(S.edit_l_title);await m.answer("عنوان جدید:")

@dp.message(S.edit_l_title)
async def l_edit_title(m:Message,state:FSMContext):
    await state.update_data(title=m.text);await state.set_state(S.edit_l_desc);await m.answer("توضیح جدید یا - :")

@dp.message(S.edit_l_desc)
async def l_edit_desc(m:Message,state:FSMContext):
    z=await state.get_data();x=await db();await x.execute("UPDATE lessons SET title=?,description=? WHERE id=?",(z["title"],"" if m.text=="-" else m.text,z["id"]));await x.commit();await x.close();await state.clear();await m.answer("✅ ویرایش شد.",reply_markup=lesson_manage_kb())

# -------- Quiz management --------
@dp.message(F.text=="📝 مدیریت آزمون‌ها")
async def q_menu(m:Message):
    if await is_admin(m.from_user.id):await m.answer("📝 مدیریت آزمون‌ها",reply_markup=quiz_manage_kb())

@dp.message(F.text=="➕ ساخت آزمون")
async def q_add(m:Message,state:FSMContext):
    if await is_admin(m.from_user.id):await state.set_state(S.quiz_lesson);await m.answer("ID درس:")

@dp.message(S.quiz_lesson)
async def q_lesson(m:Message,state:FSMContext):
    await state.update_data(lesson=int(m.text));await state.set_state(S.quiz_pass);await m.answer("درصد قبولی (مثلاً 70):")

@dp.message(S.quiz_pass)
async def q_pass(m:Message,state:FSMContext):
    await state.update_data(passp=int(m.text));await state.set_state(S.quiz_time);await m.answer("زمان آزمون به ثانیه:")

@dp.message(S.quiz_time)
async def q_time(m:Message,state:FSMContext):
    z=await state.get_data();x=await db()
    await x.execute("INSERT OR REPLACE INTO quizzes(lesson_id,pass_percent,time_limit) VALUES(?,?,?)",(z["lesson"],z["passp"],int(m.text)))
    await x.commit();await x.close();await state.clear();await m.answer("✅ آزمون ساخته شد. حالا از «➕ افزودن سؤال» سؤال‌ها را اضافه کن.",reply_markup=quiz_manage_kb())

@dp.message(F.text=="➕ افزودن سؤال")
async def q_question(m:Message,state:FSMContext):
    if await is_admin(m.from_user.id):await state.set_state(S.question_quiz);await m.answer("ID آزمون:")

@dp.message(S.question_quiz)
async def q_question_quiz(m:Message,state:FSMContext):
    await state.update_data(quiz=int(m.text));await state.set_state(S.question_text);await m.answer("متن سؤال:")

@dp.message(S.question_text)
async def q_question_text(m:Message,state:FSMContext):
    await state.update_data(text=m.text);await state.set_state(S.question_options);await m.answer("۴ گزینه را دقیقاً در ۴ خط بفرست:")

@dp.message(S.question_options)
async def q_options(m:Message,state:FSMContext):
    opts=[x.strip() for x in m.text.splitlines() if x.strip()]
    if len(opts)<2:return await m.answer("حداقل ۲ گزینه در خط‌های جداگانه بفرست.")
    await state.update_data(opts=opts);await state.set_state(S.question_correct);await m.answer("شماره گزینه صحیح را بفرست (از 1 شروع می‌شود):")

@dp.message(S.question_correct)
async def q_correct(m:Message,state:FSMContext):
    z=await state.get_data();x=await db();c=await x.execute("SELECT COALESCE(MAX(position),0)+1 p FROM questions WHERE quiz_id=?",(z["quiz"],));p=(await c.fetchone())["p"]
    c=await x.execute("INSERT INTO questions(quiz_id,text,position) VALUES(?,?,?)",(z["quiz"],z["text"],p));qid=c.lastrowid
    correct=int(m.text)-1
    for i,o in enumerate(z["opts"]):await x.execute("INSERT INTO options(question_id,text,is_correct) VALUES(?,?,?)",(qid,o,1 if i==correct else 0))
    await x.commit();await x.close();await state.clear();await m.answer("✅ سؤال اضافه شد.",reply_markup=quiz_manage_kb())

@dp.message(F.text=="📋 لیست آزمون‌ها")
async def q_list(m:Message):
    if not await is_admin(m.from_user.id):return
    x=await db();c=await x.execute("SELECT q.*,l.title lt FROM quizzes q JOIN lessons l ON l.id=q.lesson_id");r=await c.fetchall();await x.close()
    await m.answer("📝 آزمون‌ها:\n\n"+"\n".join(f"#{z['id']} | درس {z['lesson_id']} | قبولی {z['pass_percent']}% | زمان {z['time_limit']}s" for z in r) if r else "آزمونی نیست.",reply_markup=quiz_manage_kb())

@dp.message(F.text=="🗑 حذف آزمون")
async def q_del(m:Message):
    if not await is_admin(m.from_user.id):return await m.answer("⛔")
    await m.answer("برای حذف آزمون فعلاً ID آزمون را در قالب «حذف آزمون ID» بفرست.")

@dp.message(F.text.regexp(r"^حذف آزمون \d+$"))
async def q_del_real(m:Message):
    if not await is_admin(m.from_user.id):return
    qid=int(m.text.split()[-1]);x=await db();await x.execute("DELETE FROM quizzes WHERE id=?",(qid,));await x.commit();await x.close();await m.answer("🗑 آزمون حذف شد.",reply_markup=quiz_manage_kb())

# -------- Users/admins/channels/support/broadcast/stats --------
@dp.message(F.text=="👥 کاربران")
async def users(m:Message):
    if not await is_admin(m.from_user.id):return
    x=await db();c=await x.execute("SELECT COUNT(*) n FROM users");n=(await c.fetchone())["n"];c=await x.execute("SELECT * FROM users ORDER BY id DESC LIMIT 30");r=await c.fetchall();await x.close()
    await m.answer(f"👥 تعداد کاربران: {n}\n\n"+"\n".join(f"{z['id']} | {z['first_name']} | @{z['username'] or '-'} | {z['telegram_id']}" for z in r),reply_markup=admin_kb())

@dp.message(F.text=="👑 ادمین‌ها")
async def admins(m:Message):
    if not await is_admin(m.from_user.id):return
    await m.answer("👑 برای افزودن: «افزودن ادمین ID»\nبرای حذف: «حذف ادمین ID»\n\nمالک اصلی از OWNER_ID است.",reply_markup=admin_kb())

@dp.message(F.text.regexp(r"^افزودن ادمین \d+$"))
async def add_admin(m:Message):
    if m.from_user.id!=OWNER_ID:return
    uid=int(m.text.split()[-1]);x=await db();await x.execute("INSERT OR IGNORE INTO admins(telegram_id) VALUES(?)",(uid,));await x.commit();await x.close();await m.answer("✅ ادمین اضافه شد.",reply_markup=admin_kb())

@dp.message(F.text.regexp(r"^حذف ادمین \d+$"))
async def del_admin(m:Message):
    if m.from_user.id!=OWNER_ID:return
    uid=int(m.text.split()[-1]);x=await db();await x.execute("DELETE FROM admins WHERE telegram_id=?",(uid,));await x.commit();await x.close();await m.answer("🗑 ادمین حذف شد.",reply_markup=admin_kb())

@dp.message(F.text=="📢 جوین اجباری")
async def channels(m:Message):
    if not await is_admin(m.from_user.id):return
    await m.answer("📢 افزودن: «افزودن کانال | عنوان | chat_id | لینک»\nحذف: «حذف کانال ID»\nلیست: «لیست کانال‌ها»",reply_markup=admin_kb())

@dp.message(F.text.regexp(r"^افزودن کانال \|"))
async def add_channel(m:Message):
    if not await is_admin(m.from_user.id):return
    a=[x.strip() for x in m.text.split("|")]
    if len(a)!=4:return await m.answer("فرمت: افزودن کانال | عنوان | chat_id | لینک")
    x=await db();await x.execute("INSERT INTO channels(title,chat_id,link) VALUES(?,?,?)",(a[1],a[2],a[3]));await x.commit();await x.close();await m.answer("✅ کانال اجباری اضافه شد.",reply_markup=admin_kb())

@dp.message(F.text.regexp(r"^حذف کانال \d+$"))
async def del_channel(m:Message):
    if not await is_admin(m.from_user.id):return
    x=await db();await x.execute("DELETE FROM channels WHERE id=?",(int(m.text.split()[-1]),));await x.commit();await x.close();await m.answer("🗑 کانال حذف شد.",reply_markup=admin_kb())

@dp.message(F.text=="📣 پیام همگانی")
async def broadcast_start(m:Message,state:FSMContext):
    if await is_admin(m.from_user.id):await state.set_state(S.broadcast);await m.answer("متن پیام همگانی را بفرست:")

@dp.message(S.broadcast)
async def broadcast_send(m:Message,state:FSMContext):
    x=await db();c=await x.execute("SELECT telegram_id FROM users WHERE blocked=0");users=await c.fetchall();await x.close()
    ok=bad=0
    for u in users:
        try:await m.bot.send_message(u["telegram_id"],m.text);ok+=1
        except Exception:bad+=1
    await state.clear();await m.answer(f"📣 ارسال تمام شد.\n✅ {ok}\n❌ {bad}",reply_markup=admin_kb())

@dp.message(F.text=="📊 آمار")
async def stats(m:Message):
    if not await is_admin(m.from_user.id):return
    x=await db();vals=[]
    for t in ("users","chapters","lessons","quizzes","tickets","channels"):
        c=await x.execute(f"SELECT COUNT(*) n FROM {t}");vals.append((await c.fetchone())["n"])
    await x.close()
    await m.answer(f"📊 <b>آمار</b>\n\n👥 کاربران: {vals[0]}\n📚 فصل‌ها: {vals[1]}\n🎬 درس‌ها: {vals[2]}\n📝 آزمون‌ها: {vals[3]}\n💬 تیکت‌ها: {vals[4]}\n📢 کانال‌ها: {vals[5]}",parse_mode="HTML",reply_markup=admin_kb())

@dp.message(F.text=="💬 پشتیبانی",F.from_user.id==OWNER_ID)
async def admin_support(m:Message):
    x=await db();c=await x.execute("""SELECT t.id,u.telegram_id,u.first_name,COUNT(tm.id) n
        FROM tickets t JOIN users u ON u.id=t.user_id LEFT JOIN ticket_messages tm ON tm.ticket_id=t.id
        WHERE t.status='open' GROUP BY t.id ORDER BY t.id DESC""");r=await c.fetchall();await x.close()
    await m.answer("💬 تیکت‌های باز:\n\n"+"\n".join(f"#{z['id']} — {z['first_name']} — {z['n']} پیام" for z in r) if r else "تیکت بازی نیست.",reply_markup=admin_kb())

@dp.message(F.text.regexp(r"^پاسخ تیکت \d+ \|"))
async def ticket_reply(m:Message):
    if not await is_admin(m.from_user.id):return
    a=m.text.split("|",1);tid=int(a[0].split()[-1]);text=a[1].strip()
    x=await db();c=await x.execute("SELECT u.telegram_id FROM tickets t JOIN users u ON u.id=t.user_id WHERE t.id=?",(tid,));u=await c.fetchone()
    if not u:await x.close();return await m.answer("تیکت پیدا نشد.")
    await x.execute("INSERT INTO ticket_messages(ticket_id,sender_id,text) VALUES(?,?,?)",(tid,m.from_user.id,text));await x.commit();await x.close()
    try:await m.bot.send_message(u["telegram_id"],f"💬 <b>پاسخ پشتیبانی #{tid}</b>\n\n{html.escape(text)}",parse_mode="HTML");await m.answer("✅ پاسخ ارسال شد.",reply_markup=admin_kb())
    except Exception as e:await m.answer(f"❌ ارسال نشد: {e}",reply_markup=admin_kb())

# User ticket messages: placed last, but only when not an admin command.
@dp.message()
async def ticket_catcher(m:Message):
    if not m.text or m.text.startswith("/") or await is_admin(m.from_user.id):return
    x=await db();c=await x.execute("SELECT id FROM users WHERE telegram_id=?",(m.from_user.id,));u=await c.fetchone()
    if not u:await x.close();return
    c=await x.execute("SELECT id FROM tickets WHERE user_id=? AND status='open' ORDER BY id DESC LIMIT 1",(u["id"],));t=await c.fetchone()
    if not t:await x.close();return
    await x.execute("INSERT INTO ticket_messages(ticket_id,sender_id,text) VALUES(?,?,?)",(t["id"],m.from_user.id,m.text));await x.commit();await x.close()
    try:await m.bot.send_message(OWNER_ID,f"💬 <b>تیکت #{t['id']}</b>\n👤 {html.escape(m.from_user.full_name)}\n\n{html.escape(m.text)}\n\nبرای پاسخ:\n<code>پاسخ تیکت {t['id']} | متن پاسخ</code>",parse_mode="HTML")
    except Exception:pass
    await m.answer("✅ پیام شما برای پشتیبانی ارسال شد.",reply_markup=user_kb(False))

async def main():
    global bot
    await init_db()
    bot=Bot(TOKEN)
    await dp.start_polling(bot)

if __name__=="__main__":
    asyncio.run(main())
