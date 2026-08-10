from database import connect
async def chapters():
    x=await connect(); c=await x.execute("SELECT * FROM chapters WHERE active=1 ORDER BY position,id"); r=await c.fetchall(); await x.close(); return r
async def lessons(cid):
    x=await connect(); c=await x.execute("SELECT * FROM lessons WHERE chapter_id=? AND active=1 ORDER BY position,id",(cid,)); r=await c.fetchall(); await x.close(); return r
async def lesson(lid):
    x=await connect(); c=await x.execute("SELECT * FROM lessons WHERE id=?",(lid,)); r=await c.fetchone(); await x.close(); return r
async def can_open(uid,lid):
    x=await connect(); c=await x.execute("SELECT chapter_id,position FROM lessons WHERE id=?",(lid,)); cur=await c.fetchone()
    if not cur: await x.close(); return False
    c=await x.execute("SELECT id FROM lessons WHERE chapter_id=? AND position<? ORDER BY position DESC LIMIT 1",(cur["chapter_id"],cur["position"])); p=await c.fetchone()
    if not p: await x.close(); return True
    c=await x.execute("SELECT quiz_passed FROM progress p JOIN users u ON u.id=p.user_id WHERE u.telegram_id=? AND p.lesson_id=?",(uid,p["id"])); r=await c.fetchone(); await x.close()
    return bool(r and r["quiz_passed"])
