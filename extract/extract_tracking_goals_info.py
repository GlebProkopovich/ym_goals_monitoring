from utils.logger import logger
from db.db_connection import get_db_connection


def extract_tracking_goals_info(db_config):
    """
   Извлекает информацию о целях, которые уже находятся в мониторинге,
   то есть у которых указана дата начала мониторинга (start_monitoring_date),
   которая наступила (сегодня или ранее).

   Args:
       db_config (dict): Конфигурация подключения к базе данных.

   Returns:
       list of tuples: Список кортежей с информацией о целях в формате:
                       (goal_id, counter_id, agency_name)
   """
    logger.info("Извлечение целей, находящихся в мониторинге...")
    tracking_goals_info = []
    with get_db_connection(db_config) as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT
                g.id as goal_id,
                g.counter_id as counter_id,
                a.name as agency_name
            FROM
                ym_goals g
            JOIN
                ym_counters c
            ON
                c.id = g.counter_id
            JOIN
                agencies a
            ON
                c.agency_id = a.id
            WHERE 
                g.start_monitoring_date <= CURRENT_DATE
        """)

        results = cur.fetchall()
        for row in results:
            tracking_goals_info.append(row)

        logger.info(f"Извлечено {len(tracking_goals_info)} целей для мониторинга")

        return tracking_goals_info


def extract_counters_for_tracking_goals(tracking_goals_info):
    """
    Уникальные счётчики среди целей в мониторинге.

    Returns:
        list[tuple]: [(counter_id, agency_name), ...]
    """
    seen = set()
    counters = []
    for _goal_id, counter_id, agency_name in tracking_goals_info:
        key = (counter_id, agency_name)
        if key not in seen:
            seen.add(key)
            counters.append(key)
    logger.info(f"Для мониторинга нужно {len(counters)} уникальных счётчиков")
    return counters