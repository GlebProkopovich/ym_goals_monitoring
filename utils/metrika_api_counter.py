"""
Суточный счётчик HTTP-запросов к API Яндекс.Метрики.

Состояние хранится в logs/metrika_api_daily.json и сбрасывается при смене календарной даты
(локальное время сервера, где запускается скрипт).
"""

import json
import os
from datetime import date

from utils.logger import logger

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(BASE_DIR, "logs")
COUNTER_FILE = os.path.join(LOG_DIR, "metrika_api_daily.json")

METRIKA_API_HOST = "api-metrika.yandex.net"


def is_metrika_api_url(url: str) -> bool:
    return METRIKA_API_HOST in str(url)


def _today_str() -> str:
    return date.today().isoformat()


def _load_state() -> dict:
    os.makedirs(LOG_DIR, exist_ok=True)
    if not os.path.exists(COUNTER_FILE):
        return {"date": _today_str(), "count": 0}

    try:
        with open(COUNTER_FILE, encoding="utf-8") as f:
            state = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning(f"Не удалось прочитать {COUNTER_FILE}: {exc}. Счётчик обнулён.")
        return {"date": _today_str(), "count": 0}

    if state.get("date") != _today_str():
        return {"date": _today_str(), "count": 0}
    return {"date": state["date"], "count": int(state.get("count", 0))}


def _save_state(state: dict) -> None:
    with open(COUNTER_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)


def get_metrika_api_requests_today() -> int:
    """Текущее число запросов к API Метрики за сегодня."""
    return _load_state()["count"]


def increment_metrika_api_request() -> int:
    """
    Увеличивает суточный счётчик на 1 (один фактический HTTP-запрос).

    Returns:
        int: значение счётчика после увеличения.
    """
    state = _load_state()
    state["count"] += 1
    _save_state(state)
    return state["count"]


def format_metrika_api_daily_usage(context: str = "") -> str:
    """Текстовая строка с итогом суточного расхода квоты API Метрики."""
    count = get_metrika_api_requests_today()
    prefix = f"{context}: " if context else ""
    return (
        f"{prefix}Запросов к API Яндекс.Метрики за сегодня ({_today_str()}): {count}"
    )


def log_metrika_api_daily_usage(context: str = "") -> None:
    """Пишет итог суточного расхода квоты в лог и в консоль (отдельным блоком)."""
    message = format_metrika_api_daily_usage(context)
    logger.info(message)
    print(f"\n--- {message} ---\n")
