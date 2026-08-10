import asyncio
from aiogram import Bot,Dispatcher
from config import BOT_TOKEN
from database import init_db
from handler_start import router as start_router
from handler_course import router as course_router
from handler_admin import router as admin_router
from handler_support import router as support_router

async def main():
    await init_db()
    bot=Bot(BOT_TOKEN); dp=Dispatcher()
    dp.include_router(start_router); dp.include_router(course_router)
    dp.include_router(admin_router); dp.include_router(support_router)
    await dp.start_polling(bot)

if __name__=="__main__": asyncio.run(main())
