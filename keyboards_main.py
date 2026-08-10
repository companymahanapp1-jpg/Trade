from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
def main_keyboard(is_admin=False):
    rows = [[KeyboardButton(text="🎓 شروع یادگیری"), KeyboardButton(text="💬 پشتیبانی")]]
    if is_admin: rows.append([KeyboardButton(text="👑 پنل مدیریت")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, is_persistent=True)
