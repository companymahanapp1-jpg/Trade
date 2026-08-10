from aiogram import Router,F
from aiogram.types import CallbackQuery
from course import get_chapters,get_lessons,get_lesson,can_open
from ui import chapters_kb,lessons_kb,back
router=Router()
@router.callback_query(F.data=="learn")
async def learn(c:CallbackQuery):
    r=await get_chapters()
    await c.message.edit_text("📚 <b>هنوز آموزشی اضافه نشده است.</b>",parse_mode="HTML",reply_markup=back("home")) if not r else await c.message.edit_text("📚 <b>فصل موردنظر را انتخاب کن:</b>",parse_mode="HTML",reply_markup=chapters_kb(r))
    await c.answer()
@router.callback_query(F.data.startswith("chapter:"))
async def chapter(c:CallbackQuery):
    r=await get_lessons(int(c.data.split(":")[1]));open_ids=set()
    for x in r:
        if await can_open(c.from_user.id,x["id"]):open_ids.add(x["id"])
    await c.message.edit_text("🎓 <b>درس‌های این فصل</b>",parse_mode="HTML",reply_markup=lessons_kb(r,open_ids));await c.answer()
@router.callback_query(F.data.startswith("lesson:"))
async def open_lesson(c:CallbackQuery):
    lid=int(c.data.split(":")[1])
    if not await can_open(c.from_user.id,lid):return await c.answer("🔒 ابتدا درس قبلی و آزمون آن را کامل کن.",show_alert=True)
    x=await get_lesson(lid)
    if x and x["video_file_id"]:await c.message.answer_video(x["video_file_id"],caption=f"🎬 <b>{x['title']}</b>\n{x['description']}",parse_mode="HTML")
    else:await c.message.answer("🎬 ویدیوی این درس هنوز توسط ادمین ثبت نشده است.")
    await c.answer()
