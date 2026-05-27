import os
import requests
from dotenv import load_dotenv

from utils.http_retry import request_with_retry
from utils.logger import logger

load_dotenv()


def fetch_counters(agencies_info):
    """
    Получает счетчики Яндекс.Метрики для списка агентств.

    Args:
        agencies_info: Список кортежей (agency_id, agency_name) с информацией об агентствах

    Returns:
        tuple: (список словарей счётчиков с agency_id, множество agency_id с успешным ответом API)

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
    fetched_agency_ids = set()

    for agency_id, agency_name in agencies_info:
        if not isinstance(agency_name, str) or not agency_name.strip():
            logger.warning(f"Пропускаем некорректное название агентства: {agency_name}")
            continue

        token = os.getenv(f"YM_API_TOKEN_{agency_name}")
        if not token:
            logger.warning(f"Для агентства '{agency_name}' отсутствует токен, пропускаем")
            continue

        try:
            response = request_with_retry(
                "GET",
                url,
                headers={"Authorization": f"OAuth {token}"},
                timeout=30,
            )

            counters = response.json().get('counters', [])
            fetched_agency_ids.add(agency_id)
            logger.info(f"Получено {len(counters)} счетчиков для агентства {agency_name}")

            for counter in counters:
                counter['agency_id'] = agency_id
                counter['agency_name'] = agency_name

            all_counters.extend(counters)

        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка запроса для агентства {agency_name}: {str(e)}")
            continue
        except Exception as e:
            logger.error(f"Неожиданная ошибка для агентства {agency_name}: {str(e)}")
            continue

    return all_counters, fetched_agency_ids