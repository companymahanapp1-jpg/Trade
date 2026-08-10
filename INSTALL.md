# نصب روی Ubuntu 24 / Rivaly VPS

```bash
sudo apt update
sudo apt install -y python3 python3-venv unzip
unzip trading_course_bot_flat.zip
cd trading_course_bot_flat
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env
python main.py
```

در `.env` مقدار `BOT_TOKEN` و `OWNER_ID` را وارد کن.

## GitHub
همه فایل‌ها مستقیماً در Root ریپو قرار می‌گیرند و نیازی به ساخت پوشه‌های تو در تو نیست.

## اجرای دائمی
بعد از تست اولیه می‌توانی با systemd سرویس را دائمی کنی.
