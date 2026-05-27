"""Общие периоды дат для загрузки фактов и мониторинга."""

from datetime import timedelta

# От (вчера - 12) до вчера включительно = 13 календарных дней.
# Покрывает категорию low: эталон 8–17 + проверка 18–19–20 при вчера = 20 мая.
FACTS_LOOKBACK_DAYS = 12


def facts_date_range(yesterday):
    """Возвращает (start_day, end_day) для загрузки и анализа фактов."""
    start_day = yesterday - timedelta(days=FACTS_LOOKBACK_DAYS)
    return start_day, yesterday
