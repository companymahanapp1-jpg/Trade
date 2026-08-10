from aiogram import Router,F
from aiogram.types import Message,CallbackQuery
from keyboards_inline import chapters_kb,lessons_kb
from course import chapters,lessons,lesson,can_access
from database import connect
from auth import is_admin
from keyboards_main import main_keyboard
router=Router()

@router.message(F.text=="🎓 شروع یادگیری")
async def learn(m:Message):
    rows=await chapters()
    await m.answer("📚 فصل موردنظر را انتخاب کنید:",reply_markup=chapters_kb(rows)) if rows else await m.answer("هنوز آموزشی ثبت نشده است.")

@router.callback_query(F.data.startswith("chapter:"))
async def chapter(c:CallbackQuery):
    cid=int(c.data.split(":")[1]); rows=await lessons(cid)
    unlocked=set()
    for x in rows:
        if await can_access(c.from_user.id,x["id"]): unlocked.add(x["id"])
    await c.message.edit_text("🎓 درس‌های این فصل:",reply_markup=lessons_kb(rows,unlocked)); await c.answer()

@router.callback_query(F.data.startswith("lesson:"))
async def lesson_open(c:CallbackQuery):
    lid=int(c.data.split(":")[1])
    if not await can_access(c.from_user.id,lid):
        await c.answer("🔒 ابتدا درس قبلی و آزمون آن را کامل کنید.",show_alert=True); return
    x=await lesson(lid)
    if x["video_file_id"]:
        await c.message.answer_video(x["video_file_id"],caption=f"🎬 {x['title']}\n{x['description'] or ''}")
    else:
        await c.message.answer(f"🎬 {x['title']}\n\nویدیوی این درس هنوز ثبت نشده است.")
    db=await connect()
    cur=await db.execute("SELECT id FROM users WHERE telegram_id=?",(c.from_user.id,)); u=await cur.fetchone()
    if u:
        await db.execute("INSERT OR IGNORE INTO progress(user_id,lesson_id,video_completed) VALUES(?,?,1)",(u["id"],lid))
        await db.execute("UPDATE progress SET video_completed=1 WHERE user_id=? AND lesson_id=?",(u["id"],lid))
    await db.commit(); await db.close()
    await c.message.answer("📝 پس از مشاهده درس، آزمون آن را انجام دهید.",reply_markup=main_keyboard(await is_admin(c.from_user.id))); await c.answer()
