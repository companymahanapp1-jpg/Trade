from aiogram import Router,F
from aiogram.types import Message,CallbackQuery
from course import chapters,lessons,lesson,can_open
from ui import chapters_kb,lessons_kb
from database import connect
router=Router()
@router.message(F.text=="🎓 شروع یادگیری")
async def learn(m:Message):
    r=await chapters()
    if not r:return await m.answer("📚 هنوز آموزشی اضافه نشده است.")
    await m.answer("📚 <b>فصل را انتخاب کنید:</b>",parse_mode="HTML",reply_markup=chapters_kb(r))
@router.callback_query(F.data.startswith("c:"))
async def chapter(c:CallbackQuery):
    r=await lessons(int(c.data[2:])); open_ids=set()
    for x in r:
        if await can_open(c.from_user.id,x["id"]):open_ids.add(x["id"])
    await c.message.edit_text("🎓 <b>درس‌های این فصل</b>",parse_mode="HTML",reply_markup=lessons_kb(r,open_ids)); await c.answer()
@router.callback_query(F.data.startswith("l:"))
async def open_lesson(c:CallbackQuery):
    lid=int(c.data[2:])
    if not await can_open(c.from_user.id,lid):return await c.answer("🔒 ابتدا درس قبلی و آزمون آن را کامل کنید.",show_alert=True)
    x=await lesson(lid)
    if x["video_file_id"]:await c.message.answer_video(x["video_file_id"],caption=f"🎬 <b>{x['title']}</b>\n{x['description']}",parse_mode="HTML")
    else:await c.message.answer("🎬 ویدیوی این درس هنوز آپلود نشده است.")
    await c.answer()
