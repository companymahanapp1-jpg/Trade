import asyncio
from aiogram import Bot,Dispatcher
from config import BOT_TOKEN
from database import init_db
import handler_start,handler_course,handler_admin,handler_support,handler_quiz
async def main():
    await init_db();bot=Bot(BOT_TOKEN);dp=Dispatcher()
    for r in (handler_start.router,handler_course.router,handler_admin.router,handler_support.router,handler_quiz.router):dp.include_router(r)
    await dp.start_polling(bot)
if __name__=="__main__":asyncio.run(main())
