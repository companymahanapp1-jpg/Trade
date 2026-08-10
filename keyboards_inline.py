from aiogram.utils.keyboard import InlineKeyboardBuilder

def chapters_kb(rows):
    b=InlineKeyboardBuilder()
    for x in rows: b.button(text=f"📚 {x['title']}", callback_data=f"chapter:{x['id']}")
    b.button(text="⬅️ بازگشت", callback_data="back:main"); b.adjust(1)
    return b.as_markup()

def lessons_kb(rows, unlocked):
    b=InlineKeyboardBuilder()
    for x in rows:
        icon="🎬" if x["id"] in unlocked else "🔒"
        b.button(text=f"{icon} {x['title']}", callback_data=f"lesson:{x['id']}")
    b.button(text="⬅️ بازگشت", callback_data="back:chapters"); b.adjust(1)
    return b.as_markup()
