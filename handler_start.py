from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message
from auth import ensure_user,is_admin
from ui import main_keyboard
router=Router()
@router.message(CommandStart())
async def start(m:Message):
    await ensure_user(m.from_user)
    await m.answer("✨ <b>به آکادمی آموزش ترید خوش آمدید!</b>\n\n🎓 آموزش را مرحله‌به‌مرحله دنبال کنید.\n💬 پشتیبانی همیشه در دسترس است.",parse_mode="HTML",reply_markup=main_keyboard(await is_admin(m.from_user.id)))
