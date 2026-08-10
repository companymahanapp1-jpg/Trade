# Trading Course Bot — GOD
نسخه بدون Inline Keyboard؛ همه رابط کاربری با Reply Keyboard است.

این نسخه از قابلیت رسمی جدید Telegram برای `KeyboardButton.style` و `icon_custom_emoji_id` استفاده می‌کند. Bot API 9.4 این دو فیلد را برای KeyboardButton اضافه کرده است.

رنگ‌ها:
- `primary` آبی
- `success` سبز
- `danger` قرمز

برای Custom/Premium Emoji باید ID واقعی Custom Emoji را در Service Variables قرار دهید:
`START_EMOJI_ID`
`SUPPORT_EMOJI_ID`
`ADMIN_EMOJI_ID`

نصب:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python main.py
```

Service Variables:
- BOT_TOKEN
- OWNER_ID
- START_EMOJI_ID (اختیاری)
- SUPPORT_EMOJI_ID (اختیاری)
- ADMIN_EMOJI_ID (اختیاری)

ربات باید در کانال‌های Join اجباری دسترسی لازم برای بررسی اعضا داشته باشد.
