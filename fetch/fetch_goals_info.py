import os
import requests
from dotenv import load_dotenv
from utils.logger import logger

load_dotenv()


def fetch_goals_info(counters):
    """
    Получает список всех целей для каждого счетчика через API управления Яндекс.Метрики (management/v1).

    Args:
        counters: Список счетчиков в формате [(counter_id, agency_name), ...]

    Returns:
        Список словарей с ключами:
        - counter_id: ID счетчика
        - goal_id: ID цели
        - type: Тип цели (например, 'url', 'action')
        - name: Название цели

    Raises:
        ValueError: Если не удалось обработать ни один счетчик
    """
    url_template = "https://api-metrika.yandex.net/management/v1/counter/{}/goals"
    all_goals = []
    processed_counters = 0

    logger.info(f"Начало получения списка целей для {len(counters)} счетчиков")

    for counter_id, agency_name in counters:
        token = os.getenv(f"YM_API_TOKEN_{agency_name}")
        if not token:
            logger.warning(f"Токен не найден для агентства {agency_name} (ID счётчика: {counter_id}) — пропускаем")
            continue

        url = url_template.format(counter_id)
        headers = {'Authorization': f'OAuth {token}'}

        try:
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            response_json = response.json()
            goals = response_json.get('goals', [])

            for goal in goals:
                all_goals.append({
                    'counter_id': counter_id,
                    'goal_id': goal.get('id'),
                    'type': goal.get('type'),
                    'name': goal.get('name')
                })

            logger.info(f"Получено {len(goals)} целей для агентства {agency_name} (ID счётчика: {counter_id})")
            processed_counters += 1

        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка API для агентства {agency_name} (ID счётчика: {counter_id}): {str(e)}")
        except Exception as e:
            logger.error(f"Неожиданная ошибка для агентства {agency_name} (ID счётчика: {counter_id}): {str(e)}")

    if not all_goals:
        error_msg = "Не удалось получить цели ни для одного счетчика"
        logger.error(error_msg)
        raise ValueError(error_msg)

    logger.info(f"Успешно обработано {processed_counters}/{len(counters)} счетчиков")
    return all_goals