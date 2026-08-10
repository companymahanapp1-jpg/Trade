import aiosqlite
from pathlib import Path
DB_PATH = Path("data/bot.db")

async def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA foreign_keys=ON")
    return db

async def init_db():
    db = await connect()
    await db.executescript("""
    CREATE TABLE IF NOT EXISTS users(
      id INTEGER PRIMARY KEY AUTOINCREMENT, telegram_id INTEGER UNIQUE NOT NULL,
      username TEXT, first_name TEXT, is_blocked INTEGER DEFAULT 0,
      created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS admins(
      telegram_id INTEGER PRIMARY KEY, role TEXT DEFAULT 'admin', created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS chapters(
      id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, description TEXT DEFAULT '',
      position INTEGER DEFAULT 0, is_active INTEGER DEFAULT 1);
    CREATE TABLE IF NOT EXISTS lessons(
      id INTEGER PRIMARY KEY AUTOINCREMENT, chapter_id INTEGER NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
      title TEXT NOT NULL, description TEXT DEFAULT '', position INTEGER DEFAULT 0,
      video_file_id TEXT, duration_seconds INTEGER DEFAULT 0, is_active INTEGER DEFAULT 1);
    CREATE TABLE IF NOT EXISTS quizzes(
      id INTEGER PRIMARY KEY AUTOINCREMENT, lesson_id INTEGER UNIQUE NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
      pass_score INTEGER DEFAULT 70, time_limit_seconds INTEGER DEFAULT 300,
      cooldown_seconds INTEGER DEFAULT 600, max_attempts INTEGER DEFAULT 0);
    CREATE TABLE IF NOT EXISTS questions(
      id INTEGER PRIMARY KEY AUTOINCREMENT, quiz_id INTEGER NOT NULL REFERENCES quizzes(id) ON DELETE CASCADE,
      question TEXT NOT NULL, position INTEGER DEFAULT 0, points INTEGER DEFAULT 1);
    CREATE TABLE IF NOT EXISTS options(
      id INTEGER PRIMARY KEY AUTOINCREMENT, question_id INTEGER NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
      text TEXT NOT NULL, is_correct INTEGER DEFAULT 0);
    CREATE TABLE IF NOT EXISTS progress(
      user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      lesson_id INTEGER NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
      video_completed INTEGER DEFAULT 0, quiz_passed INTEGER DEFAULT 0, completed_at TEXT,
      PRIMARY KEY(user_id, lesson_id));
    CREATE TABLE IF NOT EXISTS attempts(
      id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      quiz_id INTEGER NOT NULL REFERENCES quizzes(id) ON DELETE CASCADE, score INTEGER DEFAULT 0,
      passed INTEGER DEFAULT 0, started_at TEXT NOT NULL, finished_at TEXT, retry_after TEXT);
    CREATE TABLE IF NOT EXISTS required_channels(
      id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, chat_id TEXT NOT NULL,
      invite_link TEXT NOT NULL, is_active INTEGER DEFAULT 1);
    CREATE TABLE IF NOT EXISTS support_tickets(
      id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      status TEXT DEFAULT 'open', created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS support_messages(
      id INTEGER PRIMARY KEY AUTOINCREMENT, ticket_id INTEGER NOT NULL REFERENCES support_tickets(id) ON DELETE CASCADE,
      sender_telegram_id INTEGER NOT NULL, text TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS admin_logs(
      id INTEGER PRIMARY KEY AUTOINCREMENT, admin_id INTEGER NOT NULL, action TEXT NOT NULL,
      created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    """)
    await db.commit()
    await db.close()
