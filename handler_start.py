from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message
from auth import ensure_user,is_admin
from keyboards_main import main_keyboard
router=Router()

@router.message(CommandStart())
async def start(m:Message):
    await ensure_user(m.from_user)
    await m.answer("👋 خوش آمدید!\n\n🎓 آموزش ترید را مرحله‌به‌مرحله دنبال کنید.", reply_markup=main_keyboard(await is_admin(m.from_user.id)))
