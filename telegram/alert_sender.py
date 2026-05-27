import os

import requests
from dotenv import load_dotenv

from utils.http_retry import request_with_retry
from utils.logger import logger

load_dotenv()

TELEGRAM_MAX_MESSAGE_LENGTH = 4096
# Запас под заголовок части «(99/99)» + переносы
TELEGRAM_SAFE_CHUNK_LENGTH = 3850

# Разделитель между блоками одной цели в find_broken_goals
GOAL_BLOCK_DELIMITER = "\n\n" + ("—" * 30) + "\n\n"
PART_HEADER_SUFFIX = "\n\n\n"


def is_telegram_enabled() -> bool:
    """
    True, если заданы TELEGRAM_TOKEN и TELEGRAM_CHAT_ID
    и TELEGRAM_ENABLED не отключён явно (false / 0 / no).
    """
    flag = os.getenv("TELEGRAM_ENABLED", "true").strip().lower()
    if flag in ("0", "false", "no"):
        return False
    return bool(os.getenv("TELEGRAM_TOKEN") and os.getenv("TELEGRAM_CHAT_ID"))


def _get_telegram_config():
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        raise ValueError(
            "Для отправки в Telegram нужны TELEGRAM_TOKEN и TELEGRAM_CHAT_ID в .env"
        )
    return token, chat_id


def _strip_leading_goal_delimiter(text: str) -> str:
    """Убирает разделитель в начале части (между Telegram-сообщениями он не нужен)."""
    if text.startswith(GOAL_BLOCK_DELIMITER):
        return text[len(GOAL_BLOCK_DELIMITER) :]
    return text


def _atomic_blocks(text: str) -> list[str]:
    """
    Разбивает текст на неделимые блоки: заголовок + первая цель, затем каждая цель целиком.
    Если разделителя нет — весь текст один блок.
    """
    if GOAL_BLOCK_DELIMITER not in text:
        return [text]

    segments = text.split(GOAL_BLOCK_DELIMITER)
    blocks = [segments[0]]
    for segment in segments[1:]:
        if segment:
            blocks.append(GOAL_BLOCK_DELIMITER + segment)
    return blocks


def _split_block_by_lines(block: str, max_length: int) -> list[str]:
    """Запасной вариант: один блок цели длиннее лимита — режем только по строкам."""
    if len(block) <= max_length:
        return [block]

    logger.warning(
        f"Блок уведомления ({len(block)} симв.) длиннее лимита Telegram — "
        "разбиение по строкам (редкий случай)"
    )
    parts = []
    remaining = block
    while remaining:
        if len(remaining) <= max_length:
            parts.append(remaining)
            break
        split_at = remaining.rfind("\n", 0, max_length)
        if split_at <= 0:
            split_at = max_length
        parts.append(remaining[:split_at].rstrip())
        remaining = remaining[split_at:].lstrip("\n")
    return parts


def _pack_atomic_blocks(blocks: list[str], max_length: int) -> list[str]:
    """Собирает части сообщения, не разрывая блоки целей между частями."""
    packed = []
    current = ""

    for block in blocks:
        if len(block) > max_length:
            if current:
                packed.append(current)
                current = ""
            packed.extend(_split_block_by_lines(block, max_length))
            continue

        if not current:
            current = block
            continue

        candidate = current + block
        if len(candidate) <= max_length:
            current = candidate
        else:
            packed.append(current)
            current = block

    if current:
        packed.append(current)

    if len(packed) > 1:
        packed = [packed[0]] + [_strip_leading_goal_delimiter(part) for part in packed[1:]]

    return packed


def split_message(text: str, max_length: int = TELEGRAM_SAFE_CHUNK_LENGTH) -> list[str]:
    """
    Делит длинный текст на части для Telegram.
    Блоки одной цели (между разделителем «———») не разрываются — переносятся целиком.
    """
    if len(text) <= max_length:
        return [text]

    parts = _pack_atomic_blocks(_atomic_blocks(text), max_length)
    total = len(parts)
    if total == 1:
        return parts

    return [f"({i + 1}/{total}){PART_HEADER_SUFFIX}{part}" for i, part in enumerate(parts)]


def send_telegram_message(text: str) -> None:
    """
    Отправляет сообщение в Telegram (с разбиением при длине > 4096).

    Raises:
        ValueError: если не установлены переменные окружения
        RuntimeError: если произошла ошибка при отправке
    """
    token, chat_id = _get_telegram_config()
    url = f"https://api.telegram.org/bot{token}/sendMessage"

    for chunk in split_message(text):
        if len(chunk) > TELEGRAM_MAX_MESSAGE_LENGTH:
            logger.warning(
                f"Часть сообщения {len(chunk)} символов — обрезаем до {TELEGRAM_MAX_MESSAGE_LENGTH}"
            )
            chunk = chunk[:TELEGRAM_MAX_MESSAGE_LENGTH]

        params = {"chat_id": chat_id, "text": chunk}
        try:
            response = request_with_retry("POST", url, json=params, timeout=10)
            logger.info("Уведомление в Telegram отправлено успешно")
        except requests.exceptions.RequestException as exc:
            logger.error(f"Ошибка при отправке уведомления в Telegram: {exc}")
            raise RuntimeError(f"Ошибка при отправке сообщения в Telegram: {exc}") from exc


def notify_console(text: str) -> None:
    """Вывод текста в консоль (мониторинг целей)."""
    print(text)


def notify_monitoring(text: str) -> None:
    """Консоль всегда; Telegram — если TELEGRAM_ENABLED=true."""
    notify_console(text)
    if is_telegram_enabled():
        send_telegram_message(text)


def send_pipeline_error_alert(stage: str, error_message: str, traceback_text: str) -> None:
    """
    Алерт об ошибке пайплайна: всегда в лог и консоль;
    в Telegram — если включён TELEGRAM_ENABLED.
    """
    short_text = (
        "⚠️ Ошибка ym_goals_monitoring\n"
        f"Этап: {stage}\n"
        f"Ошибка: {error_message}"
    )
    full_text = f"{short_text}\n\n{traceback_text}"

    logger.error(full_text)
    notify_console(short_text)
    if len(traceback_text) > 500:
        notify_console(f"(полный traceback в logs/project.log)\n{traceback_text[:2000]}...")

    if is_telegram_enabled():
        try:
            send_telegram_message(short_text)
        except Exception as exc:
            logger.error(f"Не удалось отправить алерт об ошибке в Telegram: {exc}")
