from config import OWNER_ID
from database import connect

async def ensure_user(u):
    db = await connect()
    await db.execute("""INSERT INTO users(telegram_id,username,first_name) VALUES(?,?,?)
    ON CONFLICT(telegram_id) DO UPDATE SET username=excluded.username, first_name=excluded.first_name,
    updated_at=CURRENT_TIMESTAMP""", (u.id,u.username,u.first_name))
    await db.commit(); await db.close()

async def is_admin(uid):
    if uid == OWNER_ID: return True
    db = await connect()
    cur = await db.execute("SELECT 1 FROM admins WHERE telegram_id=?", (uid,))
    row = await cur.fetchone(); await db.close()
    return row is not None
