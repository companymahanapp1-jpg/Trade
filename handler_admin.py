from aiogram import Router,F
from aiogram.types import Message
from auth import is_admin
from database import connect
router=Router()

@router.message(F.text=="👑 پنل مدیریت")
async def panel(m:Message):
    if not await is_admin(m.from_user.id): return await m.answer("⛔ دسترسی ندارید.")
    db=await connect()
    counts={}
    for name,t in [("کاربران","users"),("فصل‌ها","chapters"),("درس‌ها","lessons"),("تیکت‌ها","support_tickets")]:
        cur=await db.execute(f"SELECT COUNT(*) c FROM {t}"); counts[name]=(await cur.fetchone())["c"]
    await db.close()
    await m.answer("👑 پنل مدیریت\n\n👥 کاربران: %s\n📚 فصل‌ها: %s\n🎬 درس‌ها: %s\n💬 تیکت‌ها: %s" % tuple(counts.values()))
