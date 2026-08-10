# نصب
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env
python main.py
```
`BOT_TOKEN` و `OWNER_ID` را در Service Variables قرار بده.

## Telegram UI
این پروژه از آخرین نسخه موجود aiogram در زمان ساخت استفاده می‌کند.
رنگ دکمه‌های Inline و Custom/Premium Emoji باید فقط با قابلیت‌هایی استفاده شوند که نسخه Bot API و کلاینت Telegram واقعاً پشتیبانی می‌کنند؛ ID جعلی ساخته نشده است.
