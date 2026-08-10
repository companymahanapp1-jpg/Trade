from aiogram import Router,F
from aiogram.filters import CommandStart
from aiogram.types import Message,CallbackQuery
from auth import ensure_user,is_admin
from ui import main_inline
router=Router()
@router.message(CommandStart())
async def start(m:Message):
    await ensure_user(m.from_user)
    await m.answer("✨ <b>آکادمی آموزش ترید</b>\n\n🎓 مسیر آموزشی را مرحله‌به‌مرحله طی کن.\n💬 پشتیبانی همیشه در دسترس است.",parse_mode="HTML",reply_markup=main_inline(await is_admin(m.from_user.id)))
@router.callback_query(F.data=="home")
async def home(c:CallbackQuery):
    await c.message.edit_text("✨ <b>آکادمی آموزش ترید</b>\n\nیک گزینه را انتخاب کن:",parse_mode="HTML",reply_markup=main_inline(await is_admin(c.from_user.id)));await c.answer()
