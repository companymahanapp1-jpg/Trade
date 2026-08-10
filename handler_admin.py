from aiogram import Router,F
from aiogram.types import Message,CallbackQuery
from auth import is_admin
from ui import admin_kb,back
from database import connect
router=Router()
@router.callback_query(F.data=="admin")
async def admin_open(c:CallbackQuery):
    if not await is_admin(c.from_user.id):return await c.answer("⛔ دسترسی ندارید.",show_alert=True)
    await c.message.edit_text("👑 <b>پنل مدیریت</b>\n\nبخش موردنظر را انتخاب کن:",parse_mode="HTML",reply_markup=admin_kb());await c.answer()
@router.message(F.text=="👑 پنل مدیریت")
async def admin_message(m:Message):
    if not await is_admin(m.from_user.id):return await m.answer("⛔ دسترسی ندارید.")
    await m.answer("👑 <b>پنل مدیریت</b>",parse_mode="HTML",reply_markup=admin_kb())
@router.callback_query(F.data.startswith("adm:"))
async def adm(c:CallbackQuery):
    if not await is_admin(c.from_user.id):return await c.answer("⛔",show_alert=True)
    k=c.data.split(":")[1]
    if k=="stats":
        x=await connect();v=[]
        for t in ("users","chapters","lessons","tickets"):
            q=await x.execute(f"SELECT COUNT(*) n FROM {t}");v.append((await q.fetchone())["n"])
        await x.close();text=f"📊 <b>آمار</b>\n\n👥 کاربران: {v[0]}\n📚 فصل‌ها: {v[1]}\n🎬 درس‌ها: {v[2]}\n💬 تیکت‌ها: {v[3]}"
    else:
        labels={"chapters":"📚 مدیریت فصل‌ها","lessons":"🎬 مدیریت درس‌ها","quizzes":"📝 مدیریت آزمون‌ها","users":"👥 کاربران","admins":"👑 ادمین‌ها","tickets":"💬 پشتیبانی","channels":"📢 جوین اجباری","broadcast":"📣 پیام همگانی","settings":"⚙️ تنظیمات"}
        text=f"<b>{labels.get(k,k)}</b>\n\n🚧 این بخش هنوز CRUD کامل ندارد."
    await c.message.edit_text(text,parse_mode="HTML",reply_markup=back("admin"));await c.answer()
