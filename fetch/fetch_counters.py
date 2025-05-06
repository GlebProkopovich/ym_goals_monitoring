import os
import requests
from dotenv import load_dotenv
from utils.logger import logger

load_dotenv()


def fetch_counters(agencies_info):
    """
    Получает счетчики Яндекс.Метрики для списка агентств.

    Args:
        agencies_info: Список кортежей (agency_id, agency_name) с информацией об агентствах

    Returns:
        Список словарей с данными счетчиков, обогащенными agency_id

    Raises:
        ValueError: При некорректных входных данных
    """
    logger.info("Запуск функции получения счетчиков Яндекс.Метрики")

    if not agencies_info or not isinstance(agencies_info, list):
        error_msg = "Некорректные данные об агентствах: ожидается непустой список"
        logger.error(error_msg)
        raise ValueError(error_msg)

    url = 'https://api-metrika.yandex.net/management/v1/counters'
    all_counters = []

    for agency_id, agency_name in agencies_info:
        if not isinstance(agency_name, str) or not agency_name.strip():
            logger.warning(f"Пропускаем некорректное название агентства: {agency_name}")
            continue

        token = os.getenv(f"YM_API_TOKEN_{agency_name}")
        if not token:
            logger.warning(f"Для агентства '{agency_name}' отсутствует токен, пропускаем")
            continue

        try:
            response = requests.get(
                url,
                headers={'Authorization': f'OAuth {token}'},
                timeout=30
            )
            response.raise_for_status()

            counters = response.json().get('counters', [])
            logger.info(f"Получено {len(counters)} счетчиков для агентства {agency_name}")

            # Добавляем agency_id к каждому счетчику
            for counter in counters:
                counter['agency_id'] = agency_id

            all_counters.extend(counters)

        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка запроса для агентства {agency_name}: {str(e)}")
            continue
        except Exception as e:
            logger.error(f"Неожиданная ошибка для агентства {agency_name}: {str(e)}")
            continue

    return all_counters