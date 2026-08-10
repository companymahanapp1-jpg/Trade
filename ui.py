from aiogram.types import InlineKeyboardMarkup,InlineKeyboardButton
from config import START_EMOJI_ID,SUPPORT_EMOJI_ID,ADMIN_EMOJI_ID
def btn(text,data,style=None,emoji_id=None):
    kw={"text":text,"callback_data":data}
    if style: kw["style"]=style
    if emoji_id: kw["icon_custom_emoji_id"]=emoji_id
    return InlineKeyboardButton(**kw)
def main_inline(admin=False):
    rows=[[btn("🎓 شروع یادگیری","learn","success",START_EMOJI_ID),btn("💬 پشتیبانی","support","primary",SUPPORT_EMOJI_ID)]]
    if admin: rows.append([btn("👑 پنل مدیریت","admin","primary",ADMIN_EMOJI_ID)])
    return InlineKeyboardMarkup(inline_keyboard=rows)
def admin_kb():
    items=[("📚 فصل‌ها","adm:chapters","success"),("🎬 درس‌ها","adm:lessons","success"),("📝 آزمون‌ها","adm:quizzes","primary"),("👥 کاربران","adm:users","primary"),("👑 ادمین‌ها","adm:admins","primary"),("💬 پشتیبانی","adm:tickets","primary"),("📢 جوین اجباری","adm:channels","success"),("📣 پیام همگانی","adm:broadcast","primary"),("📊 آمار","adm:stats","success"),("⚙️ تنظیمات","adm:settings","primary")]
    rows=[]
    for i in range(0,len(items),2):
        rows.append([btn(*items[i])] + ([btn(*items[i+1])] if i+1<len(items) else []))
    rows.append([btn("⬅️ بازگشت","home","danger")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
def back(data):
    return InlineKeyboardMarkup(inline_keyboard=[[btn("⬅️ بازگشت",data,"danger")]])
def chapters_kb(rows):
    return InlineKeyboardMarkup(inline_keyboard=[[btn(f"📚 {r['title']}",f"chapter:{r['id']}","success")] for r in rows]+[[btn("⬅️ بازگشت","home","danger")]])
def lessons_kb(rows,open_ids):
    out=[]
    for r in rows:
        out.append([btn(f"{'🎬' if r['id'] in open_ids else '🔒'} {r['title']}",f"lesson:{r['id']}","success" if r['id'] in open_ids else "danger")])
    out.append([btn("⬅️ بازگشت","learn","danger")])
    return InlineKeyboardMarkup(inline_keyboard=out)
