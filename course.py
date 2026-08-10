from database import connect

async def chapters():
    db=await connect(); cur=await db.execute("SELECT * FROM chapters WHERE is_active=1 ORDER BY position,id")
    r=await cur.fetchall(); await db.close(); return r

async def lessons(cid):
    db=await connect(); cur=await db.execute("SELECT * FROM lessons WHERE chapter_id=? AND is_active=1 ORDER BY position,id",(cid,))
    r=await cur.fetchall(); await db.close(); return r

async def lesson(lid):
    db=await connect(); cur=await db.execute("SELECT * FROM lessons WHERE id=?",(lid,))
    r=await cur.fetchone(); await db.close(); return r

async def can_access(uid,lid):
    db=await connect()
    cur=await db.execute("SELECT chapter_id,position FROM lessons WHERE id=?",(lid,))
    cur_l=await cur.fetchone()
    if not cur_l: await db.close(); return False
    cur=await db.execute("""SELECT id FROM lessons WHERE chapter_id=? AND position<?
      ORDER BY position DESC,id DESC LIMIT 1""",(cur_l["chapter_id"],cur_l["position"]))
    prev=await cur.fetchone()
    if not prev: await db.close(); return True
    cur=await db.execute("SELECT quiz_passed FROM progress p JOIN users u ON u.id=p.user_id WHERE u.telegram_id=? AND p.lesson_id=?",(uid,prev["id"]))
    row=await cur.fetchone(); await db.close()
    return bool(row and row["quiz_passed"])
