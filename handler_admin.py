from aiogram import Router,F
from aiogram.types import Message,CallbackQuery
from auth import is_admin
from ui import admin_keyboard
from database import connect
router=Router()
@router.message(F.text=="👑 پنل مدیریت")
async def panel(m:Message):
    if not await is_admin(m.from_user.id):return await m.answer("⛔ دسترسی ندارید.")
    await m.answer("👑 <b>پنل مدیریت</b>\n\nیک بخش را انتخاب کنید:",parse_mode="HTML",reply_markup=admin_keyboard())
@router.callback_query(F.data.startswith("a:"))
async def menu(c:CallbackQuery):
    if not await is_admin(c.from_user.id):return await c.answer("⛔",show_alert=True)
    k=c.data[2:]
    if k=="back":await c.message.edit_text("👑 <b>پنل مدیریت</b>",parse_mode="HTML",reply_markup=admin_keyboard())
    elif k=="stats":
        x=await connect(); out=[]
        for t in ("users","chapters","lessons","tickets"):
            q=await x.execute(f"SELECT COUNT(*) n FROM {t}");out.append((await q.fetchone())["n"])
        await x.close()
        await c.message.edit_text(f"📊 <b>آمار</b>\n\n👥 {out[0]} کاربر\n📚 {out[1]} فصل\n🎬 {out[2]} درس\n💬 {out[3]} تیکت",parse_mode="HTML",reply_markup=admin_keyboard())
    else:
        names={"chapters":"📚 مدیریت فصل‌ها","lessons":"🎬 مدیریت درس‌ها","quizzes":"📝 مدیریت آزمون‌ها","users":"👥 کاربران","admins":"👑 ادمین‌ها","tickets":"💬 پشتیبانی","channels":"📢 عضویت اجباری","broadcast":"📣 پیام همگانی"}
        await c.message.edit_text(f"<b>{names.get(k,k)}</b>\n\nاین ماژول در ساختار دیتابیس آماده است.",parse_mode="HTML",reply_markup=admin_keyboard())
    await c.answer()
