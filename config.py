import os
from dotenv import load_dotenv
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))
DEFAULT_COOLDOWN = int(os.getenv("DEFAULT_COOLDOWN", "600"))
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not configured")
