# Trading Course Bot V3 — Fixed / Railway

نسخه اصلاح‌شده بر پایه همان پروژه V3 ارسالی است؛ دیتابیس SQLite و Premium Custom Emoji حفظ شده‌اند.

## مهم
- Python 3.12+
- aiogram 3.30.0
- Reply Keyboard برای منوها
- بدون InlineKeyboardMarkup / CallbackQuery
- متن واقعی سه دکمه اصلی:
  - `شروع یادگیری`
  - `پشتیبانی`
  - `پنل مدیریت`
- Premium Custom Emoji فقط با `icon_custom_emoji_id` و جدا از متن دکمه ارسال می‌شود.
- `KeyboardButton.style` با `primary/success/danger` استفاده شده است.

## Railway Deploy

Service Variables:
- `BOT_TOKEN` = توکن BotFather
- `OWNER_ID` = Telegram numeric ID مالک
- `START_EMOJI_ID` = 5935946026308342844
- `SUPPORT_EMOJI_ID` = 5938359183748370657
- `ADMIN_EMOJI_ID` = 5935933089866846598
- اختیاری: `DB_PATH=data/bot.db`

Start Command:
```bash
python main.py
```

Procfile نیز `worker: python main.py` دارد.

### SQLite روی Railway
برای حفظ SQLite بعد از restart/redeploy یک Railway Volume متصل به پروژه بسازید و `DB_PATH` را روی مسیر volume قرار دهید، مثلاً:
```text
/mnt/data/bot.db
```

## اجرای محلی
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python main.py
```

## نکات Forced Join
ربات باید در کانال‌های اجباری دسترسی لازم برای `getChatMember` داشته باشد. افزودن کانال از پنل با `@channel` انجام می‌شود.

## تست فنی انجام‌شده
- Syntax compile روی `main.py`
- بررسی نبود `InlineKeyboardMarkup` و `CallbackQuery`
- بررسی duplicate decoratorهای exact در `main.py`
- حفظ schema و migration غیرمخرب برای دیتابیس V3
