from aiogram import Router,F
from aiogram.types import Message,CallbackQuery
from database import connect
from config import OWNER_ID
from ui import back
router=Router()
@router.callback_query(F.data=="support")
async def support(c:CallbackQuery):
    x=await connect();cur=await x.execute("SELECT id FROM users WHERE telegram_id=?",(c.from_user.id,));u=await cur.fetchone()
    if not u:await x.close();return await c.answer("ابتدا /start را بزن.",show_alert=True)
    cur=await x.execute("SELECT id FROM tickets WHERE user_id=? AND status='open' LIMIT 1",(u["id"],));t=await cur.fetchone()
    if not t:
        cur=await x.execute("INSERT INTO tickets(user_id) VALUES(?)",(u["id"],));tid=cur.lastrowid;await x.commit()
    else:tid=t["id"]
    await x.close();await c.message.edit_text(f"💬 <b>پشتیبانی</b>\n\nپیامت را در یک پیام جداگانه بفرست.\n🎫 تیکت #{tid}",parse_mode="HTML",reply_markup=back("home"));await c.answer()
@router.message()
async def ticket_message(m:Message):
    if not m.text or m.text.startswith("/"):return
    x=await connect();cur=await x.execute("SELECT id FROM users WHERE telegram_id=?",(m.from_user.id,));u=await cur.fetchone()
    if not u:await x.close();return
    cur=await x.execute("SELECT id FROM tickets WHERE user_id=? AND status='open' ORDER BY id DESC LIMIT 1",(u["id"],));t=await cur.fetchone()
    if not t:await x.close();return
    await x.execute("INSERT INTO ticket_messages(ticket_id,sender_id,text) VALUES(?,?,?)",(t["id"],m.from_user.id,m.text));await x.commit();await x.close()
    try:await m.bot.send_message(OWNER_ID,f"💬 <b>تیکت #{t['id']}</b>\n👤 {m.from_user.full_name}\n\n{m.text}",parse_mode="HTML")
    except Exception:pass
