"""Telegram expense-tracking bot for two housemates."""

import datetime
import logging

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

import config
from db import (
    init_db,
    add_expense,
    delete_last_expense,
    get_recent_expenses,
    clear_all,
)
from balance import compute_balance, format_balance
from parser import parse_expense
from voice import transcribe

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

ALLOWED = {config.USER1_ID, config.USER2_ID}

_MODE_LABEL = {
    "shared": "50/50",
    "for_other": "за другого",
    "personal": "личные %",
}

_RU_MONTHS = ["янв","фев","мар","апр","май","июн","июл","авг","сен","окт","ноя","дек"]

def _fmt_date(iso: str | None) -> str:
    """Format ISO date as '5 апр' or 'сегодня'."""
    today = datetime.date.today()
    if not iso:
        return "сегодня"
    try:
        d = datetime.date.fromisoformat(iso)
    except ValueError:
        return "сегодня"
    if d == today:
        return "сегодня"
    if d == today - datetime.timedelta(days=1):
        return "вчера"
    return f"{d.day} {_RU_MONTHS[d.month - 1]}"


def _is_allowed(update: Update) -> bool:
    return update.effective_user is not None and update.effective_user.id in ALLOWED


async def _notify(context: ContextTypes.DEFAULT_TYPE, chat_id: int, text: str) -> None:
    """Send text to NOTIFY_CHAT_ID if configured and different from current chat."""
    if config.NOTIFY_CHAT_ID and config.NOTIFY_CHAT_ID != chat_id:
        await context.bot.send_message(config.NOTIFY_CHAT_ID, text)


# ── /start ─────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update):
        return
    await update.message.reply_text(  # type: ignore[union-attr]
        "👋 Привет! Я бот для учёта совместных расходов.\n\n"
        "Просто напиши (или отправь голосовое) о трате, например:\n"
        "• <i>потратил 600 бат в магазине</i>\n"
        "• <i>Маша купила продукты на 500</i>\n"
        "• <i>купил за Машу лекарства на 300</i>\n"
        "• <i>купил на 1000 бат, 70% мои личные</i>\n\n"
        "Команды:\n"
        "/balance — текущий баланс\n"
        "/history — последние 10 расходов\n"
        "/undo — отменить последний расход\n"
        "/clear — обнулить всё (требует подтверждения)",
        parse_mode="HTML",
    )


# ── /balance ───────────────────────────────────────────────────────────────

async def cmd_balance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update):
        return
    net = compute_balance()
    await update.message.reply_text(format_balance(net))  # type: ignore[union-attr]


# ── /history ───────────────────────────────────────────────────────────────

async def cmd_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update):
        return
    rows = get_recent_expenses(10)
    if not rows:
        await update.message.reply_text("История пуста.")  # type: ignore[union-attr]
        return

    lines = ["<b>Последние расходы:</b>"]
    for row in reversed(rows):
        payer = config.user_name(row["payer_id"])
        mode_label = _MODE_LABEL.get(row["mode"], row["mode"])
        extra = f" ({row['personal_pct']:.0f}% личные)" if row["mode"] == "personal" else ""
        date_label = _fmt_date(row["purchase_date"])
        lines.append(
            f"• <i>{date_label}</i> {payer} — {row['description']}: {row['amount']:.2f} ฿"
            f"  [{mode_label}{extra}]"
        )

    lines.append("")
    lines.append(format_balance(compute_balance()))
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")  # type: ignore[union-attr]


# ── /undo ──────────────────────────────────────────────────────────────────

async def cmd_undo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update):
        return
    row = delete_last_expense()
    if not row:
        await update.message.reply_text("Нет расходов для отмены.")  # type: ignore[union-attr]
        return

    payer = config.user_name(row["payer_id"])
    net = compute_balance()
    text = (
        f"↩️ Отменено: {payer} — {row['description']}: {row['amount']:.2f} ฿\n"
        f"{format_balance(net)}"
    )
    await update.message.reply_text(text)  # type: ignore[union-attr]
    await _notify(context, update.effective_chat.id, text)  # type: ignore[union-attr]


# ── /clear ─────────────────────────────────────────────────────────────────

_pending_clear: set[int] = set()


async def cmd_clear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update):
        return
    user_id = update.effective_user.id  # type: ignore[union-attr]
    if user_id not in _pending_clear:
        _pending_clear.add(user_id)
        await update.message.reply_text(  # type: ignore[union-attr]
            "⚠️ Это удалит ВСЕ расходы. Отправь /clear ещё раз для подтверждения."
        )
    else:
        _pending_clear.discard(user_id)
        count = clear_all()
        text = f"🗑 Удалено {count} записей. Баланс обнулён."
        await update.message.reply_text(text)  # type: ignore[union-attr]
        await _notify(context, update.effective_chat.id, text)  # type: ignore[union-attr]


# ── message handler ────────────────────────────────────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update):
        return

    user_id = update.effective_user.id  # type: ignore[union-attr]
    message = update.message  # type: ignore[union-attr]

    # Clear the pending-clear state on any non-/clear message
    _pending_clear.discard(user_id)

    text: str | None = message.text or message.caption

    # Voice message → transcribe
    if message.voice:
        if not config.OPENAI_API_KEY:
            await message.reply_text(
                "🎤 Голосовые сообщения не поддерживаются — задайте OPENAI_API_KEY."
            )
            return
        await message.reply_text("🎤 Распознаю голосовое…")
        voice_file = await message.voice.get_file()
        file_bytes = await voice_file.download_as_bytearray()
        text = await transcribe(bytes(file_bytes))
        if not text:
            await message.reply_text("❌ Не удалось распознать голосовое сообщение.")
            return
        await message.reply_text(f"📝 Распознано: <i>{text}</i>", parse_mode="HTML")

    if not text:
        return

    result = await _run_parser(text, user_id)
    if result is None:
        # Claude says it's not an expense — silently ignore (don't spam)
        return

    # Determine actual payer ID
    if result["actual_payer"] == "other":
        payer_id = config.other_user_id(user_id)
    else:
        payer_id = user_id

    purchase_date = result.get("purchase_date")  # None = today
    add_expense(
        payer_id=payer_id,
        amount=result["amount"],
        description=result["description"],
        mode=result["mode"],
        personal_pct=result.get("personal_pct", 0.0),
        purchase_date=purchase_date,
    )

    net = compute_balance()
    payer_name = config.user_name(payer_id)
    mode_label = _MODE_LABEL.get(result["mode"], result["mode"])
    extra = (
        f" ({result['personal_pct']:.0f}% личные)"
        if result["mode"] == "personal"
        else ""
    )
    date_label = _fmt_date(purchase_date)

    response = (
        f"✅ Записано [{mode_label}{extra}] {date_label}\n"
        f"   {payer_name}: {result['description']} — {result['amount']:.2f} ฿\n\n"
        f"{format_balance(net)}"
    )

    await message.reply_text(response)
    await _notify(context, update.effective_chat.id, response)


async def _run_parser(text: str, sender_id: int):
    """Wrapper so parse_expense (sync) runs safely in async context."""
    import asyncio

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, parse_expense, text, sender_id)


# ── main ───────────────────────────────────────────────────────────────────

def main() -> None:
    init_db()
    logger.info("Database initialised.")

    app = Application.builder().token(config.TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_start))
    app.add_handler(CommandHandler("balance", cmd_balance))
    app.add_handler(CommandHandler("history", cmd_history))
    app.add_handler(CommandHandler("undo", cmd_undo))
    app.add_handler(CommandHandler("clear", cmd_clear))

    app.add_handler(
        MessageHandler(filters.TEXT | filters.VOICE | filters.CAPTION, handle_message)
    )

    logger.info(
        "Bot started. Listening for users: %s (%d) and %s (%d)",
        config.USER1_NAME, config.USER1_ID,
        config.USER2_NAME, config.USER2_ID,
    )
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
