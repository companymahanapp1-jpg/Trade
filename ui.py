from aiogram.types import ReplyKeyboardMarkup,KeyboardButton,InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
def main_keyboard(admin=False):
    rows=[[KeyboardButton(text="🎓 شروع یادگیری"),KeyboardButton(text="💬 پشتیبانی")]]
    if admin: rows.append([KeyboardButton(text="👑 پنل مدیریت")])
    return ReplyKeyboardMarkup(keyboard=rows,resize_keyboard=True,is_persistent=True)
def admin_keyboard():
    b=InlineKeyboardBuilder()
    for t,c in [("📚 فصل‌ها","a:chapters"),("🎬 درس‌ها","a:lessons"),("📝 آزمون‌ها","a:quizzes"),("👥 کاربران","a:users"),("👑 ادمین‌ها","a:admins"),("💬 پشتیبانی","a:tickets"),("📢 جوین اجباری","a:channels"),("📣 پیام همگانی","a:broadcast"),("📊 آمار","a:stats")]:
        b.add(InlineKeyboardButton(text=t,callback_data=c))
    b.add(InlineKeyboardButton(text="⬅️ بازگشت",callback_data="a:back")); b.adjust(2); return b.as_markup()
def chapters_kb(rows):
    b=InlineKeyboardBuilder()
    for r in rows:b.add(InlineKeyboardButton(text=f"📚 {r['title']}",callback_data=f"c:{r['id']}"))
    b.add(InlineKeyboardButton(text="⬅️ بازگشت",callback_data="a:back")); b.adjust(1); return b.as_markup()
def lessons_kb(rows,open_ids):
    b=InlineKeyboardBuilder()
    for r in rows:
        b.add(InlineKeyboardButton(text=f"{'🎬' if r['id'] in open_ids else '🔒'} {r['title']}",callback_data=f"l:{r['id']}"))
    b.add(InlineKeyboardButton(text="⬅️ بازگشت",callback_data="back:c")); b.adjust(1); return b.as_markup()
