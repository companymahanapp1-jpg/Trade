import os
from dotenv import load_dotenv
load_dotenv()
BOT_TOKEN=os.getenv("BOT_TOKEN","")
OWNER_ID=int(os.getenv("OWNER_ID","0"))
START_EMOJI_ID=os.getenv("START_EMOJI_ID","")
SUPPORT_EMOJI_ID=os.getenv("SUPPORT_EMOJI_ID","")
ADMIN_EMOJI_ID=os.getenv("ADMIN_EMOJI_ID","")
if not BOT_TOKEN: raise RuntimeError("BOT_TOKEN is missing")
