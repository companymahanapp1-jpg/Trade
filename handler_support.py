from aiogram import Router,F
from aiogram.types import Message
from database import connect
router=Router()

@router.message(F.text=="💬 پشتیبانی")
async def support(m:Message):
    db=await connect()
    cur=await db.execute("SELECT id FROM users WHERE telegram_id=?",(m.from_user.id,)); u=await cur.fetchone()
    if u:
        cur=await db.execute("SELECT id FROM support_tickets WHERE user_id=? AND status='open' LIMIT 1",(u["id"],))
        if not await cur.fetchone():
            await db.execute("INSERT INTO support_tickets(user_id) VALUES(?)",(u["id"],)); await db.commit()
    await db.close()
    await m.answer("💬 پیام خود را ارسال کنید تا برای پشتیبانی ثبت شود.")

@router.message()
async def support_message(m:Message):
    if not m.text or m.text.startswith("/"): return
    db=await connect()
    cur=await db.execute("SELECT id FROM users WHERE telegram_id=?",(m.from_user.id,)); u=await cur.fetchone()
    if u:
        cur=await db.execute("SELECT id FROM support_tickets WHERE user_id=? AND status='open' ORDER BY id DESC LIMIT 1",(u["id"],)); t=await cur.fetchone()
        if t:
            await db.execute("INSERT INTO support_messages(ticket_id,sender_telegram_id,text) VALUES(?,?,?)",(t["id"],m.from_user.id,m.text)); await db.commit()
    await db.close()
