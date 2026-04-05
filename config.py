import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN: str = os.environ["TELEGRAM_TOKEN"]
ANTHROPIC_API_KEY: str = os.environ["ANTHROPIC_API_KEY"]
OPENAI_API_KEY: str | None = os.getenv("OPENAI_API_KEY")

USER1_ID: int = int(os.environ["USER1_ID"])
USER2_ID: int = int(os.environ["USER2_ID"])
USER1_NAME: str = os.getenv("USER1_NAME", "Пользователь 1")
USER2_NAME: str = os.getenv("USER2_NAME", "Пользователь 2")

_notify = os.getenv("NOTIFY_CHAT_ID", "").strip()
NOTIFY_CHAT_ID: int | None = int(_notify) if _notify else None

DB_PATH: str = os.getenv("DB_PATH", "expenses.db")


def other_user_id(user_id: int) -> int:
    return USER2_ID if user_id == USER1_ID else USER1_ID


def user_name(user_id: int) -> str:
    return USER1_NAME if user_id == USER1_ID else USER2_NAME
