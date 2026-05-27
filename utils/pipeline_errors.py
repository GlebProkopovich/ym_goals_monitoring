"""Обработка ошибок пайплайна и уведомления."""

import traceback

from telegram.alert_sender import send_pipeline_error_alert
from utils.logger import logger


def send_pipeline_error(stage: str, error: Exception) -> None:
    """Логирует ошибку и отправляет алерт (Telegram при включённой отправке)."""
    tb = traceback.format_exc()
    message = (
        f"Ошибка пайплайна на этапе: {stage}\n"
        f"Тип: {type(error).__name__}\n"
        f"Сообщение: {error}\n\n"
        f"Traceback:\n{tb}"
    )
    logger.error(message)
    send_pipeline_error_alert(stage, str(error), tb)


def run_stage(stage: str, fn):
    """Выполняет этап пайплайна; при ошибке шлёт алерт и пробрасывает исключение."""
    try:
        logger.info(f"Этап: {stage}")
        return fn()
    except Exception as exc:
        send_pipeline_error(stage, exc)
        raise
