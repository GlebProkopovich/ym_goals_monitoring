from utils.logger import logger
from db.db_connection import get_db_connection


def extract_goals_info(db_config):
    """
   Извлекает информацию о всех целях из таблицы ym_goals целях.

   Args:
       db_config (dict): Конфигурация подключения к базе данных.

   Returns:
       list of tuples: Список кортежей с информацией о целях в формате:
                       (goal_id, counter_id, agency_name)
   """
    logger.info("Извлечение целей, из таблицы ym_goals...")
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
        """)

        results = cur.fetchall()
        for row in results:
            tracking_goals_info.append(row)

        logger.info(f"Извлечено {len(tracking_goals_info)} целей из таблицы ym_goals")

        return tracking_goals_info