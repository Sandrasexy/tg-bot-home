"""Natural-language expense parser powered by Claude."""

import json
import logging
import re
from typing import Any

import anthropic

from config import ANTHROPIC_API_KEY, USER1_NAME, USER2_NAME

logger = logging.getLogger(__name__)

_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

_SYSTEM = """\
Ты — парсер расходов для совместного учёта трат двух человек, живущих вместе.
Тебе приходит сообщение от одного из них. Нужно извлечь информацию о расходе и вернуть JSON.

Поля JSON:
{
  "amount": <число — сумма в местной валюте>,
  "description": "<краткое описание расхода по-русски>",
  "actual_payer": "sender" | "other",
  "mode": "shared" | "for_other" | "personal",
  "personal_pct": <число 0-100, только если mode="personal">,
  "purchase_date": "<дата в формате YYYY-MM-DD или null если не упомянута>"
}

Правила:
- actual_payer="sender"  — если платил тот, кто пишет сообщение
- actual_payer="other"   — если платил второй человек (отправитель просто записывает)
- mode="shared"    — расход делится 50/50 (по умолчанию)
- mode="for_other" — отправитель заплатил ЗА другого (другой должен всю сумму)
- mode="personal"  — personal_pct% это личные расходы отправителя, остаток делим 50/50
  Пример: "70% мои" → personal_pct=70, другой должен: сумма * 30/200
- purchase_date: дата покупки. Сегодня — {today}. Примеры:
  "вчера" → вчерашняя дата, "3 апреля" → {year}-04-03, "позавчера" → 2 дня назад.
  Если дата не упомянута — верни null (бот подставит сегодня).
- Если сообщение НЕ описывает расход, верни: {"error": "not_an_expense"}

Примеры:
- "потратил 600 бат в магазине"
  → {"amount":600,"description":"магазин","actual_payer":"sender","mode":"shared","personal_pct":0,"purchase_date":null}
- "вчера заехал в 7/11, потратил 700 бат"
  → {"amount":700,"description":"7/11","actual_payer":"sender","mode":"shared","personal_pct":0,"purchase_date":"<вчера>"}
- "{other} купила продукты на 500"
  → {"amount":500,"description":"продукты","actual_payer":"other","mode":"shared","personal_pct":0,"purchase_date":null}
- "купил за {other} лекарства на 300"
  → {"amount":300,"description":"лекарства","actual_payer":"sender","mode":"for_other","personal_pct":0,"purchase_date":null}
- "купил на 1000 бат, 70% мои личные"
  → {"amount":1000,"description":"покупка","actual_payer":"sender","mode":"personal","personal_pct":70,"purchase_date":null}
- "3 апреля купил продукты на 400"
  → {"amount":400,"description":"продукты","actual_payer":"sender","mode":"shared","personal_pct":0,"purchase_date":"{year}-04-03"}

Верни ТОЛЬКО JSON без дополнительного текста.\
"""


def _build_system(sender_name: str, other_name: str) -> str:
    import datetime
    today = datetime.date.today()
    return (
        _SYSTEM
        .replace("{other}", other_name)
        .replace("{sender}", sender_name)
        .replace("{today}", today.isoformat())
        .replace("{year}", str(today.year))
    )


def parse_expense(
    text: str,
    sender_id: int,
) -> dict[str, Any] | None:
    """Parse expense from message text.

    Returns a dict with keys: amount, description, actual_payer, mode, personal_pct
    or None if the message is not an expense.
    """
    from config import USER1_ID, user_name, other_user_id

    sender_name = user_name(sender_id)
    other_name = user_name(other_user_id(sender_id))

    system = _build_system(sender_name, other_name)
    user_prompt = f"Сообщение от {sender_name}: \"{text}\""

    try:
        msg = _client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=256,
            system=system,
            messages=[{"role": "user", "content": user_prompt}],
        )
        raw = msg.content[0].text.strip()
        # Strip potential markdown code fences
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
        data = json.loads(raw)
    except Exception as e:
        logger.error("Parser error: %s", e)
        return None

    if data.get("error") == "not_an_expense":
        return None

    # Validate required fields
    if "amount" not in data or data["amount"] <= 0:
        return None

    data.setdefault("description", "расход")
    data.setdefault("actual_payer", "sender")
    data.setdefault("mode", "shared")
    data.setdefault("personal_pct", 0.0)
    # null means today — leave as None so add_expense uses today
    if data.get("purchase_date") in (None, "null", ""):
        data["purchase_date"] = None

    return data
