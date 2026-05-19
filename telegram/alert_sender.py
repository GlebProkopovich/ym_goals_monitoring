import os
import requests
from dotenv import load_dotenv
from utils.logger import logger


# Загрузка переменных из файла .env
load_dotenv()

# Получение и проверка переменных
TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TOKEN:
    logger.error("TELEGRAM_TOKEN не был получен из env-файла")
    raise ValueError("TELEGRAM_TOKEN не был получен из env-файла")

CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
if not CHAT_ID:
    logger.error("TELEGRAM_CHAT_ID не был получен из env-файла")
    raise ValueError("TELEGRAM_CHAT_ID не был получен из env-файла")


def send_telegram_message(text):
    """
    Отправляет сообщение в Telegram чат.

    Args:
        text: Текст сообщения для отправки

    Raises:
        ValueError: Если не установлены переменные окружения
        RuntimeError: Если произошла ошибка при отправке сообщения
    """
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    params = {
        "chat_id": CHAT_ID,
        "text": text,
    }

    try:
        response = requests.post(url, json=params, timeout=10)
        response.raise_for_status()  # Вызовет исключение для 4XX/5XX статусов
        logger.info("Уведомление в Telegram отправлено успешно")
    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка при отправке уведомления в Telegram: {e}")
        raise RuntimeError(f"Ошибка при отправке сообщения в Telegram: {e}")