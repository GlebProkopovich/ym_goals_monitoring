import os
import requests
from dotenv import load_dotenv
from utils.logger import logger
from datetime import date, timedelta

load_dotenv()


def fetch_goals_fact(counters):
    """
    Получает значения достижений целей по данным из Яндекс.Метрики
    за последние два месяца до вчерашнего дня включительно
    для всех целей всех переданных счетчиков.

    Args:
        counters (list of tuples): Список кортежей (counter_id, agency_name)

    Returns:
        list of dict: Список словарей с данными по датам, целям и количеству достижений
    """
    logger.info("Запуск функции получения значений достижений целей для счетчиков...")

    end_date = (date.today() - timedelta(days=1)).strftime('%Y-%m-%d')
    start_date = (date.today() - timedelta(days=61)).strftime('%Y-%m-%d')

    goals_fact = []

    for counter_id, agency_name in counters:
        token = os.getenv(f"YM_API_TOKEN_{agency_name}")

        url = "https://api-metrika.yandex.net/stat/v1/data"
        params = {
            'ids': counter_id,
            'dimensions': 'ym:s:date, ym:s:goal',
            'metrics': 'ym:s:sumGoalReachesAny',
            'date1': start_date,
            'date2': end_date,
            'attribution': 'cross_device_last_significant',
            'accuracy': 'full',
            'limit': 100000
        }
        headers = {'Authorization': f'OAuth {token}'}

        try:
            response = requests.get(url, headers=headers, params=params, timeout=30)
            response.raise_for_status()

            data = response.json().get("data", [])
            if not data:
                logger.warning(f"Пустой ответ API для счетчика {counter_id}")
                continue

            for row in data:
                try:
                    date_str = row["dimensions"][0]["name"]  # ym:s:date
                    goal_id = int(row["dimensions"][1]["id"])  # ym:s:goal
                    reaches = int(row["metrics"][0])  # ym:s:sumGoalReachesAny

                    goals_fact.append({
                        'date': date_str,
                        'goal_id': goal_id,
                        'reaches': reaches
                    })
                except (KeyError, IndexError, ValueError) as e:
                    logger.warning(f"Некорректная строка данных от API для счетчика {counter_id}: {row}, ошибка: {e}")

            logger.info(
                f"Успешно получены данные для счетчика {counter_id} "
                f"за период с {start_date} по {end_date}"
            )

        except requests.exceptions.RequestException as e:
            logger.error(
                f"Ошибка API для счетчика {counter_id}: {str(e)}. "
                f"URL: {url}, Параметры: {params}"
            )
        except Exception as e:
            logger.error(f"Ошибка при обработке данных для счетчика {counter_id}: {str(e)}")

    logger.info(f"Данные по {len(goals_fact)} записям целей успешно получены")
    return goals_fact