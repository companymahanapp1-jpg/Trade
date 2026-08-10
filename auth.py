from config import OWNER_ID
from database import connect
async def ensure_user(u):
    x=await connect()
    await x.execute('''INSERT INTO users(telegram_id,username,first_name) VALUES(?,?,?)
    ON CONFLICT(telegram_id) DO UPDATE SET username=excluded.username,first_name=excluded.first_name''',(u.id,u.username,u.first_name))
    await x.commit(); await x.close()
async def is_admin(uid):
    if uid==OWNER_ID:return True
    x=await connect(); c=await x.execute("SELECT 1 FROM admins WHERE telegram_id=?",(uid,)); r=await c.fetchone(); await x.close()
    return bool(r)
