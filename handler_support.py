from aiogram import Router,F
from aiogram.types import Message
from database import connect
router=Router()
@router.message(F.text=="💬 پشتیبانی")
async def support(m:Message):
    x=await connect(); c=await x.execute("SELECT id FROM users WHERE telegram_id=?",(m.from_user.id,));u=await c.fetchone()
    if u:
        c=await x.execute("SELECT id FROM tickets WHERE user_id=? AND status='open' LIMIT 1",(u["id"],))
        if not await c.fetchone():await x.execute("INSERT INTO tickets(user_id) VALUES(?)",(u["id"],));await x.commit()
    await x.close();await m.answer("💬 <b>پشتیبانی</b>\n\nپیامت را ارسال کن.",parse_mode="HTML")
@router.message()
async def capture(m:Message):
    if not m.text or m.text.startswith("/"):return
    x=await connect();c=await x.execute("SELECT id FROM users WHERE telegram_id=?",(m.from_user.id,));u=await c.fetchone()
    if u:
        c=await x.execute("SELECT id FROM tickets WHERE user_id=? AND status='open' ORDER BY id DESC LIMIT 1",(u["id"],));t=await c.fetchone()
        if t:await x.execute("INSERT INTO ticket_messages(ticket_id,sender_id,text) VALUES(?,?,?)",(t["id"],m.from_user.id,m.text));await x.commit()
    await x.close()
